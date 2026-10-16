# 🚀 AgentFlow Production Deployment & Operations Runbook

This guide covers deploying and operating the full AgentFlow stack across **Railway** (FastAPI backend + worker), **Supabase** (PostgreSQL + pgvector), and **Vercel** (Next.js frontend).

---

## 1. Supabase (Database & pgvector Setup)

### Step 1: Create Database & Enable Extensions
1. Create a new Supabase project in your preferred region.
2. In the Supabase Dashboard, navigate to **SQL Editor** and run the database setup script located at [`backend/migrations/init.sql`](file:///Users/adithyasaineeli/Desktop/Agentflow/backend/migrations/init.sql):

```sql
-- Enable vector and UUID extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
```

### Step 2: Connection String Configuration
Supabase provides two connection modes in **Project Settings → Database**:
- **Session Mode (Direct - Port 5432)**: `postgresql://postgres:[PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres`
- **Transaction Pooler (Port 6543)**: `postgresql://postgres.[PROJECT-REF]:[PASSWORD]@aws-0-[REGION].pooler.supabase.com:6543/postgres?sslmode=require`

> **Recommendation**: Use the **Transaction Pooler (Port 6543)** for serverless and containerized environments. Our SQLAlchemy connection settings (`pool_size=10`, `pool_pre_ping=True`, `pool_recycle=300`) are pre-configured to handle Supabase pooler idle disconnects cleanly.

---

## 2. Railway (FastAPI Backend & Worker Deployment)

AgentFlow is configured with a root [`Procfile`](file:///Users/adithyasaineeli/Desktop/Agentflow/Procfile) and a containerized [`backend/Dockerfile`](file:///Users/adithyasaineeli/Desktop/Agentflow/backend/Dockerfile).

### Option A: Railway Procfile / Native Deploy
Railway automatically detects `Procfile` at the root:
```text
web: uvicorn backend.main:app --host 0.0.0.0 --port $PORT
worker: python -m backend.worker
```

### Option B: Unified Container Deploy via `start.sh`
[`backend/start.sh`](file:///Users/adithyasaineeli/Desktop/Agentflow/backend/start.sh) runs database schema verification, seeds trajectories if `AUTO_SEED=true`, spawns the worker in the background, and boots `uvicorn`:

```bash
#!/usr/bin/env bash
python -m backend.worker &
exec uvicorn backend.main:app --host 0.0.0.0 --port "${PORT:-8000}"
```

### Railway Environment Variables
Configure the following in your Railway service settings:

| Variable | Recommended Value | Purpose |
| :--- | :--- | :--- |
| `DATABASE_URL` | `postgresql://...` | Connection URI to Supabase PostgreSQL. |
| `ALLOWED_ORIGINS` | `https://agentflow.vercel.app,http://localhost:3000` | Whitelisted CORS origins for the frontend. |
| `ALLOW_VERCEL_PREVIEWS` | `true` | Permits regex matching for Vercel preview deploys (`https://.*\.vercel\.app`). |
| `OPENAI_API_KEY` | `sk-proj-...` *(Optional)* | For `text-embedding-3-small`. Uses deterministic mock embedder if omitted. |
| `START_WORKER` | `true` | Runs queue processor thread inside the web container (or run worker service). |
| `AUTO_SEED` | `false` *(or `true` for first deploy)* | Automatically runs `seed_playbooks.py` on container startup. |

### Health Check Configuration
- In Railway Service Settings, configure **Healthcheck Path**:
  ```text
  /healthz
  ```
- Railway will continuously ping `GET /healthz`. If the database pool drops or the container crashes, Railway will restart the container automatically.

---

## 3. Vercel (Next.js Frontend Deployment)

The frontend is located in the [`frontend/`](file:///Users/adithyasaineeli/Desktop/Agentflow/frontend) directory.

### Step 1: Import Repository
1. In Vercel, click **Add New Project** and select the AgentFlow repository.
2. Set **Root Directory** to `frontend`.
3. Framework Preset: **Next.js** (detected automatically).

### Step 2: Environment Variables
Configure the following environment variable in the Vercel dashboard:

| Variable | Value | Purpose |
| :--- | :--- | :--- |
| `NEXT_PUBLIC_API_URL` | `https://agentflow-backend-production.up.railway.app/api/v1` | Public REST API base URL consumed by React components. |

### Step 3: Deploy
Click **Deploy**. Next.js will build all static pages and App Router dynamic endpoints.

---

## 4. Production Verification Runbook

Run these automated verification checks against your deployed production endpoints:

### 1. Deep Health Probe (`/healthz`)
Verify that the database session pool and embedding service are healthy:

```bash
curl -i -X GET "https://your-backend.up.railway.app/healthz"
```
**Expected Response (`200 OK`)**:
```json
{
  "status": "healthy",
  "database": "connected",
  "embedding_service": "active",
  "timestamp": "2026-10-16T02:35:00.123456+00:00"
}
```

---

### 2. CORS Preflight Validation
Test that production and preview domains receive proper CORS access headers, while unauthorized domains are rejected:

```bash
# Test 1: Production Domain (Should Return 200 OK + CORS Header)
curl -i -X OPTIONS "https://your-backend.up.railway.app/api/v1/trajectories" \
  -H "Origin: https://agentflow.vercel.app" \
  -H "Access-Control-Request-Method: GET"

# Test 2: Vercel Preview Domain (Should Return 200 OK + CORS Header)
curl -i -X OPTIONS "https://your-backend.up.railway.app/api/v1/trajectories" \
  -H "Origin: https://agentflow-git-feature.vercel.app" \
  -H "Access-Control-Request-Method: GET"

# Test 3: Unauthorized Domain (Should Return 400 Bad Request / No CORS Header)
curl -i -X OPTIONS "https://your-backend.up.railway.app/api/v1/trajectories" \
  -H "Origin: https://malicious-site.com" \
  -H "Access-Control-Request-Method: GET"
```

---

### 3. Rate Limiting Defense Verification
Send 35 requests in rapid sequence to verify that `slowapi` triggers HTTP 429 when exceeding the 30/min limit on search:

```bash
for i in {1..35}; do
  echo -n "Request $i: "
  curl -s -o /dev/null -w "%{http_code}\n" -X POST "https://your-backend.up.railway.app/api/v1/trajectories/search" \
    -H "Content-Type: application/json" \
    -d '{"query": "probe"}'
done
```
**Expected Output**:
```text
Request 1..30: 200
Request 31..35: 429
```

---

### 4. Payload Boundary Rejection
Verify that abusive or oversized payloads are rejected with HTTP 422:

```bash
# Attempt to send an error_trace exceeding 20,000 characters
python3 -c "
import requests
res = requests.post(
    'https://your-backend.up.railway.app/api/v1/trajectories',
    headers={'Authorization': 'Bearer test-token'},
    json={'title': 'Test Cap', 'task_goal': 'Test Goal', 'error_trace': 'X' * 20001, 'playbook': {}}
)
print('Status:', res.status_code)
assert res.status_code == 422
print('Payload cap test PASSED.')
"
```

---

### 5. Provision Machine Agent Credentials
Create an agent token for your production runners:

```bash
python -m backend.scripts.create_agent --name "Railway Production Worker"
```

Use the printed token to configure Cursor or Claude Desktop as described in [Agent Integration Guide](AGENT_INTEGRATION.md).
