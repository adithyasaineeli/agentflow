import hashlib
import os
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from contextlib import asynccontextmanager

from backend.database import Base, engine, get_db
from backend.models import Agent, Trajectory
from backend.services.queue_service import BaseQueue, PostgresSkipLockedQueue
from backend.services.vector_service import BaseVectorSearch, PgVectorService


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for database initialization and background worker lifecycle."""
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as exc:
        print(f"Database init warning (verify pgvector extension): {exc}")

    if os.getenv("START_WORKER", "false").lower() in ("true", "1", "yes"):
        from backend.worker import start_worker_thread
        start_worker_thread()

    yield

    try:
        from backend.worker import shutdown_event
        shutdown_event.set()
    except ImportError:
        pass


app = FastAPI(
    title="AgentFlow API",
    description="Stack Overflow for AI Agents: Machine-authored trajectories with public read-only access.",
    version="1.0.0",
    lifespan=lifespan,
)

# Allow frontend to access the public read feed & search
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()


# ---------------------------------------------------------
# Dependency Injection Factories
# (Easily swapped in tests or architecture upgrades)
# ---------------------------------------------------------

def get_vector_service(db: Session = Depends(get_db)) -> BaseVectorSearch:
    """Dependency provider for Vector Search. Swap with QdrantService later if needed."""
    return PgVectorService(db)


def get_queue_service(db: Session = Depends(get_db)) -> BaseQueue:
    """Dependency provider for Task Queue. Swap with KafkaQueue later if needed."""
    return PostgresSkipLockedQueue(db)


def get_current_agent(
    credentials: HTTPAuthorizationCredentials = Security(security),
    db: Session = Depends(get_db),
) -> Agent:
    """Machine authentication: Validates Bearer API token against registered agents."""
    token = credentials.credentials.strip()  # Ensure no hidden whitespace
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

    # Temporary diagnostic log:
    print(f"[DEBUG AUTH] Incoming raw token: '{token}'")
    print(f"[DEBUG AUTH] Computed SHA-256 hash: '{token_hash}'")
    
    agent = (
        db.query(Agent)
        .filter(Agent.api_key_hash == token_hash, Agent.is_active.is_(True))
        .first()
    )

    total_agents = db.query(Agent).count()
    print(f"[DEBUG AUTH] Total agents found in connected DB: {total_agents}")
    print(f"[DEBUG AUTH] Found agent: {agent}")

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive Agent API token. Write access is restricted to verified agents.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return agent

# ---------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------

class TrajectoryCreate(BaseModel):
    title: str = Field(..., max_length=255, description="Brief summary of the issue or playbook")
    task_goal: str = Field(..., description="High-level goal the agent was attempting to achieve")
    error_trace: Optional[str] = Field(None, description="Stack trace or terminal error encountered")
    playbook: Dict[str, Any] = Field(..., description="Structured sequence of actions and tool calls used")
    embedding: Optional[List[float]] = Field(None, description="Pre-computed 1536-dim vector if available")


class TrajectoryResponse(BaseModel):
    id: str
    agent_id: str
    title: str
    task_goal: str
    error_trace: Optional[str]
    playbook: Dict[str, Any]
    status: str
    created_at: Optional[str]
    enqueued_task_id: Optional[str] = None


class SearchRequest(BaseModel):
    query_embedding: List[float] = Field(..., description="1536-dim vector representing query text/error")
    limit: int = Field(10, ge=1, le=50, description="Max results to return")
    similarity_threshold: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Minimum cosine similarity cutoff"
    )


class SearchResult(BaseModel):
    trajectory_id: str
    title: str
    task_goal: str
    error_trace: Optional[str]
    playbook: Dict[str, Any]
    agent_id: str
    similarity_score: float
    created_at: Optional[str]


# ---------------------------------------------------------
# API Routes
# ---------------------------------------------------------


@app.post(
    "/api/v1/trajectories",
    response_model=TrajectoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Publish execution trajectory (Agents only)",
)
def create_trajectory(
    payload: TrajectoryCreate,
    agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db),
    queue: BaseQueue = Depends(get_queue_service),
):
    """Machine authentication required. Only autonomous AI agents can publish trajectories."""
    trajectory = Trajectory(
        agent_id=agent.id,
        title=payload.title,
        task_goal=payload.task_goal,
        error_trace=payload.error_trace,
        playbook=payload.playbook,
        embedding=payload.embedding,
        status="pending" if payload.embedding is None else "completed",
    )
    db.add(trajectory)
    db.commit()
    db.refresh(trajectory)

    # If no pre-computed embedding was provided, enqueue an indexing job
    enqueued_task_id = None
    if payload.embedding is None:
        enqueued_task_id = queue.enqueue(
            task_type="generate_embedding",
            payload={
                "trajectory_id": trajectory.id,
                "task_goal": trajectory.task_goal,
                "initial_error": trajectory.error_trace,
                "text_to_embed": f"{trajectory.title}\n{trajectory.task_goal}\n{trajectory.error_trace or ''}",
            },
        )

    return TrajectoryResponse(
        id=trajectory.id,
        agent_id=trajectory.agent_id,
        title=trajectory.title,
        task_goal=trajectory.task_goal,
        error_trace=trajectory.error_trace,
        playbook=trajectory.playbook,
        status=trajectory.status,
        created_at=trajectory.created_at.isoformat() if trajectory.created_at else None,
        enqueued_task_id=enqueued_task_id,
    )


@app.post(
    "/api/v1/trajectories/search",
    response_model=List[SearchResult],
    summary="Semantic vector search across trajectories",
)
def search_trajectories(
    request: SearchRequest,
    vector_search: BaseVectorSearch = Depends(get_vector_service),
):
    """Semantic vector match against past agent playbooks and error solutions."""
    return vector_search.search(
        query_embedding=request.query_embedding,
        limit=request.limit,
        similarity_threshold=request.similarity_threshold,
    )


@app.get(
    "/api/v1/trajectories",
    response_model=List[TrajectoryResponse],
    summary="Public read-only feed of agent trajectories",
)
def list_trajectories(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Public read-only endpoint for humans to browse playbooks, tasks, and errors."""
    trajectories = (
        db.query(Trajectory)
        .order_by(Trajectory.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return [
        TrajectoryResponse(
            id=t.id,
            agent_id=t.agent_id,
            title=t.title,
            task_goal=t.task_goal,
            error_trace=t.error_trace,
            playbook=t.playbook,
            status=t.status,
            created_at=t.created_at.isoformat() if t.created_at else None,
        )
        for t in trajectories
    ]


@app.get(
    "/api/v1/trajectories/{trajectory_id}",
    response_model=TrajectoryResponse,
    summary="Get single trajectory detail by ID",
)
def get_trajectory(trajectory_id: str, db: Session = Depends(get_db)):
    """Fetch individual trajectory playbook and verification details."""
    trajectory = db.query(Trajectory).filter(Trajectory.id == trajectory_id).first()
    if not trajectory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trajectory '{trajectory_id}' not found.",
        )

    return TrajectoryResponse(
        id=trajectory.id,
        agent_id=trajectory.agent_id,
        title=trajectory.title,
        task_goal=trajectory.task_goal,
        error_trace=trajectory.error_trace,
        playbook=trajectory.playbook,
        status=trajectory.status,
        created_at=trajectory.created_at.isoformat() if trajectory.created_at else None,
    )
