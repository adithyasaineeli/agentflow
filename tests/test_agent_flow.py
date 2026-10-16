import hashlib
import os
import uuid
import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from starlette.testclient import TestClient

from backend.database import Base, get_db
from backend.main import app
from backend.models import Agent, QueueTask, Trajectory
from backend.services.embedding_service import get_embedding_service
from backend.services.queue_service import PostgresSkipLockedQueue
from backend.services.vector_service import PgVectorService
from backend.worker import process_task

# Ensure .env is loaded
load_dotenv()


# ---------------------------------------------------------------------------
# Test Fixtures & Engine Configuration
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def db_engine():
    """Provides a database engine based on DATABASE_URL in .env, with automatic test isolation."""
    env_db_url = os.getenv("DATABASE_URL", "sqlite:///agentflow_test.db")

    # Driver normalization for psycopg2
    if env_db_url.startswith("postgres://"):
        env_db_url = env_db_url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif env_db_url.startswith("postgresql://") and "+psycopg2" not in env_db_url:
        env_db_url = env_db_url.replace("postgresql://", "postgresql+psycopg2://", 1)

    connect_args = {}
    engine_kwargs = {"pool_pre_ping": True}
    if "sqlite" in env_db_url:
        connect_args["check_same_thread"] = False
        engine_kwargs["connect_args"] = connect_args

    engine = create_engine(env_db_url, **engine_kwargs)

    # Ensure schema tables exist
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as exc:
        print(f"[Fixture Warning] Table creation encountered: {exc}")

    yield engine


@pytest.fixture(scope="session")
def session_factory(db_engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=db_engine)


@pytest.fixture
def db_session(session_factory):
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(session_factory):
    def override_get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# Shared token across test steps
TEST_RAW_TOKEN = "agentflow-secret-token-integration-xyz-987"
TEST_TOKEN_HASH = hashlib.sha256(TEST_RAW_TOKEN.encode("utf-8")).hexdigest()
TEST_AGENT_ID = "agent-test-fixed-uuid-001"


# ---------------------------------------------------------------------------
# Integration Workflow Tests
# ---------------------------------------------------------------------------

def test_01_database_connectivity_and_extensions(db_engine):
    """Step 1: Verify database connection, vector extension support, and table schema."""
    with db_engine.connect() as conn:
        result = conn.execute(text("SELECT 1")).scalar()
        assert result == 1, "Failed basic connection query."

        # If connected to live PostgreSQL, verify pgvector extension
        if db_engine.dialect.name == "postgresql":
            ext_check = conn.execute(
                text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
            ).fetchone()
            if not ext_check:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
                conn.commit()
                ext_check = conn.execute(
                    text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
                ).fetchone()
            assert ext_check is not None, "pgvector extension is not installed on PostgreSQL."

    # Verify that the pgvector Vector column definition is attached to Trajectory
    embedding_col = Trajectory.__table__.columns.get("embedding")
    assert embedding_col is not None, "Trajectory model missing 'embedding' column."

    # Verify all 3 required tables exist in database
    inspector = inspect(db_engine)
    tables = inspector.get_table_names()
    assert "agents" in tables, f"'agents' table not found in {tables}"
    assert "trajectories" in tables, f"'trajectories' table not found in {tables}"
    assert "queue_tasks" in tables, f"'queue_tasks' table not found in {tables}"


def test_02_seed_agent_and_machine_auth(client, db_session):
    """Step 2: Seed test agent and verify machine authentication enforcement."""
    # Seed known test agent idempotently
    agent = db_session.query(Agent).filter(Agent.api_key_hash == TEST_TOKEN_HASH).first()
    if not agent:
        agent = Agent(
            id=TEST_AGENT_ID,
            name="Integration Test Autonomous Agent",
            api_key_hash=TEST_TOKEN_HASH,
            is_active=True,
        )
        db_session.add(agent)
    else:
        agent.is_active = True
    db_session.commit()

    # 1. Unauthenticated request must return 401
    unauth_response = client.post(
        "/api/v1/trajectories",
        json={
            "title": "Unauthorized attempt",
            "task_goal": "Attempting trajectory write without credentials",
            "playbook": {"execution_steps": []},
        },
    )
    assert unauth_response.status_code == 401, (
        f"Expected 401 for unauthenticated request, got {unauth_response.status_code}"
    )

    # 2. Invalid Bearer token must also return 401
    invalid_token_response = client.post(
        "/api/v1/trajectories",
        json={
            "title": "Invalid token attempt",
            "task_goal": "Attempting trajectory write with bad credentials",
            "playbook": {"execution_steps": []},
        },
        headers={"Authorization": "Bearer totally-invalid-token-000"},
    )
    assert invalid_token_response.status_code == 401


