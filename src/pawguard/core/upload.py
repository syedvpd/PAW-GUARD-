"""File upload validation: mime-type, magic-bytes signature, and size enforcement.

Every file upload endpoint MUST call ``verify_upload`` before persisting the file.
"""


import magic  # type: ignore[import-untyped]

ALLOWED_MIME_TYPES: frozenset[str] = frozenset({
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/pdf",
    "video/mp4",
})

MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB

MAX_IMAGE_COUNT = 5


class UploadError(Exception):
    """Raised when a file fails validation."""


def verify_file_size(content: bytes) -> None:
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise UploadError(
            f"File exceeds maximum size of {MAX_FILE_SIZE_BYTES // (1024*1024)} MB."
        )


def verify_mime_type(content: bytes, declared_mime: str | None = None) -> str:
    detected = _detect_mime(content)
    if detected not in ALLOWED_MIME_TYPES:
        raise UploadError(
            f"File type '{detected}' is not allowed. "
            f"Allowed: {', '.join(sorted(ALLOWED_MIME_TYPES))}."
        )
    if declared_mime and declared_mime != detected:
        raise UploadError("Declared MIME type does not match file content.")
    return detected


def _detect_mime(content: bytes) -> str:
    mime = magic.from_buffer(content, mime=True)
    if isinstance(mime, bytes):
        mime = mime.decode("utf-8")
    return mime or "application/octet-stream"


def verify_upload(content: bytes, declared_mime: str | None = None) -> str:
    verify_file_size(content)
    return verify_mime_type(content, declared_mime)
