"""Storage module: file metadata management with S3 presigned URL generation.

Provides CRUD for StoredFile records, upload/download URL generation,
entity-scoped file listing, and bulk soft-delete.
"""

from pawguard.modules.storage.router import router

__all__ = ["router"]
