"""Unit tests for responsive image transformation, variants, and delivery."""

from io import BytesIO

from PIL import Image

from pawguard.modules.storage.image_delivery import (
    VARIANT_CONFIG,
    compute_etag,
    transform_image_variant,
)


def _create_dummy_image(width: int = 3000, height: int = 4000, color: str = "blue") -> bytes:
    img = Image.new("RGB", (width, height), color=color)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def test_transform_image_card_variant():
    orig_bytes = _create_dummy_image(3000, 4000)
    variant_bytes, mime, etag = transform_image_variant(orig_bytes, "card")

    assert mime == "image/webp"
    assert etag.startswith('"') and etag.endswith('"')
    assert len(variant_bytes) < len(orig_bytes)

    # Check transformed dimensions
    with Image.open(BytesIO(variant_bytes)) as img:
        w, h = img.size
        assert w <= VARIANT_CONFIG["card"]["max_w"]
        assert h <= VARIANT_CONFIG["card"]["max_h"]


def test_transform_image_thumb_variant():
    orig_bytes = _create_dummy_image(2000, 2000)
    variant_bytes, mime, etag = transform_image_variant(orig_bytes, "thumb")

    assert mime == "image/webp"
    assert len(variant_bytes) < len(orig_bytes)

    with Image.open(BytesIO(variant_bytes)) as img:
        w, h = img.size
        assert w <= VARIANT_CONFIG["thumb"]["max_w"]
        assert h <= VARIANT_CONFIG["thumb"]["max_h"]


def test_transform_image_original_variant():
    orig_bytes = _create_dummy_image(500, 500)
    variant_bytes, mime, etag = transform_image_variant(orig_bytes, "original")

    assert variant_bytes == orig_bytes
    assert mime == "image/jpeg"
    assert etag == compute_etag(orig_bytes)


def test_etag_consistency():
    data = b"some-consistent-image-bytes"
    etag1 = compute_etag(data)
    etag2 = compute_etag(data)
    assert etag1 == etag2
