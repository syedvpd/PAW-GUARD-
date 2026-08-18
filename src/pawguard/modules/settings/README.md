# Settings Module

System configuration, business rules, password policy, and notification settings.

---

## Architecture

```
settings/
  router.py          # 14 endpoints
  service.py         # SettingsService
  repository.py      # Data access
  models.py          # ORM models
  schemas.py         # Pydantic DTOs
```

## Endpoints

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| GET | `/settings/general` | `system:admin` | General settings |
| GET | `/settings/email` | `system:admin` | Email configuration |
| GET | `/settings/storage` | `system:admin` | Storage configuration |
| GET | `/settings/public-content` | `public:read` | Public content settings |
| PUT | `/settings/public-content` | `system:admin` | Update public content |
| GET | `/settings/system` | `system:admin` | All system settings |
| GET | `/settings/system/{key}` | `system:admin` | Get setting by key |
| POST | `/settings/system` | `system:admin` | Create setting |
| PUT | `/settings/system/{key}` | `system:admin` | Update setting |
| DELETE | `/settings/system/{id}` | `system:admin` | Delete setting |
| GET | `/settings/password-policy` | `system:admin` | Password policy |
| PUT | `/settings/password-policy` | `system:admin` | Update password policy |
| GET | `/settings/business-rules` | `system:admin` | Business rules |
| GET/POST/PUT/DELETE | `/settings/business-rules/...` | `system:admin` | CRUD |

## Setting Categories

| Category | Examples |
|----------|---------|
| General | org_name, org_address, contact_email |
| Email | smtp_host, brevo_api_key, from_email |
| Storage | s3_bucket, s3_region |
| Public Content | hero_message, about_text |
| System | session_timeout, rate_limit_enabled |
| Password Policy | min_length, require_uppercase, require_special |
| Business Rules | max_rescue_distance, adoption_fee_default |

All mutations are audit-logged via `AuthAuditEventType.SETTINGS_UPDATED`.
