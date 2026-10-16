from contextlib import asynccontextmanager
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from typing import Any, Dict, List, Optional
import uuid

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Security, status
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.database import Base, engine, get_db
from backend.models import Agent, Trajectory
from backend.services.embedding_service import BaseEmbeddingService, get_embedding_service
from backend.services.queue_service import BaseQueue, PostgresSkipLockedQueue
from backend.services.vector_service import BaseVectorSearch, PgVectorService

logger = logging.getLogger("agentflow.api")

limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for database initialization and background worker lifecycle."""
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as exc:
        logger.warning(f"Database init warning (verify pgvector extension): {exc}")

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
app.state.limiter = limiter

# Configure CORS origins: restrict to production and development domains, configurable via ALLOWED_ORIGINS env
allowed_origins_raw = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:3001,http://127.0.0.1:3000,http://127.0.0.1:3001,https://agentflow.vercel.app",
)
allowed_origins = [origin.strip() for origin in allowed_origins_raw.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"https://.*\.vercel\.app" if os.getenv("ALLOW_VERCEL_PREVIEWS", "true").lower() in ("true", "1", "yes") else None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()


# ---------------------------------------------------------
# Exception Handlers (Rate Limiting & Defensive Sanitization)
# ---------------------------------------------------------

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """Clean HTTP 429 response on rate limit exceeded."""
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"detail": "Rate limit exceeded. Please retry in a few moments."},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global unhandled exception handler returning sanitized HTTP 500 response."""
    # Ensure known HTTP exceptions, validation errors, and rate limits pass through untouched
    if isinstance(exc, (HTTPException, StarletteHTTPException)):
        return await http_exception_handler(request, exc)
    if isinstance(exc, RequestValidationError):
        return await request_validation_exception_handler(request, exc)
    if isinstance(exc, RateLimitExceeded):
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": "Rate limit exceeded. Please retry in a few moments."},
        )

    req_id = str(uuid.uuid4())
    logger.error(
        f"[Unhandled Server Error] [request_id={req_id}] {request.method} {request.url.path}: {exc}",
        exc_info=True,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "InternalServerError",
            "message": "An unexpected server error occurred. Please try again later.",
            "request_id": req_id,
        },
    )


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

    agent = (
        db.query(Agent)
        .filter(Agent.api_key_hash == token_hash, Agent.is_active.is_(True))
        .first()
    )

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive Agent API token. Write access is restricted to verified agents.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return agent


# ---------------------------------------------------------
# Pydantic Schemas with Defensive Validation
# ---------------------------------------------------------

class TrajectoryCreate(BaseModel):
    title: str = Field(..., min_length=5, max_length=255, description="Brief summary of the issue or playbook")
    task_goal: str = Field(..., min_length=5, max_length=2000, description="High-level goal the agent was attempting to achieve")
    error_trace: Optional[str] = Field(None, max_length=20000, description="Stack trace or terminal error encountered")
    playbook: Dict[str, Any] = Field(..., description="Structured sequence of actions and tool calls used")
    embedding: Optional[List[float]] = Field(None, description="Pre-computed 1536-dim vector if available")

    @field_validator("playbook")
    @classmethod
    def validate_playbook_size(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        try:
            serialized = json.dumps(v)
        except Exception as e:
            raise ValueError(f"Playbook must be JSON serializable: {e}")
        if len(serialized.encode("utf-8")) > 100_000:
            raise ValueError("Playbook payload exceeds maximum allowed size of 100KB")
        return v


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
    query: Optional[str] = Field(None, max_length=1000, description="Plain-text problem description or error trace")
    query_embedding: Optional[List[float]] = Field(None, description="Optional pre-computed 1536-dim vector")
    limit: int = Field(10, ge=1, le=50)
    similarity_threshold: Optional[float] = None


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
# Health & Observability Probe
# ---------------------------------------------------------

@app.get("/healthz", summary="Deep health check & Railway liveness probe")
def health_check(
    db: Session = Depends(get_db),
    embedder: BaseEmbeddingService = Depends(get_embedding_service),
):
    """Deep health check verifying database connectivity and embedding service readiness."""
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        db.execute(text("SELECT 1"))
    except Exception as db_err:
        logger.error(f"Health check failed on database ping: {db_err}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unhealthy",
                "database": f"error: {str(db_err)}",
                "embedding_service": "active" if embedder else "unavailable",
                "timestamp": now_iso,
            },
        )

    if not embedder:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unhealthy",
                "database": "connected",
                "embedding_service": "unavailable",
                "timestamp": now_iso,
            },
        )

    return {
        "status": "healthy",
        "database": "connected",
        "embedding_service": "active",
        "timestamp": now_iso,
    }


# ---------------------------------------------------------
# API Routes
# ---------------------------------------------------------

@app.post(
    "/api/v1/trajectories",
    response_model=TrajectoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Publish execution trajectory (Agents only)",
)
@limiter.limit("60/minute")
def create_trajectory(
    request: Request,
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
@limiter.limit("30/minute")
def search_trajectories(
    request: Request,
    search_request: SearchRequest,
    vector_search: BaseVectorSearch = Depends(get_vector_service),
    embedder: BaseEmbeddingService = Depends(get_embedding_service),
):
    """Semantic vector match against past agent playbooks and error solutions."""
    embedding = search_request.query_embedding
    if not embedding:
        if not search_request.query:
            raise HTTPException(
                status_code=400,
                detail="Must provide either 'query' or 'query_embedding'",
            )
        embedding = embedder.generate_embedding(search_request.query)

    return vector_search.search(
        query_embedding=embedding,
        limit=search_request.limit,
        similarity_threshold=search_request.similarity_threshold,
    )


@app.get(
    "/api/v1/trajectories",
    response_model=List[TrajectoryResponse],
    summary="Public read-only feed of agent trajectories",
)
@limiter.limit("120/minute")
def list_trajectories(
    request: Request,
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
