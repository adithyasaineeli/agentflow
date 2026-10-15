from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from backend.models import QueueTask


class BaseQueue(ABC):
    """Abstract base class defining the contract for queue operations.

    Allows swapping the Postgres SKIP LOCKED queue with distributed message brokers
    (e.g. Kafka, RabbitMQ, Redis Streams, SQS) without modifying API routes.
    """

    @abstractmethod
    def enqueue(self, task_type: str, payload: Dict[str, Any]) -> str:
        """Push a new task to the queue and return its task_id."""
        pass

    @abstractmethod
    def dequeue(
        self,
        batch_size: int = 1,
        worker_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Atomically fetch up to batch_size available tasks for processing."""
        pass

    @abstractmethod
    def ack(self, task_id: str) -> bool:
        """Acknowledge successful completion of a task."""
        pass

    @abstractmethod
    def nack(self, task_id: str, error: Optional[str] = None) -> bool:
        """Mark task execution as failed."""
        pass


class PostgresSkipLockedQueue(BaseQueue):
    """Zero-capital PostgreSQL task queue using SELECT ... FOR UPDATE SKIP LOCKED."""

    def __init__(self, db: Session):
        self.db = db

    def enqueue(self, task_type: str, payload: Dict[str, Any]) -> str:
        task = QueueTask(task_type=task_type, payload=payload, status="PENDING")
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return task.id

    def dequeue(
        self,
        batch_size: Any = 1,
        worker_id: Optional[str] = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        # Handle flexible arguments (e.g. dequeue(worker_id="w1") or dequeue(batch_size=5))
        if isinstance(batch_size, str):
            actual_worker_id = batch_size
            actual_batch_size = kwargs.get("batch_size", 1)
        else:
            actual_batch_size = int(batch_size) if batch_size is not None else 1
            actual_worker_id = worker_id or kwargs.get("worker_id") or "worker"

        # SELECT ... FOR UPDATE SKIP LOCKED guarantees concurrent workers never block or double-process
        tasks = (
            self.db.query(QueueTask)
            .filter(QueueTask.status.in_(["PENDING", "pending", "queued"]))
            .order_by(QueueTask.created_at.asc())
            .with_for_update(skip_locked=True)
            .limit(actual_batch_size)
            .all()
        )

        if not tasks:
            return []

        results = []
        for task in tasks:
            task.status = "PROCESSING"
            task.locked_at = func.now()
            task.locked_by = actual_worker_id
            task.attempts += 1
            results.append({
                "id": task.id,
                "task_type": task.task_type,
                "payload": task.payload,
                "attempts": task.attempts,
            })

        self.db.commit()
        return results

    def ack(self, task_id: str) -> bool:
        task = self.db.query(QueueTask).filter(QueueTask.id == task_id).first()
        if not task:
            return False

        task.status = "COMPLETED"
        self.db.commit()
        return True

    def nack(self, task_id: str, error: Optional[str] = None) -> bool:
        task = self.db.query(QueueTask).filter(QueueTask.id == task_id).first()
        if not task:
            return False

        task.status = "FAILED"
        task.error = error
        self.db.commit()
        return True
