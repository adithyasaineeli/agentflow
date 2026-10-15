#!/usr/bin/env bash
set -e

echo "==> [AgentFlow] Verifying database connectivity and schema..."
python -c "
from backend.database import Base, engine
try:
    Base.metadata.create_all(bind=engine)
    print('[AgentFlow] Database schema verified successfully.')
except Exception as e:
    print(f'[AgentFlow Warning] Database initialization: {e}')
" || true

# Optional auto-seeding flag for staging/demo environments
if [ "${AUTO_SEED:-false}" = "true" ]; then
    echo "==> [AgentFlow] Auto-seeding production playbooks..."
    python -m backend.scripts.seed_playbooks || true
fi

echo "==> [AgentFlow] Starting background queue worker..."
python -m backend.worker &

echo "==> [AgentFlow] Starting FastAPI & FastMCP web application on port ${PORT:-8000}..."
exec uvicorn backend.main:app --host 0.0.0.0 --port "${PORT:-8000}"
