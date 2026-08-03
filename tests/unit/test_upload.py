"""Unit tests for core/upload.py thumbnail generation."""

from io import BytesIO

from PIL import ExifTags, Image

from pawguard.core.upload import create_thumbnail


def _image_bytes_with_gps_exif(width: int = 800, height: int = 600) -> bytes:
    img = Image.new("RGB", (width, height), color=(255, 0, 0))
    exif = Image.Exif()
    exif[ExifTags.IFD.GPSInfo] = {
        ExifTags.GPS.GPSLatitude: (37, 5, 0),
        ExifTags.GPS.GPSLongitude: (122, 2, 0),
        ExifTags.GPS.GPSLatitudeRef: "N",
        ExifTags.GPS.GPSLongitudeRef: "W",
    }
    buf = BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


class TestCreateThumbnail:
    def test_resizes_to_max_size_preserving_aspect_ratio(self) -> None:
        source = _image_bytes_with_gps_exif(800, 600)
        thumb = create_thumbnail(source, max_size=400)
        assert thumb is not None

        with Image.open(BytesIO(thumb)) as out:
            assert out.width <= 400
            assert out.height <= 400
            # 800x600 -> 400x300 keeps the 4:3 ratio.
            assert out.width == 400
            assert out.height == 300

    def test_strips_exif_metadata(self) -> None:
        source = _image_bytes_with_gps_exif(800, 600)
        thumb = create_thumbnail(source, max_size=400)
        assert thumb is not None

        with Image.open(BytesIO(thumb)) as out:
            exif = out.getexif()
            assert not exif
            assert ExifTags.IFD.GPSInfo not in exif

    def test_returns_none_for_non_image_bytes(self) -> None:
        assert create_thumbnail(b"not an image at all") is None

    def test_smaller_input_is_not_upscaled(self) -> None:
        source = _image_bytes_with_gps_exif(10, 10)
        thumb = create_thumbnail(source, max_size=400)
        assert thumb is not None
        with Image.open(BytesIO(thumb)) as out:
            assert out.width <= 10
            assert out.height <= 10
