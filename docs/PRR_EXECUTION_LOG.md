# PawGuard Backend — PRR Forensic Remediation Execution Log

**Initial Date**: 2026-09-15  
**Document**: `docs/PRR_EXECUTION_LOG.md`  
**Standard**: Non-negotiable forensic re-audit standard (RULE 1 - RULE 5)

---

## Phase 0 — Baseline Repository State

### 1. Environment & Version Baseline

| Component | Reported / Detected Value | Command Executed | Status / Notes |
| :--- | :--- | :--- | :--- |
| **Git Branch** | `main` | `git status` | Clean tracking `origin/main` |
| **Python** | `Python 3.14.5` / `3.13` | `python --version` | Verified |
| **PostgreSQL** | Local PostgreSQL 16 on port 5432 (`pawguard-postgres`) | `alembic upgrade head` | Verified with live migrations |
| **Redis** | Local Redis 7 on port 6379 (`pawguard-redis`) | Redis client connectivity | Verified |
| **Alembic Head** | `b7c8d9e0f1a2` | `.venv\Scripts\alembic.exe heads` | Single head verified, upgraded cleanly |
| **Static Linter** | 0 errors | `.venv\Scripts\ruff.exe check src/ tests/` | `All checks passed!` |
| **Code Formatter** | 0 errors | `.venv\Scripts\ruff.exe format --check src/ tests/` | `388 files already formatted` |
| **Type Checker** | 0 errors | `.venv\Scripts\mypy.exe src/` | `Success: no issues found in 204 source files` |
| **Unit Tests** | 1,335 passed, 0 failed | `.venv\Scripts\pytest.exe tests/unit/ -q` | `1335 passed, 122 warnings in 95.36s` |
| **Regression Tests**| 5 passed, 0 failed | `.venv\Scripts\pytest.exe tests/regression/ -q` | `5 passed, 1 warning in 12.25s` |

---

## Remediations Executed & Verified

### P0 Findings (Critical / Blocker)
1. **P0-1 & P1-1: Payment Webhook Concurrency & Outer-Join Row Locking**:
   - Registered `/donations/webhook/razorpay` in `FINANCIAL_IDEMPOTENT_PATHS` (`src/pawguard/core/idempotency.py`).
   - Replaced unbounded outer-join `with_for_update()` in `DonationRepository` with targeted `with_for_update(of=Donation)` to prevent Postgres locking failures on nullable relations.
   - Verified with 4 concurrency tests in `test_donation_webhook_concurrency.py`.
2. **P0-3 & P1-3: Kennel Capacity & Adoption Exclusivity**:
   - Multi-capacity kennels locked cleanly with row-level `FOR UPDATE`.
   - Changed `uq_dog_profiles_kennel_single` to lookup index `ix_dog_profiles_kennel_id` so multi-capacity kennels can hold multiple dogs.
   - Reconciled ORM `__table_args__` and partial unique index on `adoption_applications` for active dog lock states.
3. **P0-4: PRR Acceptance Regressions**:
   - All 5 regression tests in `tests/regression/test_prr_acceptance.py` pass against live database.

### P1 Findings (High Priority)
1. **P1-5: Facility IDOR Enforcement**:
   - Added `assert_facility_access` across shelter service (`create_section`, `create_kennel`, `assign_dog_to_kennel`, `update_kennel_sanitation`, `log_kennel_cleaning`, `request_transfer`, `get_transfer`, `list_transfers`).
   - Scoped non-admin roles to their assigned `managed_facility_id`.
2. **P1-7: MFA Defaults**:
   - Enforced `mfa_mandatory_for_admins: bool = True` in `src/pawguard/core/config.py`, `.env.example`, and `render.yaml`.
3. **P1-11: Medical Mock Removal**:
   - Removed hardcoded placeholder dog/vet mock names ("Bella (Labrador)", "Dr. Sarah Jenkins") in `src/pawguard/modules/medical/router.py`. Real DB queries with 404 validation enforced.
4. **P1-13: Post-Rescue Feedback Survey Worker**:
   - Implemented `send_post_rescue_feedback_surveys` job in `scheduled_jobs.py` and registered with ARQ worker cron.
5. **P1-14: Quarantine Enforcement**:
   - Adoptability blocked until `is_quarantine_passed` is verified by authorized veterinary roles.
   - Unquarantined dogs blocked from assignment to adoption sections and clinic transfers.
6. **P1-19: Secret Scrub**:
   - Scrubbed credentials from `.env.example`.
7. **P1-20: Alembic Hack Removal**:
   - Removed SQL rewrite hack from `alembic/env.py`.
   - Cleaned index definitions in `f61eaab29ac9`.
8. **P1-22 & Phase 15: Production Alerting**:
   - Configured Prometheus alert rules (`monitoring/prometheus/alert.rules.yml` and `monitoring/prometheus.yml`) for 5xx rate, latency p95, DB down, Redis down, worker errors, kennel capacity.

### P2 Findings (Medium Priority)
1. **P2-1: Money Fields Decimal Typing**:
   - Upgraded `monthly_amount`, `amount`, `target_amount` in donation models and schemas to `Decimal`.
2. **P2-2: Finance Expense Foreign Keys**:
   - Added `rescue_case_id` and `shelter_facility_id` to `FinanceExpense` model and schemas, backed by Alembic migration `b7c8d9e0f1a2`.
3. **P2-3: Foster-to-Adopt Sibling Rejection**:
   - Automatically auto-rejects active sibling applications when a foster placement is converted to adoption, notifying applicants.
4. **P2-5: Donor PII Masking**:
   - Implemented `mask_pan` and `mask_address` in `src/pawguard/core/pii.py`, applied in `_mask_donor_pii`.
5. **P2-8: Redis Pipeline Optimization**:
   - Replaced N*2 serial Redis calls in `get_agent_availability` with batch `geopos` and Redis `pipeline()`.
6. **P2-10: Lost & Found Match Audit Trail**:
   - Recorded reviewer user ID and audit log in direct match resolutions.
7. **P2-17: Medical Intake Examination Check Constraint**:
   - Added `ck_clinical_exams_bcs_1_9` (`body_condition_score >= 1 AND body_condition_score <= 9`) in ORM and migration `b7c8d9e0f1a2`.
