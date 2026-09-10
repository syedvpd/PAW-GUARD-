# PawGuard — AWS RDS PostgreSQL & S3 Migration Runbook

This runbook provides the definitive, step-by-step guide and exact CLI commands to provision, migrate, seed, and verify a fresh **AWS RDS PostgreSQL** database and **AWS S3** bucket for the PawGuard platform without errors.

---

## Table of Contents
1. [Prerequisites & AWS Resource Provisioning](#1-prerequisites--aws-resource-provisioning)
   - [AWS RDS PostgreSQL Setup](#aws-rds-postgresql-setup)
   - [AWS S3 Bucket & IAM Credentials Setup](#aws-s3-bucket--iam-credentials-setup)
2. [Connection String & URL Encoding Rules](#2-connection-string--url-encoding-rules)
3. [Environment Configuration Reference](#3-environment-configuration-reference)
4. [Step-by-Step Migration & Seeding Commands](#4-step-by-step-migration--seeding-commands)
   - [Step 1: Test Database Connectivity](#step-1-test-database-connectivity)
   - [Step 2: Run Alembic Schema Migrations](#step-2-run-alembic-schema-migrations)
   - [Step 3: Reconcile 15 Roles, Granular Permissions & Test Accounts](#step-3-reconcile-15-roles-granular-permissions--test-accounts)
   - [Step 4: Verify Zero Business Data Integrity](#step-4-verify-zero-business-data-integrity)
   - [Step 5: Verify AWS S3 Bucket Connectivity](#step-5-verify-aws-s3-bucket-connectivity)
   - [Step 6: Execute Authentication Smoke Test](#step-6-execute-authentication-smoke-test)
5. [Automated One-Click Script Method](#5-automated-one-click-script-method)
6. [Common Errors & Troubleshooting](#6-common-errors--troubleshooting)

---

## 1. Prerequisites & AWS Resource Provisioning

### AWS RDS PostgreSQL Setup
1. **Engine**: PostgreSQL 16 or 17.
2. **Instance Class**: `db.t4g.micro` / `db.t4g.small` (Staging) or `db.m6g.large`+ (Production).
3. **Storage**: GP3 SSD (20 GB+ minimum, auto-scaling enabled).
4. **VPC & Security Groups**:
   - Ensure the Security Group allows inbound traffic on port `5432` from your deployment runner (Render outbound IPs, EC2, or developer IP).
5. **Database Name**: `postgres` (or `pawguard`).
6. **Master Username**: `postgres` (or `pawguard_admin`).

### AWS S3 Bucket & IAM Credentials Setup
1. **Bucket Name**: `pawguard-media` (or your chosen environment bucket name).
2. **Region**: e.g., `ap-southeast-1` or `us-east-1`.
3. **Block Public Access**: Keep enabled or configure according to public asset CDN rules.
4. **CORS Policy** (Required for Direct Mobile/Web Uploads):
   ```json
   [
     {
       "AllowedHeaders": ["*"],
       "AllowedMethods": ["GET", "PUT", "POST", "HEAD"],
       "AllowedOrigins": ["*"],
       "ExposeHeaders": ["ETag"]
     }
   ]
   ```
5. **IAM User / Credentials**:
   Create an IAM user with `AmazonS3FullAccess` (or scoped policy to `pawguard-media/*`) and generate an **Access Key ID** and **Secret Access Key**.

---

## 2. Connection String & URL Encoding Rules

> [!IMPORTANT]
> If your database password contains special characters like `@`, `:`, `/`, `?`, `#`, or `%`, you **MUST** URL-encode them. Otherwise, database drivers will parse the password as a host delimiter and fail with `connection refused` or `invalid port` errors.

### Common Special Character Encodings:
| Character | Encoded Value |
|---|---|
| `@` | `%40` |
| `:` | `%3A` |
| `/` | `%2F` |
| `#` | `%23` |
| `$` | `%24` |
| `%` | `%25` |

### Connection String Formats:
* **AsyncPG (FastAPI Backend & Alembic)**:
  ```text
  postgresql+asyncpg://<USER>:<ENCODED_PASSWORD>@<RDS_ENDPOINT>:5432/<DB_NAME>?ssl=require
  ```
  *Example*:
  ```text
  postgresql+asyncpg://postgres:MySecureP%40ss2026@pawguard-rds.c12345678.ap-southeast-1.rds.amazonaws.com:5432/postgres?ssl=require
  ```

---

## 3. Environment Configuration Reference

When deploying to Render, AWS ECS, or local development, set these environment variables:

```env
# Database Settings
DATABASE_URL=postgresql+asyncpg://<USER>:<ENCODED_PASSWORD>@<RDS_ENDPOINT>:5432/<DB_NAME>?ssl=require
DATABASE_POOL_SIZE=50
DATABASE_MAX_OVERFLOW=25
DATABASE_POOL_TIMEOUT=30
DATABASE_POOL_RECYCLE=1800

# AWS S3 Storage Settings
S3_ENDPOINT_URL=https://s3.<REGION>.amazonaws.com
S3_REGION=<REGION>
S3_ACCESS_KEY_ID=<YOUR_AWS_ACCESS_KEY_ID>
S3_SECRET_ACCESS_KEY=<YOUR_AWS_SECRET_ACCESS_KEY>
S3_BUCKET_NAME=pawguard-media
```

---

## 4. Step-by-Step Migration & Seeding Commands

Run all commands from the repository root directory.

### Step 1: Test Database Connectivity
Verify that your terminal or runner can reach the RDS instance:

```powershell
# Windows PowerShell
$env:DATABASE_URL="postgresql+asyncpg://<USER>:<ENCODED_PASSWORD>@<RDS_ENDPOINT>:5432/<DB_NAME>?ssl=require"
.venv\Scripts\python.exe -c "
import asyncio, asyncpg
async def test():
    # Strip +asyncpg dialect for raw probe
    url = '$env:DATABASE_URL'.replace('+asyncpg', '')
    conn = await asyncpg.connect(url, statement_cache_size=0)
    print('Connected successfully:', await conn.fetchval('SELECT version()'))
    await conn.close()
asyncio.run(test())
"
```

```bash
# Linux / macOS / Bash
export DATABASE_URL="postgresql+asyncpg://<USER>:<ENCODED_PASSWORD>@<RDS_ENDPOINT>:5432/<DB_NAME>?ssl=require"
python -c "
import os, asyncio, asyncpg
async def test():
    url = os.environ['DATABASE_URL'].replace('+asyncpg', '')
    conn = await asyncpg.connect(url, statement_cache_size=0)
    print('Connected successfully:', await conn.fetchval('SELECT version()'))
    await conn.close()
asyncio.run(test())
"
```

---

### Step 2: Run Alembic Schema Migrations
Applies all 98+ migrations from `initial` to the current `head`, creating all 100+ tables, indexes, and constraints.

```powershell
# Windows PowerShell
$env:DATABASE_URL="postgresql+asyncpg://<USER>:<ENCODED_PASSWORD>@<RDS_ENDPOINT>:5432/<DB_NAME>?ssl=require"
.venv\Scripts\alembic.exe upgrade head
```

```bash
# Linux / macOS / Bash
export DATABASE_URL="postgresql+asyncpg://<USER>:<ENCODED_PASSWORD>@<RDS_ENDPOINT>:5432/<DB_NAME>?ssl=require"
uv run alembic upgrade head
```

---

### Step 3: Reconcile 15 Roles, Granular Permissions & Test Accounts
Populates the 15 system roles, links 330+ permissions, and creates all 15 standard verified test accounts with the shared password (`PawGuard@2026`):

```powershell
# Windows PowerShell
$env:DATABASE_URL="postgresql+asyncpg://<USER>:<ENCODED_PASSWORD>@<RDS_ENDPOINT>:5432/<DB_NAME>?ssl=require"
.venv\Scripts\python.exe scripts\setup_clean_supabase_environment.py
```

```bash
# Linux / macOS / Bash
export DATABASE_URL="postgresql+asyncpg://<USER>:<ENCODED_PASSWORD>@<RDS_ENDPOINT>:5432/<DB_NAME>?ssl=require"
python scripts/setup_clean_supabase_environment.py
```

---

### Step 4: Verify Zero Business Data Integrity
Verify that no legacy records exist in operational business tables:

```powershell
# Windows PowerShell
.venv\Scripts\python.exe -c "
import asyncio, os, sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / 'src'))
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import text

async def check_empty():
    engine = create_async_engine(os.environ['DATABASE_URL'], connect_args={'statement_cache_size': 0})
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    tables = [
        'dog_profiles', 'rescue_requests', 'rescue_dispatches', 'shelter_facilities',
        'kennels', 'adoption_applications', 'foster_placements', 'donations',
        'clinical_exams', 'medical_treatments', 'vaccination_records', 'prescriptions',
        'inventory_items', 'requisition_orders', 'financial_transactions', 'grievance_tickets', 'notifications'
    ]
    async with session_factory() as session:
        for t in tables:
            cnt = (await session.execute(text(f'SELECT COUNT(*) FROM {t}'))).scalar()
            assert cnt == 0, f'Table {t} is NOT empty (count={cnt})'
            print(f'  [OK] {t}: 0 rows')
    await engine.dispose()
    print('ALL BUSINESS TABLES 100% EMPTY')

asyncio.run(check_empty())
"
```

---

### Step 5: Verify AWS S3 Bucket Connectivity
Test AWS S3 upload, read, and delete permissions:

```powershell
# Windows PowerShell
.venv\Scripts\python.exe -c "
import boto3, os
from botocore.client import Config

s3 = boto3.client(
    's3',
    endpoint_url=os.environ.get('S3_ENDPOINT_URL'),
    aws_access_key_id=os.environ['S3_ACCESS_KEY_ID'],
    aws_secret_access_key=os.environ['S3_SECRET_ACCESS_KEY'],
    region_name=os.environ.get('S3_REGION', 'ap-southeast-1'),
    config=Config(signature_version='s3v4')
)
bucket = os.environ.get('S3_BUCKET_NAME', 'pawguard-media')
s3.put_object(Bucket=bucket, Key='healthcheck/probe.txt', Body=b'AWS S3 Storage Verified')
res = s3.get_object(Bucket=bucket, Key='healthcheck/probe.txt')
print('Read probe:', res['Body'].read().decode())
s3.delete_object(Bucket=bucket, Key='healthcheck/probe.txt')
print('AWS S3 Healthcheck Passed!')
"
```

---

### Step 6: Execute Authentication Smoke Test
Verify that all 15 seeded test accounts can authenticate and receive valid RS256 JWT tokens:

```powershell
# Windows PowerShell
.venv\Scripts\python.exe -c "
import asyncio, os, sys, uuid
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / 'src'))

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from pawguard.modules.auth.models import User
from pawguard.core.security import verify_password, create_access_token

async def test_tokens():
    engine = create_async_engine(os.environ['DATABASE_URL'], connect_args={'statement_cache_size': 0})
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    
    accounts = [
        'super.admin@pawguard.com', 'rescue.admin@pawguard.com', 'rescue.coordinator@pawguard.com',
        'rescue.agent@pawguard.com', 'vet@pawguard.com', 'shelter.manager@pawguard.com',
        'adoption.coordinator@pawguard.com', 'foster.coordinator@pawguard.com', 'volunteer.coordinator@pawguard.com',
        'inventory.manager@pawguard.com', 'finance.user@pawguard.com', 'volunteer@pawguard.com',
        'foster.family@pawguard.com', 'donor@pawguard.com', 'public.user@pawguard.com'
    ]
    
    async with session_factory() as session:
        for email in accounts:
            user = (await session.execute(select(User).options(selectinload(User.roles)).where(User.email == email))).scalar_one()
            assert verify_password('PawGuard@2026', user.hashed_password)
            roles = [r.name for r in user.roles]
            token = create_access_token(user_id=user.id, session_id=uuid.uuid4(), roles=roles)
            print(f'  [AUTH OK] {email:35s} | Role: {str(roles):25s} | Token: {token[:20]}...')

asyncio.run(test_tokens())
"
```

---

## 5. Automated One-Click Script Method

You can perform the entire migration and seeding in a single command using [`scripts/setup_clean_supabase_environment.py`](file:///C:/Users/win10/Downloads/PAW-GUARD-/scripts/setup_clean_supabase_environment.py):

1. Set your environment variables:
   ```env
   DATABASE_URL=postgresql+asyncpg://<USER>:<ENCODED_PASSWORD>@<RDS_ENDPOINT>:5432/<DB_NAME>?ssl=require
   S3_ENDPOINT_URL=https://s3.<REGION>.amazonaws.com
   S3_REGION=<REGION>
   S3_ACCESS_KEY_ID=<AWS_KEY_ID>
   S3_SECRET_ACCESS_KEY=<AWS_SECRET_KEY>
   S3_BUCKET_NAME=pawguard-media
   ```
2. Run:
   ```powershell
   # Step A: Apply schema DDL
   .venv\Scripts\alembic.exe upgrade head

   # Step B: Seed roles, permissions, accounts & S3 bucket
   .venv\Scripts\python.exe scripts\setup_clean_supabase_environment.py
   ```

---

## 6. Common Errors & Troubleshooting

### 1. `asyncpg.exceptions.InvalidPasswordError` / `ConnectionRefusedError`
* **Cause**: Password contains special characters (`@`, `#`, `$`) that were not URL-encoded.
* **Fix**: Encode `@` as `%40` in the `DATABASE_URL`.

### 2. `asyncpg.exceptions.UndefinedTableError: relation "xyz" does not exist`
* **Cause**: Attempting to run queries before running `alembic upgrade head`.
* **Fix**: Always execute `alembic upgrade head` first to build the complete table schema.

### 3. `asyncpg.exceptions.InterfaceError: cannot perform operation: another operation is in progress` / PgBouncer prepared statement error
* **Cause**: Poolers (like AWS RDS Proxy or Supabase PgBouncer) do not support statement caching.
* **Fix**: Ensure `connect_args={"statement_cache_size": 0}` is present in SQLAlchemy engine settings (already configured in `src/pawguard/db/session.py`).

### 4. `botocore.exceptions.ClientError: 403 Forbidden` on S3
* **Cause**: IAM user does not have permission to `s3:ListBucket`, `s3:PutObject`, `s3:GetObject`, or `s3:DeleteObject`.
* **Fix**: Attach `AmazonS3FullAccess` policy or update the bucket access policy in the AWS S3 Console.

### 5. `Multiple heads are present in repository`
* **Cause**: Git merge conflicts created competing Alembic head revisions.
* **Fix**: Run `alembic merge -m "merge_heads" <rev1> <rev2>` or ensure you are on the linear `b3c4d5e6f7a9` head.
