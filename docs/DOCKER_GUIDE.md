# PawGuard Docker & Container Deployment Guide

This guide explains how to run the PawGuard Backend, Worker, PostgreSQL database, Redis cache, and MinIO storage emulator using Docker and Docker Compose with the latest production code.

---

## 1. Quick Start with Docker Compose (Recommended)

To launch the complete local PawGuard environment with PostgreSQL, Redis, MinIO, API Service, and ARQ Background Worker in a single command:

```bash
docker compose up --build
```

### What Happens Automatically:
1. **PostgreSQL 16**: Starts database on `5432` with health checks.
2. **Redis 7**: Starts caching & task queue broker on `6379`.
3. **MinIO (S3 Emulator)**: Starts S3 object store on `9000` (API) and `9001` (Admin Console).
4. **PawGuard API**: Runs Alembic migrations (`alembic upgrade head`), seeds initial system roles & permissions, and starts Uvicorn server on `http://localhost:8000`.
5. **PawGuard Worker**: Starts background ARQ job worker listening to Redis.

---

## 2. Running Individual Containers with Docker

If you want to build and run **only** the PawGuard API container (pointing to an external database or RDS):

### Step 1: Build the Image
```bash
docker build -t pawguard-backend:latest .
```

### Step 2: Run the Container
```bash
docker run -d \
  --name pawguard-api \
  -p 8000:8000 \
  -e DATABASE_URL="postgresql+asyncpg://user:password@rds-host:5432/pawguard" \
  -e REDIS_URL="redis://redis-host:6379/0" \
  -e JWT_SECRET_KEY="your-production-jwt-secret-min-32-chars" \
  pawguard-backend:latest
```

---

## 3. Useful Docker Commands

| Action | Command |
|---|---|
| **Start in background (detached)** | `docker compose up -d` |
| **Stop all services** | `docker compose down` |
| **Stop and remove volumes** | `docker compose down -v` |
| **View live logs** | `docker compose logs -f api` |
| **Rebuild without cache** | `docker compose build --no-cache` |
| **Run migrations manually inside container** | `docker compose exec api alembic upgrade head` |
| **Check container health** | `docker compose ps` |

---

## 4. Health Check & API Verification

Once started, test the API health endpoint:

```bash
curl http://localhost:8000/health
```

Expected Response:
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "database": "connected",
  "redis": "connected"
}
```

Open API Swagger Documentation is accessible at:
- `http://localhost:8000/docs`
- `http://localhost:8000/redoc`

---

## 5. Render / Cloud Container Deployment

When deploying to **Render**, **AWS ECS/App Runner**, **GCP Cloud Run**, or **DigitalOcean App Platform**:
- Use the repository root `Dockerfile`.
- Set Environment Variables (`DATABASE_URL`, `REDIS_URL`, `JWT_SECRET_KEY`, `S3_BUCKET_NAME`, etc.) in your provider dashboard.
- The `docker-entrypoint.sh` automatically runs `alembic upgrade head` before starting the web worker, ensuring zero manual database setup is required.
