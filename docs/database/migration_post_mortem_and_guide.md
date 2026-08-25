# PawGuard Database & Storage Migration Technical Guide

This guide details the exact process followed for the migration to the new Supabase instance, explaining the scripts, methodologies, challenges, and providing a step-by-step blueprint for future migrations (e.g., to AWS RDS and S3).

---

## 📁 1. The Migration Post-Mortem

### The Challenges Faced
1. **Foreign Key Deadlocks & Constraints**: 
   - *Problem*: Standard SQL inserts fail if parent tables aren't populated before child tables.
   - *Solution*: Enabled `session_replication_role = 'replica'` in PostgreSQL to bypass constraint checks during bulk sync, allowing concurrent data insertion.
2. **PgBouncer Port Restrictions (Direct vs Pooler)**:
   - *Problem*: DDL migrations and sequence alignments fail on Supabase Transaction Pooler port `6543`.
   - *Solution*: Used direct connection port `5432` for all schema alterations, sequence resets, and large bulk transfers, while using transaction port `6543` for the live FastAPI app.
3. **Integer Autoincrement PK Sequences**:
   - *Problem*: Copying data directly doesn't update PostgreSQL sequences. Future inserts result in `UniqueViolationError` primary key collisions.
   - *Solution*: Executed `fix_sequences.py` to reset sequence counters (`setval`) to the current max ID.
4. **Transient Network Connection Resets**:
   - *Problem*: Bulk transferring thousands of rows or large high-res image files can cause socket disconnects (`wsarecv` / connection resets).
   - *Solution*: Batch chunked database inserts into sizes of 500 rows and wrote a stateful S3 verification/retry script (`retry_s3.py`) to catch missed files.

### ⏱️ Total Time & Sync Statistics
- **Schema Validation & DDL Creation**: ~3 minutes
- **Database Bulk Transfer (22,254 Rows across 106 tables)**: ~8 minutes
- **Media Object Transfer (190 files / 7 directories)**: ~6 minutes
- **Total Migration Window**: **~17 minutes**

---

## 🧬 2. Seeding vs. Migration

- **Seeding**: Creating *mock*, synthetic, or initial default settings data (e.g., admin users, default settings, lookup roles) in an empty database so the app can start up.
- **Migration (`sync_fast.py` / `sync_all_supabase_storage_s3.py`)**: Moving **100% of real production data** (existing user accounts, real audit logs, uploaded medical PDFs, rescue records) from an old system to a new system with zero row loss.

---

## 🛠️ 3. Execution Scripts Directory
The following migration utility scripts are saved and ready in your workspace:

1. **Schema DDL Creator**: [`create_schema.py`](file:///C:/Users/win10/.gemini/antigravity-ide/brain/8fc243b1-166f-4e96-ae87-a0c60839515a/scratch/create_schema.py)
   - Generates tables, foreign keys, and indexes on a fresh target database.
2. **Bulk Data Migrator**: [`sync_fast.py`](file:///C:/Users/win10/.gemini/antigravity-ide/brain/8fc243b1-166f-4e96-ae87-a0c60839515a/scratch/sync_fast.py)
   - Cleans old target tables and streams database rows in chunked transactions under replica role.
3. **Autoincrement Fixer**: [`fix_sequences.py`](file:///C:/Users/win10/.gemini/antigravity-ide/brain/8fc243b1-166f-4e96-ae87-a0c60839515a/scratch/fix_sequences.py)
   - Re-aligns integer primary key sequences to prevent insertion collisions.
4. **Audit Verifier**: [`verify_sync.py`](file:///C:/Users/win10/.gemini/antigravity-ide/brain/8fc243b1-166f-4e96-ae87-a0c60839515a/scratch/verify_sync.py)
   - Queries source and target databases side-by-side to verify exact row counts.
5. **Storage Synchronizer**: [`sync_all_supabase_storage_s3.py`](file:///C:/Users/win10/.gemini/antigravity-ide/brain/8fc243b1-166f-4e96-ae87-a0c60839515a/scratch/sync_all_supabase_storage_s3.py)
   - Copies files across all directories using the S3 API.

---

## 🗺️ 4. Future Blueprint: Migrating to AWS RDS & S3

If you plan to migrate to AWS in the future, follow this step-by-step blueprint to ensure zero data loss.

### Part A: AWS RDS (PostgreSQL Database Migration)
1. **Create target database**: Provision a PostgreSQL instance on AWS RDS.
2. **Extract Schema**: Run DDL schemas on the fresh RDS instance:
   ```bash
   uv run alembic upgrade head
   ```
3. **Run sync script**: Update the target URL in `scratch/sync_fast.py` to point to your new RDS connection string:
   ```env
   TARGET_DATABASE_URL=postgresql+asyncpg://<username>:<password>@<rds-endpoint>:5432/<dbname>
   ```
4. **Run sync script**:
   ```bash
   .venv\Scripts\python.exe scratch/sync_fast.py
   ```
5. **Reset Sequences**:
   ```bash
   .venv\Scripts\python.exe scratch/fix_sequences.py
   ```
6. **Verify Row Counts**:
   ```bash
   .venv\Scripts\python.exe scratch/verify_sync.py
   ```

### Part B: AWS S3 (Storage Migration)
1. **Create Bucket**: Go to AWS S3 Console -> Click **Create Bucket** -> name it `pawguard-media`.
2. **Storage Policies**: Enable public read permissions or set bucket policy so URLs are readable by your web app.
3. **Configure connection settings**: Edit target settings in `sync_all_supabase_storage_s3.py`:
   ```python
   NEW_ENDPOINT_URL = "https://s3.<region>.amazonaws.com"
   NEW_ACCESS_KEY_ID = "<YOUR_AWS_ACCESS_KEY>"
   NEW_SECRET_ACCESS_KEY = "<YOUR_AWS_SECRET_KEY>"
   ```
4. **Upload files**: Run the upload script to push the backup local folder directly into AWS S3.

---

## ⚡ 5. Best Practices: Manual vs. Scripted
- **Manual (e.g. `pg_dump` & `pg_restore`)**: Very fast for homogeneous servers, but can fail when target database schema configurations, Postgres major versions, or user permissions differ slightly.
- **Scripted (e.g. `sync_fast.py`) [RECOMMENDED]**:
  - Handles table schema column intersections (allows database schema versions to differ slightly without breaking).
  - Skips corrupted columns safely.
  - Safe, predictable, chunk-by-chunk transaction logging.
