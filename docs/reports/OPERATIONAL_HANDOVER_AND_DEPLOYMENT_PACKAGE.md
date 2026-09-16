# PawGuard Platform — Operational Handover & Deployment Package

**Document ID:** PG-PKG-HANDOVER-2026-v1.0  
**Target Audience:** Client DevOps Engineers, Cloud Infrastructure Leads, & IT Operations  
**Classification:** OFFICIAL CONTRACTUAL HANDOVER PACKAGE  
**PaaS / Cloud Architecture:** Render PaaS / Docker / PostgreSQL 16 (PostGIS) / Redis 7.2  

---

## 1. Package Overview & Handover Components

This document delivers the operational architecture, deployment manifests, environment variables, administrator credentials, and database migration tooling for the PawGuard Backend.

### 1.1 Source Repositories & Artifacts

| Component | Location / File Path | Description |
| :--- | :--- | :--- |
| **Backend Core Engine** | `src/pawguard/` | FastAPI Async Application, 26 Domain Modules |
| **Database Migrations** | `alembic/versions/` | Version-controlled SQLAlchemy database schema revisions |
| **Docker Configuration** | `Dockerfile`, `docker-compose.yml` | Multi-stage production container definitions |
| **Cloud Deployment** | `render.yaml` | Infrastructure-as-Code service deployment manifest |
| **API Specifications** | `openapi.json`, `PawGuard.postman_collection.json` | Complete Swagger/OpenAPI spec & Postman collection |

---

## 2. Production Environment Configuration

All backend parameters are loaded from environment variables using Pydantic Settings (`pawguard.core.config`).

### 2.1 Critical Configuration Template (`.env`)

```ini
# --- Application Environment ---
ENVIRONMENT=production
DEBUG=false
PROJECT_NAME="PawGuard Backend"
API_V1_STR=/api/v1
SECRET_KEY=<GENERATE_SECURE_64_CHAR_HEX_SECRET>

# --- Database Connectivity (PostgreSQL 16 with PostGIS) ---
DATABASE_URL=postgresql+asyncpg://pawguard_user:<SECURE_PASSWORD>@db.pawguard.internal:5432/pawguard_prod
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10

# --- Redis Cache & Background Queue ---
REDIS_URL=redis://default:<REDIS_PASSWORD>@redis.pawguard.internal:6379/0

# --- JWT & Security Tokens ---
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7
MFA_MANDATORY_FOR_ADMINS=true

# --- Storage & S3 Presigned Uploads ---
STORAGE_BACKEND=s3
S3_BUCKET_NAME=pawguard-production-assets
AWS_ACCESS_KEY_ID=<AWS_ACCESS_KEY>
AWS_SECRET_ACCESS_KEY=<AWS_SECRET_KEY>
AWS_REGION=ap-south-1

# --- Notifications & Outbox ---
FIREBASE_CREDENTIALS_PATH=/secrets/firebase-admin.json
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USER=apikey
SMTP_PASSWORD=<SENDGRID_API_KEY>
EMAILS_FROM_EMAIL=notifications@pawguard.org
EMAILS_FROM_NAME="PawGuard Emergency Rescue"
```

---

## 3. Deployment & Startup Execution

### 3.1 Dockerized Production Startup
```bash
# Build production image
docker build -t pawguard-backend:latest .

# Run container stack with PostgreSQL and Redis
docker-compose up -d
```

### 3.2 Database Migration & Schema Seeding
```bash
# Run latest database migrations
alembic upgrade head

# Seed initial 15 operational roles and master facility records
python scripts/seed_roles.py
```

---

## 4. Standard Operational User Credentials (Seeded Handover)

All standard seeded accounts are provisioned with initial default credentials (prompting immediate password update upon first sign-in).

| Role ID | Role Code | Seeded Email Address | Domain Module Access |
| :---: | :--- | :--- | :--- |
| **1** | `super_admin` | `super.admin@pawguard.com` | Global IAM, Audit, Config |
| **2** | `rescue_centre_admin`| `rescue.admin@pawguard.com` | Centre Ops, Staff, Fleet |
| **3** | `rescue_coordinator` | `rescue.coordinator@pawguard.com`| Emergency Dispatch, Agents |
| **4** | `rescue_agent` | `rescue.agent@pawguard.com` | Field Rescue Response |
| **5** | `veterinarian` | `vet@pawguard.com` | Medical, RX, Vaccinations |
| **6** | `shelter_manager` | `shelter.manager@pawguard.com` | Kennels, Dogs, Inventory |
| **7** | `adoption_coordinator`| `adoption.coordinator@pawguard.com`| Applications, Contracts |
| **8** | `foster_coordinator` | `foster.coordinator@pawguard.com` | Foster Homes, Placements |
| **9** | `volunteer_coordinator`| `volunteer.coordinator@pawguard.com`| Volunteer Roster & Shifts |
| **10** | `inventory_manager` | `inventory.manager@pawguard.com` | Supplies & Stock Control |
| **11** | `finance_user` | `finance.user@pawguard.com` | Donations, 80G, Expenses |
| **12** | `volunteer` | `volunteer@pawguard.com` | Shifts, Self Hours Log |
| **13** | `foster_family` | `foster.family@pawguard.com` | Assigned Foster Dog Logs |
| **14** | `donor` | `donor@pawguard.com` | Donation Receipts |
| **15** | `general_public` | `public.user@pawguard.com` | Adoptable Dogs & Reports |

---
*End of Operational Handover & Deployment Package.*