def test_03_ingestion_and_asynchronous_queue(client, db_session):
    """Step 3: Publish trajectory with valid agent auth; assert HTTP 201/202 and PENDING queue record."""
    payload = {
        "title": "Fix React state hydration mismatch in SSR",
        "task_goal": "Resolve unhandled text mismatch between server rendered HTML and client DOM",
        "error_trace": "Error: Hydration failed because the initial UI does not match what was rendered on the server.",
        "playbook": {
            "execution_steps": [
                {"tool": "read_file", "path": "src/app/page.tsx"},
                {
                    "tool": "apply_patch",
                    "diff": "- <span>{Date.now()}</span>\n+ <span>{mounted ? Date.now() : null}</span>",
                },
            ],
            "verification_command": "npm run build && npm run test:e2e",
        },
    }

    response = client.post(
        "/api/v1/trajectories",
        json=payload,
        headers={"Authorization": f"Bearer {TEST_RAW_TOKEN}"},
    )

    # Allow HTTP 201 Created or HTTP 202 Accepted
    assert response.status_code in (201, 202), f"Expected 201/202, got {response.status_code}: {response.text}"
    data = response.json()

    assert data["title"] == payload["title"]
    assert data["task_goal"] == payload["task_goal"]
    assert data["status"] == "pending"
    enqueued_task_id = data.get("enqueued_task_id")
    assert enqueued_task_id is not None, "Response must include an enqueued_task_id"

    # Verify task record in queue_tasks table
    task = db_session.query(QueueTask).filter(QueueTask.id == enqueued_task_id).first()
    assert task is not None, f"QueueTask '{enqueued_task_id}' not found in database."
    assert task.status == "PENDING"
    assert task.task_type == "generate_embedding"
    assert task.payload["trajectory_id"] == data["id"]


def test_04_worker_processing(db_session):
    """Step 4: Execute worker cycle; assert task transitions PENDING -> COMPLETED and embedding populated."""
    queue_service = PostgresSkipLockedQueue(db_session)
    embedding_service = get_embedding_service()

    # Dequeue batch
    dequeued_tasks = queue_service.dequeue(batch_size=5, worker_id="test-worker-runner")
    assert len(dequeued_tasks) >= 1, "Expected at least 1 task available for dequeueing."

    # Process all dequeued tasks to ensure the queue batch is processed
    target_task = None
    for task in dequeued_tasks:
        if task.get("task_type") == "generate_embedding":
            success = process_task(db_session, queue_service, embedding_service, task)
            assert success is True, "process_task returned False."
            target_task = task

    assert target_task is not None, "No generate_embedding task dequeued."

    # Confirm QueueTask status transitioned to COMPLETED
    completed_task = db_session.query(QueueTask).filter(QueueTask.id == target_task["id"]).first()
    assert completed_task is not None
    assert completed_task.status == "COMPLETED"

    # Confirm Trajectory record has non-null 1536-dimensional embedding
    trajectory_id = target_task["payload"]["trajectory_id"]
    trajectory = db_session.query(Trajectory).filter(Trajectory.id == trajectory_id).first()
    assert trajectory is not None
    assert trajectory.status == "completed"
    assert trajectory.embedding is not None
    assert len(trajectory.embedding) == 1536


def test_05_semantic_search_retrieval(client):
    """Step 5: Query POST /api/v1/trajectories/search with error query and assert cosine similarity score."""
    embedding_service = get_embedding_service()

    # Generate query embedding matching the seeded error and goal
    query_text = (
        "Task Goal:\nResolve unhandled text mismatch between server rendered HTML and client DOM\n\n"
        "Initial Error:\nError: Hydration failed because the initial UI does not match what was rendered on the server."
    )
    query_vector = embedding_service.generate_embedding(query_text)
    assert len(query_vector) == 1536

    search_response = client.post(
        "/api/v1/trajectories/search",
        json={
            "query_embedding": query_vector,
            "limit": 3,
            "similarity_threshold": 0.0,
        },
    )

    assert search_response.status_code == 200, f"Search failed: {search_response.text}"
    results = search_response.json()
    assert len(results) >= 1, "Expected at least 1 search result."

    matched = results[0]
    assert "React state hydration mismatch" in matched["title"]
    assert "similarity_score" in matched
    assert isinstance(matched["similarity_score"], (int, float))
    assert matched["similarity_score"] > 0.0


def test_06_public_read_feed(client):
    """Step 6: Query GET /api/v1/trajectories without auth headers and assert indexed trajectory is returned."""
    feed_response = client.get("/api/v1/trajectories?limit=10&offset=0")
    assert feed_response.status_code == 200, f"Public feed failed: {feed_response.text}"

    feed_items = feed_response.json()
    assert isinstance(feed_items, list)
    assert len(feed_items) >= 1

    # Verify our published trajectory is present in the public feed
    matched_item = next(
        (t for t in feed_items if "React state hydration mismatch" in t.get("title", "")),
        None,
    )
    assert matched_item is not None, "Indexed trajectory not found in public feed."
    assert matched_item["status"] == "completed"
    assert matched_item["task_goal"] != ""
