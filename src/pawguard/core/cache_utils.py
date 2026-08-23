import hashlib
import json
from typing import Any

from fastapi import Request, Response
from fastapi.encoders import jsonable_encoder


def get_etag(content: bytes) -> str:
    """Generate a weak ETag based on content SHA-256."""
    return f'W/"{hashlib.sha256(content).hexdigest()}"'


def etag_cache_response(
    request: Request,
    data: Any,
    cache_control: str = "public, max-age=60",
) -> Response:
    """Check Request's If-None-Match header and return 304 if match, otherwise return 200 with ETag."""
    encoded_data = jsonable_encoder(data)
    json_bytes = json.dumps(encoded_data, sort_keys=True).encode("utf-8")

    etag = get_etag(json_bytes)

    if_none_match = request.headers.get("if-none-match")
    if if_none_match == etag:
        return Response(
            status_code=304,
            headers={
                "Cache-Control": cache_control,
                "ETag": etag,
            },
        )

    return Response(
        content=json_bytes,
        media_type="application/json",
        headers={
            "Cache-Control": cache_control,
            "ETag": etag,
        },
    )
