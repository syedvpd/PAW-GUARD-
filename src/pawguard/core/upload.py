"""File upload validation: mime-type, magic-bytes signature, and size enforcement.

Every file upload endpoint MUST call the appropriate verification functions
before persisting the file.
"""

from io import BytesIO

import magic  # type: ignore[import-untyped]
from PIL import Image, ImageOps

ALLOWED_MIME_TYPES: frozenset[str] = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/webp",
        "application/pdf",
        "video/mp4",
    }
)

MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB limit for images
MAX_VIDEO_SIZE_BYTES = 30 * 1024 * 1024  # 30 MB limit for videos
MAX_FILE_SIZE_BYTES = 30 * 1024 * 1024  # 30 MB limit for general files
MAX_BATCH_SIZE_BYTES = 30 * 1024 * 1024  # 30 MB combined batch cap
MAX_IMAGE_COUNT = 5


class UploadError(Exception):
    """Raised when a file fails validation."""


def verify_file_size(content: bytes, declared_mime: str | None = None) -> None:
    """Validate file size based on media type (10 MB for images, 30 MB for videos/other)."""
    size = len(content)
    if declared_mime and declared_mime.startswith("image/"):
        max_bytes = MAX_IMAGE_SIZE_BYTES
        limit_mb = 10
    elif declared_mime and declared_mime.startswith("video/"):
        max_bytes = MAX_VIDEO_SIZE_BYTES
        limit_mb = 30
    else:
        max_bytes = MAX_FILE_SIZE_BYTES
        limit_mb = 30

    if size > max_bytes:
        raise UploadError(
            f"File size ({size // (1024 * 1024)} MB) exceeds maximum allowed limit of {limit_mb} MB."
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


def verify_batch_size(sizes: list[int]) -> None:
    """Reject the batch if the combined size exceeds the 30 MB cap."""
    total = sum(sizes)
    if total > MAX_BATCH_SIZE_BYTES:
        raise UploadError(
            f"Combined batch size of {total} bytes exceeds the "
            f"{MAX_BATCH_SIZE_BYTES // (1024 * 1024)} MB limit."
        )


def _detect_mime(content: bytes) -> str:
    mime = magic.from_buffer(content, mime=True)
    if isinstance(mime, bytes):
        mime = mime.decode("utf-8")
    return mime or "application/octet-stream"


def verify_upload(content: bytes, declared_mime: str | None = None) -> str:
    verify_file_size(content)
    return verify_mime_type(content, declared_mime)


def create_thumbnail(content: bytes, max_size: int = 400) -> bytes | None:
    """Build a small, EXIF-free thumbnail for an image upload.

    Resizes the image down to at most ``max_size`` on the longest edge while
    preserving aspect ratio, re-encodes it without EXIF metadata (so uploader
    GPS/location data is never stored or served), and returns PNG bytes when
    the source has transparency and JPEG bytes otherwise. Returns ``None``
    when ``content`` is not a decodable image.
    """
    try:
        with Image.open(BytesIO(content)) as img:
            img.load()
    except (OSError, ValueError, TypeError):
        return None

    # Expose the correct pixel orientation and drop the EXIF block.
    thumb = ImageOps.exif_transpose(img)
    if thumb.mode == "P":
        thumb = thumb.convert("RGBA")
    thumb.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

    out = BytesIO()
    if thumb.mode in ("RGBA", "LA"):
        thumb.save(out, format="PNG", optimize=True)
    else:
        thumb = thumb.convert("RGB")
        thumb.save(out, format="JPEG", quality=80, optimize=True)
    return out.getvalue()


def optimize_image(
    content: bytes, max_dimension: int = 1920, quality: int = 85
) -> tuple[bytes, str, str] | None:
    """Compress and optimize an uploaded image for production web delivery.

    - Strips EXIF metadata (removing private location/device metadata).
    - Downscales dimensions exceeding ``max_dimension`` while preserving aspect ratio.
    - Encodes to WebP (or JPEG/PNG) with quality 85 and optimization.
    - Returns ``(compressed_bytes, mime_type, file_extension)`` or ``None`` if not an image.
    """
    try:
        with Image.open(BytesIO(content)) as img:
            img.load()
    except (OSError, ValueError, TypeError):
        return None

    opt = ImageOps.exif_transpose(img)
    if opt.mode == "P":
        opt = opt.convert("RGBA")

    width, height = opt.size
    if width > max_dimension or height > max_dimension:
        opt.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

    out = BytesIO()
    if opt.mode in ("RGBA", "LA"):
        opt.save(out, format="WEBP", quality=quality, method=4, optimize=True)
        return out.getvalue(), "image/webp", "webp"
    else:
        opt = opt.convert("RGB")
        opt.save(out, format="WEBP", quality=quality, method=4, optimize=True)
        return out.getvalue(), "image/webp", "webp"
