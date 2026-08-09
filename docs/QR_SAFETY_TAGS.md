# QR Code Generation Engine — Pet Safety Tags

The safety-tag engine issues privacy-safe, single-use **QR pet ID tags** that let
any finder scan a lost pet and receive only the information needed to help —
without ever exposing the owner's identity or contact details.

## Design goals

1. **Unforgeable** — a scanned token must prove the QR was minted by the system.
2. **Private** — scanning reveals the pet's safe fields, never owner PII.
3. **Revocable / rotatable** — the owner can rotate a tag so a lost old QR stops
   working, without changing the pet profile.
4. **One tag per pet** — only one *active* tag per pet is valid at any time.
5. **Auditable** — scan count and last-scan time are tracked; scans are rate
   limited.
6. **No secret at rest** — the raw token is never stored; only its hash is.

## How it works

### Provision / rotate (`POST /companion-pets/{pet_id}/safety-tag`)
- Permission: `safety_tag:manage`.
- Generates `raw_token = secrets.token_urlsafe(48)` (64 base64url chars, ~384 bit).
- Persists ONLY `token_hash = sha256(raw_token)` and `token_prefix = raw_token[:8]`.
- If an active tag already exists it is deactivated (rotation); the old raw token
  immediately fails to scan.
- Returns `raw_token` in the response body **exactly once**.
- `token_prefix` is shown on subsequent reads for the owner to identify the tag
  ("which QR is which") without revealing the full token.

### Read (`GET /companion-pets/{pet_id}/safety-tag`)
- Returns metadata: `token_prefix`, `is_active`, `last_scanned_at`, `scan_count`.
- **Never** returns the raw token (it is unrecoverable).

### Public scan (`POST /companion-pets/safety-tag/scan`)
- **No authentication.** Rate limited to 20 requests/minute per client (IP).
- Body: `{ "token": "<raw_token_from_QR>" }`.
- The service hashes the supplied token and looks up `token_hash`; a missing or
  inactive tag → `404`.
- If the pet's `is_scan_enabled` is `false` → `404`.
- Returns **only** safe fields:

```json
{
  "pet_id": "...",
  "name": "Max",
  "species": "dog",
  "breed": "Labrador",
  "color": "Brown",
  "emergency_notes": "Allergic to penicillin. Call any vet.",
  "message": "If this pet needs urgent care, contact a local veterinary clinic."
}
```

- Increments `scan_count` and sets `last_scanned_at` (audit trail).

### What the QR encodes
The client renders the `raw_token` into a QR image, ideally as a deep link:
`https://pawguard.app/qr/<raw_token>`. The finder's scanner app extracts the
token and POSTs to `/companion-pets/safety-tag/scan`. No other personal data is
encoded in the QR.

## Security properties

| Property | Mechanism |
|----------|-----------|
| Token secrecy at rest | only SHA-256 `token_hash` stored; raw token unrecoverable |
| Uniqueness | `token_hash` UNIQUE constraint |
| One active tag per pet | per-pet active tag uniqueness |
| Rotation revokes old tag | old tag set `is_active=false`; scan prefers active |
| Scan privacy | response contains no owner/microchip fields |
| Scan abuse control | rate limited 20/min per IP |
| Disabled scan | `is_scan_enabled=false` → 404 |
| Audit | `scan_count`, `last_scanned_at`, audit events on provision/scan |

## Test plan (manual / Postman)

See `POSTMAN_API_TESTING_GUIDE.md` §4 for the step-by-step checks:
provision → raw_token once → scan succeeds → wrong token 404 → 21st scan 429
→ rotate → old token 404, new token succeeds → `is_scan_enabled=false` → 404.