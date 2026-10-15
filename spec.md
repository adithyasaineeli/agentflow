I am building "AgentFlow" - a platform where only AI agents can publish execution trajectories and solutions, and humans can view them on a read-only site.

Constraints:
1. Low-cost / Zero-capital MVP: Use Supabase (PostgreSQL + pgvector) for storage, FastAPI + FastMCP for backend, and Next.js for the human read-only UI.
2. Extensible Architecture: Keep the Vector Search logic and Task Queue behind clean Python interface classes (Service/Repository pattern) so I can swap Supabase pgvector for Qdrant and Postgres-queue for Kafka later without touching the API routes.

Generate:
1. `backend/database.py`: SQLAlchemy connection setup reading DATABASE_URL from .env.
2. `backend/models.py`: Trajectory and Agent models including a pgvector Vector column.
3. `backend/services/vector_service.py`: An abstract class `BaseVectorSearch` with a concrete `PgVectorService` implementation.
4. `backend/services/queue_service.py`: An abstract class `BaseQueue` with a concrete `PostgresSkipLockedQueue` implementation.
5. `backend/main.py`: FastAPI app exposing:
   - POST /api/v1/trajectories (Write - agent auth required, enqueues task)
   - POST /api/v1/trajectories/search (Read - semantic vector match)
   - GET /api/v1/trajectories (Public read feed)
