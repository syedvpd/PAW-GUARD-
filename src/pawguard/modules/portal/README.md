# Portal Module (CMS)

Public website content management — success stories, blog posts, FAQ, legal documents, urgent alerts, contact form, newsletter, and CMS pages.

---

## Architecture

```
portal/
  router.py          # 38 endpoints (public + admin)
  service.py         # PortalService (content CRUD, CMS)
  repository.py      # Data access
  models.py          # ORM models + enums
  schemas.py         # Pydantic DTOs
```

## Models

| Model | Table | Purpose |
|-------|-------|---------|
| `SuccessStory` | `success_stories` | Adoption success stories |
| `BlogPost` | `blog_posts` | Blog articles |
| `VeterinaryPartner` | `veterinary_partners` | Vet network directory |
| `ContactMessage` | `contact_messages` | Contact form submissions |
| `NewsletterSubscription` | `newsletter_subscriptions` | Email subscribers |
| `FAQEntry` | `faq_entries` | FAQ items |
| `LegalDocument` | `legal_documents` | Terms, privacy, policies |
| `UrgentAlert` | `urgent_alerts` | System-wide alerts |
| `CmsPage` | `cms_pages` | CMS pages with draft/publish |
| `CmsSection` | `cms_sections` | Page sections |
| `CmsContentField` | `cms_content_fields` | Section content |
| `CmsPageVersion` | `cms_page_versions` | Page version history |

## Key Endpoints

**Public:**
| Method | Path | Description |
|--------|------|-------------|
| GET | `/portal/stats` | Hero stats (dogs, adoptions, volunteers) |
| GET | `/portal/success-stories` | Published stories |
| GET | `/portal/blog` | Published blog posts |
| GET | `/portal/faq` | FAQ entries |
| GET | `/portal/legal` | Legal documents |
| GET | `/portal/urgent-alerts` | Active alerts |
| GET | `/portal/transparency` | Transparency stats |
| POST | `/portal/contact` | Submit contact message (rate-limited) |
| POST | `/portal/newsletter/subscribe` | Subscribe (rate-limited) |
| GET | `/portal/me/dashboard` | User dashboard summary |

**Admin (`system:admin`):**
| Method | Path | Description |
|--------|------|-------------|
| POST/PUT/DELETE | `/portal/admin/*` | Full CRUD for all content types |
| GET/PUT | `/portal/admin/settings/*` | System settings |
| POST | `/portal/admin/cms/pages/{slug}/publish` | Publish CMS page |

## CMS Draft/Publish Flow

```
PUT /portal/admin/cms/pages/{slug} {content fields}
  -> Update draft version

POST /portal/admin/cms/pages/{slug}/publish
  -> Create CmsPageVersion snapshot
  -> Set page.status = PUBLISHED
  -> Invalidate cache

POST /portal/admin/cms/pages/{slug}/discard
  -> Revert to last published version
```

## Caching

All public endpoints use Redis caching via `CacheService`:
- `pawguard:hero_stats`, `pawguard:transparency_stats`
- Cache invalidated on any admin mutation

## Scheduled Workers

| Worker | Frequency | Action |
|--------|-----------|--------|
| `post_adoption_followups` | Daily 10:00 | Follow-up reminders to adopters |
| `send_post_service_feedback_surveys` | Daily | Feedback survey emails |
