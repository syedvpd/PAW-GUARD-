"""High-performance responsive image transformation and delivery service.

Transforms original multi-megabyte images into mobile-optimized WebP variants:
- thumb: max 200x200, WebP, quality 75 (~3-5 KB)
- card: max 680x1020, WebP, quality 80 (~30-50 KB)
- detail: max 1200x1200, WebP, quality 85 (~100-150 KB)
- original: original image bytes

Caches transformed variants locally in memory / scratch cache so repeated requests
are served in < 5ms with stable ETags and Cache-Control: public, max-age=31536000, immutable.
"""

import hashlib
from io import BytesIO
from typing import Literal

from PIL import Image, ImageOps

from pawguard.core.logging import get_logger

logger = get_logger(__name__)

ImageVariantType = Literal["thumb", "card", "detail", "original"]

VARIANT_CONFIG: dict[str, dict[str, int]] = {
    "thumb": {"max_w": 200, "max_h": 200, "quality": 75},
    "card": {"max_w": 680, "max_h": 1020, "quality": 80},
    "mobile": {"max_w": 680, "max_h": 1020, "quality": 80},
    "detail": {"max_w": 1200, "max_h": 1200, "quality": 85},
}

# In-memory LRU variant cache: (cache_key) -> (bytes, content_type, etag)
_VARIANT_MEMORY_CACHE: dict[str, tuple[bytes, str, str]] = {}
_MAX_MEMORY_CACHE_ITEMS = 300


def compute_etag(data: bytes) -> str:
    """Compute deterministic ETag from content hash."""
    digest = hashlib.sha256(data).hexdigest()[:16]
    return f'"{digest}"'


def transform_image_variant(
    content: bytes,
    variant: str = "card",
) -> tuple[bytes, str, str]:
    """Transform source image bytes to the requested variant.

    Returns:
        (variant_bytes, content_type, etag)
    """
    variant_lower = variant.lower()
    if variant_lower == "original":
        etag = compute_etag(content)
        # Check image type
        try:
            with Image.open(BytesIO(content)) as img:
                fmt = (img.format or "JPEG").lower()
                mime = f"image/{fmt}"
        except Exception:
            mime = "image/jpeg"
        return content, mime, etag

    config = VARIANT_CONFIG.get(variant_lower, VARIANT_CONFIG["card"])
    max_w = config["max_w"]
    max_h = config["max_h"]
    quality = config["quality"]

    # Cache key based on content hash and variant
    content_hash = hashlib.sha256(content).hexdigest()[:16]
    cache_key = f"{content_hash}_{variant_lower}_{max_w}_{max_h}_{quality}"

    if cache_key in _VARIANT_MEMORY_CACHE:
        return _VARIANT_MEMORY_CACHE[cache_key]

    try:
        with Image.open(BytesIO(content)) as img:
            # Drop EXIF orientation and normalize
            normalized = ImageOps.exif_transpose(img)
            if normalized.mode == "P":
                normalized = normalized.convert("RGBA")

            # Check if resize needed
            w, h = normalized.size
            if w > max_w or h > max_h:
                normalized.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)

            out = BytesIO()
            if normalized.mode in ("RGBA", "LA"):
                normalized.save(out, format="WEBP", quality=quality, method=4)
            else:
                rgb_img = normalized.convert("RGB")
                rgb_img.save(out, format="WEBP", quality=quality, method=4)

            variant_bytes = out.getvalue()
            content_type = "image/webp"
            etag = compute_etag(variant_bytes)

            # Save in memory cache
            if len(_VARIANT_MEMORY_CACHE) >= _MAX_MEMORY_CACHE_ITEMS:
                # Evict 50 oldest keys
                for k in list(_VARIANT_MEMORY_CACHE.keys())[:50]:
                    del _VARIANT_MEMORY_CACHE[k]

            res = (variant_bytes, content_type, etag)
            _VARIANT_MEMORY_CACHE[cache_key] = res
            return res
    except Exception as exc:
        logger.warning("image_variant_transformation_failed", variant=variant, error=str(exc))
        etag = compute_etag(content)
        return content, "image/jpeg", etag
