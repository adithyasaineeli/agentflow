import math
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from backend.models import Trajectory


class BaseVectorSearch(ABC):
    """Abstract base class defining the contract for vector search operations.

    Allows swapping pgvector with external vector DBs (e.g. Qdrant, Pinecone)
    without touching FastAPI route definitions.
    """

    @abstractmethod
    def search(
        self,
        query_embedding: List[float],
        limit: int = 10,
        similarity_threshold: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Search for trajectories semantically matching query_embedding."""
        pass

    @abstractmethod
    def upsert_embedding(self, trajectory_id: str, embedding: List[float]) -> bool:
        """Store or update vector embedding for a given trajectory."""
        pass


class PgVectorService(BaseVectorSearch):
    """PostgreSQL + pgvector implementation of vector similarity search."""

    def __init__(self, db: Session):
        self.db = db

    def search(
        self,
        query_embedding: List[float],
        limit: int = 10,
        similarity_threshold: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        is_postgres = (
            self.db.bind is not None
            and getattr(self.db.bind.dialect, "name", "") == "postgresql"
        )

        if is_postgres:
            # Cosine distance operator (<=> in pgvector): 0 means identical, 2 means opposite
            distance_col = Trajectory.embedding.cosine_distance(query_embedding).label("distance")
            query = (
                self.db.query(Trajectory, distance_col)
                .filter(Trajectory.embedding.isnot(None))
                .order_by(distance_col.asc())
            )
            rows = query.limit(limit).all()
        else:
            # Dialect-agnostic fallback (e.g. SQLite in test environments)
            trajectories = (
                self.db.query(Trajectory)
                .filter(Trajectory.embedding.isnot(None))
                .all()
            )
            scored = []
            for t in trajectories:
                emb = t.embedding
                if isinstance(emb, str):
                    import json
                    emb = json.loads(emb)
                dot = sum(a * b for a, b in zip(query_embedding, emb))
                norm_q = math.sqrt(sum(a * a for a in query_embedding)) or 1.0
                norm_e = math.sqrt(sum(a * a for a in emb)) or 1.0
                cos_sim = dot / (norm_q * norm_e)
                dist = 1.0 - cos_sim
                scored.append((t, dist))
            scored.sort(key=lambda x: x[1])
            rows = scored[:limit]

        results = []
        for trajectory, distance in rows:
            # Convert cosine distance to cosine similarity score: 1.0 - distance
            similarity = 1.0 - float(distance) if distance is not None else 0.0

            if similarity_threshold is not None and similarity < similarity_threshold:
                continue

            results.append({
                "trajectory_id": trajectory.id,
                "title": trajectory.title,
                "task_goal": trajectory.task_goal,
                "error_trace": trajectory.error_trace,
                "playbook": trajectory.playbook,
                "agent_id": trajectory.agent_id,
                "similarity_score": round(similarity, 4),
                "created_at": trajectory.created_at.isoformat() if trajectory.created_at else None,
            })

        return results

    def upsert_embedding(self, trajectory_id: str, embedding: List[float]) -> bool:
        trajectory = self.db.query(Trajectory).filter(Trajectory.id == trajectory_id).first()
        if not trajectory:
            return False

        trajectory.embedding = embedding
        self.db.commit()
        return True
