# ADR-006: File Storage

## Status

Accepted

## Context

PawGuard requires file storage for:
- Dog photos and videos
- Rescue evidence media
- User profile pictures
- Adoption agreements (PDF)
- Medical records
- Report exports

## Decision

Use **AWS S3** (or compatible) for object storage with **Supabase Storage** as an alternative.

## Alternatives Considered

### Local filesystem
- **Pros**: Simple, no external dependency
- **Cons**: Not scalable, lost on redeployment, no CDN
- **Verdict**: Rejected for production

### Cloudinary
- **Pros**: Image optimization, CDN, transformations
- **Cons**: Vendor lock-in, cost at scale
- **Verdict**: Rejected in favor of S3 flexibility

### Google Cloud Storage
- **Pros**: Good integration with GCP
- **Cons**: Vendor lock-in, different API
- **Verdict**: Rejected in favor of S3 compatibility

### MinIO
- **Pros**: S3-compatible, self-hosted
- **Cons**: Additional infrastructure, operational overhead
- **Verdict**: Rejected for managed service simplicity

## Consequences

### Positive
- Highly durable (11 9s)
- Scalable to any size
- CDN integration (CloudFront)
- S3 API compatibility
- Cost-effective at scale
- Supabase Storage as managed alternative

### Negative
- Network latency
- Vendor dependency
- Cost monitoring required

## Implementation

### Configuration
```bash
S3_BUCKET_NAME=pawguard-media
S3_REGION=us-east-1
S3_ENDPOINT_URL=  # For S3-compatible services
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
```

### Storage Module
```python
# src/pawguard/modules/storage/
# Handles presigned URLs, uploads, file management
# S3 client via boto3
```

### Upload Flow
1. Client requests presigned upload URL
2. Backend generates URL with expiration
3. Client uploads directly to S3
4. Backend records file metadata in `stored_files` table

### File Metadata
```python
# stored_files table
- id: UUID
- object_key: S3 object path
- thumbnail_object_key: Thumbnail path
- original_filename: Original name
- mime_type: Content type
- file_size: Size in bytes
- uploaded_by: User ID
```

### Presigned URLs
- Upload URLs: 15-minute expiration
- Download URLs: 1-hour expiration
- Temporary access without exposing credentials

### Thumbnail Generation
- Automatic thumbnail creation for images
- Stored alongside original file
- Used for listing/gallery views

## Media Evidence (Rescue)

```python
# Rescue requests store media evidence
media_evidence: list[str]  # S3 object keys
# Max 5 photos + short video clips
# Max 50MB combined
```

## Dog Gallery

```python
# Dog profiles store public gallery URLs
image_urls: list[str]  # CDN URLs
# Seeded directly for public listings
# No StoredFile row required
```

## Security

- Presigned URLs with expiration
- No public bucket (all access via presigned URLs)
- IAM roles for backend access
- Server-side encryption (SSE-S3)
- Versioning for data protection

## CDN Integration

- CloudFront or similar CDN
- Custom domain for media URLs
- Cache headers for performance

## Cost Optimization

- Lifecycle policies for old versions
- Intelligent tiering for infrequent access
- Multipart upload for large files
- Client-side compression before upload
