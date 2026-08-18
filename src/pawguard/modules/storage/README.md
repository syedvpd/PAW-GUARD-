# Storage Module

File upload/download via S3 presigned URLs with entity linking.

---

## Architecture

```
storage/
  router.py          # 9 endpoints
  service.py         # StorageService (S3 presigned URLs)
  repository.py      # Data access
  models.py          # StoredFile model
  schemas.py         # Pydantic DTOs
```

## Model

| Model | Table | Purpose |
|-------|-------|---------|
| `StoredFile` | `stored_files` | File metadata: object_key, entity linking, upload status |

## Upload Flow (Presigned URL)

```
POST /storage/upload-url {filename, content_type, folder, entity_type?, entity_id?}
  -> Generate S3 object key: {folder}/{uuid}_{filename}
  -> Create StoredFile (is_uploaded=False)
  -> Generate presigned upload URL (expires in minutes)
  -> Response: {file_id, upload_url, object_key}

PUT /storage/{file_id}/confirm
  -> Mark StoredFile.is_uploaded = True, uploaded_at = now
```

## Download Flow

```
GET /storage/{file_id}/download-url
  -> Generate presigned download URL (time-limited)
  -> Response: {download_url, expires_at}
```

## File Folders

`DOGS`, `MEDICAL`, `SHELTERS`, `PROFILES`, `DOCUMENTS`, `CERTIFICATES`, `RESCUE`, `EVIDENCE`, `AVATARS`, `LOST_FOUND`, `ADOPTIONS`, `GENERAL`, `BLOG`

## Entity Linking

Files can be linked to any entity via `entity_type` + `entity_id`:
- `entity_type="adoption_application"`, `entity_id=app.id`
- `entity_type="dog_profile"`, `entity_id=dog.id`
- `entity_type="volunteer_certificate"`, `entity_id=profile.id`

Query: `GET /storage/entity/{entity_type}/{entity_id}` returns all linked files.

## Cross-Module Usage

| Module | Usage |
|--------|-------|
| Dog | Profile photos, QR images |
| Medical | Medical file uploads |
| Adoption | Agreement PDFs |
| Volunteer | Service certificates |
| Donation | Tax receipt PDFs |
| Rescue | Incident media (photos/videos) |
| Companion Pet | Medical file uploads |
| Portal | Blog images, success story images |
