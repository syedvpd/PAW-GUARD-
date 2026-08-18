# PawGuard Database Documentation

## Overview

PawGuard uses PostgreSQL as its primary database, accessed via SQLAlchemy async ORM with Alembic for migrations. This documentation covers the schema, relationships, migration conventions, indexing strategy, and constraint policies.

---

## Documentation Files

| File | Description |
|------|-------------|
| [schema.md](schema.md) | Full schema overview with all tables and columns |
| [relationships.md](relationships.md) | Entity relationship diagrams and foreign key mapping |
| [migrations.md](migrations.md) | Migration conventions and best practices |
| [indexes.md](indexes.md) | Index strategy and performance considerations |
| [constraints.md](constraints.md) | Constraints and data integrity policies |

---

## Database Configuration

- **Engine:** PostgreSQL 15+ with `asyncpg` driver
- **ORM:** SQLAlchemy 2.0 async with Mapped types
- **Migrations:** Alembic with auto-generated revisions
- **Connection Pool:** Async pool with configurable min/max connections

---

## Core Conventions

### Primary Keys

All tables use UUID v4 primary keys via the `UUIDPkMixin`:

```python
id: Mapped[uuid.UUID] = mapped_column(
    PG_UUID(as_uuid=True),
    primary_key=True,
    default=uuid.uuid4,
    server_default=func.gen_random_uuid(),
)
```

### Timestamps

All tables include `created_at` and `updated_at` via the `TimestampMixin`:

```python
created_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    server_default=func.now(),
    nullable=False,
    index=True,
)
updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    server_default=func.now(),
    onupdate=func.now(),
    nullable=False,
    index=True,
)
```

### Soft Delete

Operational records use soft delete via the `SoftDeleteMixin`:

```python
deleted_at: Mapped[datetime | None] = mapped_column(
    DateTime(timezone=True), nullable=True, index=True
)
```

Hard deletes are never performed on operational records. The `deleted_at` column is set to the deletion timestamp; null indicates an active record.

### Audit Trail

Records that track who created or modified them use the `AuditMixin`:

```python
created_by: Mapped[uuid.UUID | None] = mapped_column(
    PG_UUID(as_uuid=True),
    ForeignKey("users.id", ondelete="SET NULL"),
    nullable=True,
    index=True,
)
updated_by: Mapped[uuid.UUID | None] = mapped_column(
    PG_UUID(as_uuid=True),
    ForeignKey("users.id", ondelete="SET NULL"),
    nullable=True,
    index=True,
)
```

---

## Table Inventory

| Module | Table | Description |
|--------|-------|-------------|
| Auth | `users` | User accounts |
| Auth | `roles` | Role definitions |
| Auth | `permissions` | Permission codes |
| Auth | `user_roles` | User-role assignments |
| Auth | `role_permissions` | Role-permission grants |
| Auth | `user_sessions` | Active sessions |
| Auth | `refresh_tokens` | Refresh token records |
| Auth | `mfa_devices` | MFA TOTP devices |
| Auth | `password_reset_tokens` | Password reset tokens |
| Auth | `email_verification_tokens` | Email verification tokens |
| Auth | `oauth_accounts` | Linked OAuth accounts |
| Auth | `auth_audit_logs` | Authentication audit trail |
| Dog | `dog_profiles` | Dog master profiles |
| Dog | `dog_weight_logs` | Weight measurement history |
| Dog | `dog_activity_logs` | Lifecycle activity stream |
| Rescue | `rescue_requests` | Emergency rescue cases |
| Rescue | `rescue_dispatches` | Dispatch records |
| Rescue | `rescue_dispatch_agents` | Agent-dispatch assignments |
| Rescue | `rescue_reports` | Field observation reports |
| Medical | `clinical_exams` | Clinical examination records |
| Medical | `medical_treatments` | Treatment and surgery records |
| Medical | `vaccination_records` | Vaccination history |
| Medical | `prescriptions` | Medication prescriptions |
| Medical | `medication_administration_logs` | Administration sign-offs |
| Medical | `vaccine_protocols` | Vaccine scheduling protocols |
| Medical | `medical_clearances` | Adoption/surgery clearances |
| Adoption | `adoption_applications` | Adoption applications |
| Adoption | `adoption_scores` | Vetting scores |
| Adoption | `adoption_follow_ups` | Post-adoption check-ins |
| Shelter | `shelter_facilities` | Shelter facilities |
| Shelter | `shelter_sections` | Facility sections |
| Shelter | `kennels` | Individual kennels |
| Shelter | `facility_transfers` | Inter-facility transfers |
| Shelter | `daily_care_logs` | Daily care records |
| Shelter | `kennel_cleaning_logs` | Cleaning rotation logs |
| Fleet | `vehicles` | Fleet vehicles |
| Fleet | `fleet_maintenances` | Maintenance records |
| Fleet | `equipment_checkouts` | Equipment checkout records |
| Fleet | `fuel_logs` | Fuel fill-up records |

---

## Naming Conventions

All database objects follow a consistent naming convention defined in `src/pawguard/db/base.py`:

```python
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
```

Examples:
- Primary key: `pk_users`
- Foreign key: `fk_dog_profiles_rescue_case_id_rescue_requests`
- Unique constraint: `uq_users_email`
- Index: `ix_users_email`
