# Donation Module

Donor management, one-time/online donations, sponsorships, campaigns, Razorpay payment integration, and tax receipt generation.

---

## Architecture

```
donation/
  router.py          # 25+ endpoints
  service.py         # DonationService (donations, sponsorships, campaigns)
  repository.py      # Data access
  models.py          # ORM models + enums
  schemas.py         # Pydantic DTOs
```

## Models

| Model | Table | Purpose |
|-------|-------|---------|
| `DonorProfile` | `donor_profiles` | Donor record linked to user |
| `Donation` | `donations` | Donation: amount, status, payment gateway fields |
| `DogSponsorship` | `dog_sponsorships` | Monthly sponsorship per dog |
| `RecurringSubscription` | `recurring_subscriptions` | Monthly recurring donations |
| `DonationCampaign` | `donation_campaigns` | Fundraising campaigns with goal tracking |

## Endpoints

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| POST | `/donations/register` | Auth (rate-limited) | Register as donor |
| POST | `/donations` | `donation:manage` | Manual/offline donation |
| POST | `/donations/checkout` | Auth (rate-limited) | Initiate online payment |
| POST | `/donations/verify` | `finance:reconcile` | Verify payment signature |
| POST | `/donations/webhook/razorpay` | Webhook | Server-to-server callback |
| GET | `/donations` | `donation:read` | List donations |
| GET | `/donations/my` | Authenticated | My donation history |
| GET | `/donations/{id}/receipt` | Owner or `donation:read` | Download tax receipt |
| POST | `/donations/sponsorships` | Auth (rate-limited) | Create sponsorship |
| PATCH | `/donations/sponsorships/{id}/status` | Owner or `donation:manage` | Pause/cancel |
| GET | `/donations/sponsorships` | `donation:read` | List sponsorships |
| POST | `/donations/campaigns` | `donation:manage` | Create campaign |
| GET | `/donations/campaigns` | Public | List active campaigns |
| GET | `/donations/campaigns/{id}` | Optional auth | Campaign details |
| PATCH | `/donations/campaigns/{id}` | `donation:update` | Update campaign |
| POST | `/donations/recurring` | Authenticated | Create recurring subscription |
| DELETE | `/donations/recurring/{id}` | Owner or `donation:manage` | Cancel recurring |
| GET | `/donations/donors` | `donation:read` | List donors (PII masked) |
| GET | `/donations/donors/me` | Authenticated | My donor profile |

## Online Payment Flow

```
1. POST /donations/checkout {amount, currency, dog_id?, campaign_id?}
   -> Create Donation(status=PENDING)
   -> gateway.create_order(amount, currency, receipt=donation_id)
   -> Response: {donation_id, order_id, checkout_key}

2. Client completes payment on Razorpay

3. POST /donations/verify {donation_id, order_id, payment_id, signature}
   -> gateway.verify_payment_signature(order_id, payment_id, signature)
   -> Mark Donation(status=SUCCESS)
   -> Generate PDF tax receipt -> upload to S3
   -> Refresh campaign progress (auto-complete if goal reached)
   -> Auto-post to finance ledger
   -> Audit: DONATION_RECEIVED
```

## Tax Receipt Generation

- PDF via reportlab: donor name, amount, currency, transaction ID, date, org info
- Uploaded to S3: `documents/receipt_{donation_id}.pdf`
- Notification: in-app + email + push to donor

## Sponsorship Lifecycle

```
ACTIVE ──pause──> PAUSED ──resume──> ACTIVE
ACTIVE ──cancel──> CANCELLED
PAUSED ──cancel──> CANCELLED
```

Monthly charges via background job `process_sponsorship_charges`.

## Campaign Auto-Completion

- After every successful donation, `_refresh_campaign_progress()` is called
- If `raised >= target_amount`: auto-sets status=COMPLETED, sets `goal_reached_at`

## Cross-Module Interactions

| Trigger | Target | Effect |
|---------|--------|--------|
| Successful donation | Finance | Auto-post to ledger (debit cash, credit income) |
| Successful donation | Storage | Tax receipt PDF uploaded |
| Successful donation | Notifications | In-app + email + push to donor |
| Sponsorship created | Notifications | Confirmation to donor |
| Campaign goal reached | Notifications | Push to campaign creator + donors |
