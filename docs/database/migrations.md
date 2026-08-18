# Migration Conventions

## Overview

PawGuard uses Alembic for database schema migrations. All schema changes must go through versioned migration files to ensure reproducible and auditable database evolution.

---

## Migration File Structure

```
alembic/
  env.py
  script.py.mako
  versions/
    001_initial_schema.py
    002_add_rescue_dispatch_agents.py
    ...
```

---

## Naming Conventions

Migration files follow a sequential numbering pattern:

```
{sequence}_{descriptive_name}.py
```

Examples:
- `001_initial_schema.py`
- `002_add_rescue_dispatch_agents.py`
- `003_add_dog_weight_logs.py`
- `004_backfill_physical_condition_enum.py`

---

## Migration Script Template

```python
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

---

## Best Practices

### 1. One Logical Change Per Migration

Each migration should represent a single logical change to the schema. This makes it easier to understand the evolution and rollback if needed.

**Good:**
- Add a single column
- Create a new table
- Add an index

**Bad:**
- Multiple unrelated changes in one migration
- Data transformation mixed with schema changes

### 2. Always Provide Downgrade

Every migration must include a working `downgrade()` function. This enables rollback to any previous state.

```python
def upgrade() -> None:
    op.add_column('dog_profiles', sa.Column('ear_shape', sa.String(32), nullable=True))

def downgrade() -> None:
    op.drop_column('dog_profiles', 'ear_shape')
```

### 3. Use Explicit Table Names

Always specify table names explicitly rather than relying on model imports:

```python
# Good
op.create_table(
    'dog_profiles',
    sa.Column('id', sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
    sa.Column('name', sa.String(255), nullable=False),
)

# Avoid
from pawguard.modules.dog.models import DogProfile
op.create_table(DogProfile.__tablename__, ...)
```

### 4. Handle Data Migrations Separately

Data transformations should be in separate migrations from schema changes:

```python
# Migration 1: Schema change
def upgrade() -> None:
    op.add_column('rescue_requests', sa.Column('physical_condition_v2', sa.String(64), nullable=True))

# Migration 2: Data backfill
def upgrade() -> None:
    op.execute("""
        UPDATE rescue_requests
        SET physical_condition_v2 = CASE
            WHEN physical_condition = 'critical' THEN 'critical_life_threatening'
            WHEN physical_condition = 'injured' THEN 'fractured_injured'
            ELSE 'unknown'
        END
    """)

# Migration 3: Drop old column
def upgrade() -> None:
    op.drop_column('rescue_requests', 'physical_condition')
    op.alter_column('rescue_requests', 'physical_condition_v2', new_column_name='physical_condition')
```

### 5. Test Migrations

Before committing:
1. Test upgrade from clean database
2. Test downgrade back to previous state
3. Test upgrade from current production state (if applicable)
4. Verify data integrity after migration

---

## Common Patterns

### Adding a Column

```python
def upgrade() -> None:
    op.add_column(
        'dog_profiles',
        sa.Column('ear_shape', sa.String(32), nullable=True)
    )

def downgrade() -> None:
    op.drop_column('dog_profiles', 'ear_shape')
```

### Adding an Index

```python
def upgrade() -> None:
    op.create_index(
        'ix_dog_profiles_status_is_adoptable',
        'dog_profiles',
        ['status', 'is_adoptable']
    )

def downgrade() -> None:
    op.drop_index('ix_dog_profiles_status_is_adoptable', table_name='dog_profiles')
```

### Adding a Foreign Key

```python
def upgrade() -> None:
    op.create_foreign_key(
        'fk_dog_profiles_rescue_case_id_rescue_requests',
        'dog_profiles',
        'rescue_requests',
        ['rescue_case_id'],
        ['id'],
        ondelete='SET NULL'
    )

def downgrade() -> None:
    op.drop_constraint(
        'fk_dog_profiles_rescue_case_id_rescue_requests',
        'dog_profiles',
        type_='foreignkey'
    )
```

### Creating a Table

```python
def upgrade() -> None:
    op.create_table(
        'rescue_dispatch_agents',
        sa.Column('id', sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('dispatch_id', sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey('rescue_dispatches.id', ondelete='CASCADE'), nullable=False),
        sa.Column('agent_id', sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', sa.String(64), nullable=True),
    )
    op.create_unique_constraint(
        'uq_rescue_dispatch_agents_dispatch_agent',
        'rescue_dispatch_agents',
        ['dispatch_id', 'agent_id']
    )

def downgrade() -> None:
    op.drop_constraint('uq_rescue_dispatch_agents_dispatch_agent', 'rescue_dispatch_agents')
    op.drop_table('rescue_dispatch_agents')
```

### Dropping a Table

```python
def upgrade() -> None:
    op.drop_table('legacy_table')

def downgrade() -> None:
    op.create_table(
        'legacy_table',
        sa.Column('id', sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
    )
```

---

## Running Migrations

### Apply Pending Migrations

```bash
alembic upgrade head
```

### Rollback One Migration

```bash
alembic downgrade -1
```

### Rollback to Specific Version

```bash
alembic downgrade 001
```

### Generate New Migration

```bash
alembic revision --autogenerate -m "description of change"
```

### View Migration History

```bash
alembic history
```

### View Current Version

```bash
alembic current
```

---

## Naming Convention Enforcement

The database uses a consistent naming convention for constraints defined in `src/pawguard/db/base.py`:

```python
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
```

When creating constraints in migrations, use these naming patterns:

```python
# Index
op.create_index('ix_dog_profiles_status', 'dog_profiles', ['status'])

# Unique constraint
op.create_unique_constraint('uq_users_email', 'users', ['email'])

# Foreign key
op.create_foreign_key(
    'fk_dog_profiles_shelter_facility_id_shelter_facilities',
    'dog_profiles',
    'shelter_facilities',
    ['shelter_facility_id'],
    ['id'],
    ondelete='SET NULL'
)
```

---

## Environment Configuration

The `alembic.ini` file configures the migration environment:

```ini
[alembic]
script_location = alembic
sqlalchemy.url = driver://user:pass@localhost/dbname
```

The `env.py` file handles:
- Loading database URL from environment
- Configuring async SQLAlchemy engine
- Setting up migration context

---

## Production Considerations

1. **Back up before migrating** in production environments
2. **Test migrations** against a copy of production data
3. **Schedule migrations** during low-traffic windows
4. **Monitor** database performance after migration
5. **Keep migrations small** to minimize lock time
6. **Use online schema changes** when possible (e.g., adding nullable columns)
