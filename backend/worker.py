import logging
import os
import signal
import sys
import threading
import time
import uuid
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models import Trajectory
from backend.services.embedding_service import BaseEmbeddingService, get_embedding_service
from backend.services.queue_service import BaseQueue, PostgresSkipLockedQueue

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [Worker] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("agentflow.worker")

# Thread-safe event to signal worker stop
shutdown_event = threading.Event()


def handle_shutdown(signum: int, frame: Any) -> None:
    """Signal handler for graceful termination."""
    try:
        sig_name = signal.Signals(signum).name
    except (ValueError, AttributeError):
        sig_name = str(signum)

    logger.info(f"Received {sig_name}. Completing in-progress tasks before shutting down...")
    shutdown_event.set()


def process_task(
    db: Session,
    queue_service: BaseQueue,
    embedding_service: BaseEmbeddingService,
    task: Dict[str, Any],
) -> bool:
    """Processes a single task: generates embedding and updates the Trajectory."""
    task_id = task["id"]
    task_type = task.get("task_type")
    payload = task.get("payload") or {}

    logger.info(f"Processing task {task_id} (type: '{task_type}')")

    try:
        if task_type in ("generate_embedding", "index_trajectory"):
            trajectory_id = payload.get("trajectory_id")
            if not trajectory_id:
                raise ValueError(f"Task payload is missing required 'trajectory_id': {payload}")

            trajectory = db.query(Trajectory).filter(Trajectory.id == trajectory_id).first()
            if not trajectory:
                raise ValueError(f"Trajectory '{trajectory_id}' not found in database.")

            # Extract task_goal and initial_error (or error_trace) from payload or fallback to database model
            task_goal = payload.get("task_goal") or trajectory.task_goal or ""
            initial_error = (
                payload.get("initial_error")
                or payload.get("error_trace")
                or trajectory.error_trace
                or ""
            )

            # Combine task_goal and initial_error into a semantic string for embedding
            embedding_parts = []
            if task_goal.strip():
                embedding_parts.append(f"Task Goal:\n{task_goal.strip()}")
            if initial_error.strip():
                embedding_parts.append(f"Initial Error:\n{initial_error.strip()}")

            text_to_embed = "\n\n".join(embedding_parts)
            if not text_to_embed.strip():
                text_to_embed = payload.get("text_to_embed") or trajectory.title or "empty"

            logger.debug(f"Generating 1536-dim embedding for trajectory '{trajectory_id}'...")
            embedding_vector = embedding_service.generate_embedding(text_to_embed)

            # Update the Trajectory record with the generated embedding
            trajectory.embedding = embedding_vector
            trajectory.status = "completed"
            db.commit()

            # Mark QueueTask as COMPLETED
            queue_service.ack(task_id)
            logger.info(f"Successfully indexed trajectory '{trajectory_id}'. Task '{task_id}' -> COMPLETED.")
            return True

        else:
            logger.warning(f"Unrecognized task_type '{task_type}' for task '{task_id}'. Marking COMPLETED.")
            queue_service.ack(task_id)
            return True

    except Exception as exc:
        db.rollback()
        error_msg = f"Failed to process task '{task_id}': {exc}"
        logger.error(error_msg, exc_info=True)
        queue_service.nack(task_id, error=str(exc))
        return False


def run_worker(
    poll_interval: float = 1.5,
    batch_size: int = 5,
    worker_id: Optional[str] = None,
) -> None:
    """Continuously poll for PENDING tasks, process them, and handle graceful shutdown."""
    worker_id = worker_id or f"worker-{os.getpid()}-{uuid.uuid4().hex[:6]}"
    logger.info(
        f"Starting AgentFlow worker [{worker_id}] (poll_interval={poll_interval}s, batch_size={batch_size})"
    )

    # Register OS signals only if running in the main thread
    if threading.current_thread() is threading.main_thread():
        try:
            signal.signal(signal.SIGINT, handle_shutdown)
            signal.signal(signal.SIGTERM, handle_shutdown)
        except (ValueError, AttributeError) as sig_err:
            logger.debug(f"Could not attach signal handlers: {sig_err}")

    embedding_service = get_embedding_service()

    while not shutdown_event.is_set():
        db: Session = SessionLocal()
        try:
            queue_service = PostgresSkipLockedQueue(db)
            # Dequeue up to batch_size pending tasks using SKIP LOCKED
            tasks = queue_service.dequeue(batch_size=batch_size, worker_id=worker_id)

            if tasks:
                logger.info(f"Dequeued {len(tasks)} PENDING task(s) for execution.")
                for task in tasks:
                    process_task(db, queue_service, embedding_service, task)
            else:
                # Sleep in short slices so we can break immediately on shutdown signal
                sleep_increments = max(1, int(poll_interval * 10))
                for _ in range(sleep_increments):
                    if shutdown_event.is_set():
                        break
                    time.sleep(0.1)

        except Exception as exc:
            logger.error(f"Worker loop error: {exc}", exc_info=True)
            time.sleep(poll_interval)
        finally:
            db.close()

    logger.info(f"Worker [{worker_id}] has exited cleanly.")


def start_worker_thread(poll_interval: float = 1.5, batch_size: int = 5) -> threading.Thread:
    """Starts the worker in a background daemon thread.

    Enables running the worker concurrently within the FastAPI process during local development.
    """
    thread = threading.Thread(
        target=run_worker,
        kwargs={"poll_interval": poll_interval, "batch_size": batch_size},
        name="agentflow-background-worker",
        daemon=True,
    )
    thread.start()
    logger.info("AgentFlow background worker thread launched.")
    return thread


if __name__ == "__main__":
    run_worker()
