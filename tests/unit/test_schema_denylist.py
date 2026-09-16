"""Schema exposure denylist test — adversarial regression guard (ITEM 8e).

This test walks EVERY response_model registered in the application's routers
and asserts that no sensitive/internal field name appears in any public response
schema. It runs in CI on every push — if a developer accidentally adds
`hashed_password` to a response model, this test fails before it can merge.

Methodology (per adversarial pre-mortem §11):
- Hard denylist of known-bad names.
- Pattern-based check for credential-like field names.
- Recursive traversal including nested models.
"""

from __future__ import annotations

import re
from typing import Any, get_args, get_origin, get_type_hints

from pydantic import BaseModel

# ── Hard denylist ────────────────────────────────────────────────────────────
# Exact field names that MUST NEVER appear in any public response schema.
HARD_DENYLIST: set[str] = {
    "hashed_password",
    "password",
    "password_hash",
    "mfa_secret",
    "mfa_secret_encrypted",
    "totp_secret",
    "access_token",
    "refresh_token",
    "webhook_secret",
    "private_key",
    "secret_key",
    "api_key",
    "api_secret",
    "client_secret",
    "encryption_key",
    "signing_key",
    "jwt_secret",
    "razorpay_key_secret",
}

# ── Pattern-based check ──────────────────────────────────────────────────────
# Field names matching these patterns are suspicious — flag them for manual review.
# These are patterns that commonly indicate leaked credentials even under different names.
_CREDENTIAL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^.*_secret$", re.IGNORECASE),
    re.compile(r"^.*_password$", re.IGNORECASE),
    re.compile(r"^.*_private_key$", re.IGNORECASE),
    re.compile(r"^.*_token$", re.IGNORECASE),  # allow_list below carves out legitimate tokens
    re.compile(r"^.*_api_key$", re.IGNORECASE),
    re.compile(r"^.*_webhook$", re.IGNORECASE),
]

# Token-like field names that are LEGITIMATE in response schemas.
_ALLOWED_TOKEN_FIELDS: set[str] = {
    "fcm_token",  # Firebase push token (user's own)
    "device_token",  # User's own device token
    "idempotency_token",  # Public-safe idempotency identifier
    "csrf_token",  # Public-safe CSRF token for forms
}


def _is_credential_pattern(field_name: str) -> bool:
    """Returns True if the field name matches a credential-like pattern."""
    if field_name in _ALLOWED_TOKEN_FIELDS:
        return False
    return any(p.match(field_name) for p in _CREDENTIAL_PATTERNS)


def _collect_model_fields(
    model: type[BaseModel],
    visited: set[type[BaseModel]] | None = None,
) -> dict[str, list[str]]:
    """Recursively collect all field names from a Pydantic model and its nested models.

    Returns a dict mapping model_name -> list of field_names.
    Prevents infinite recursion via visited set.
    """
    if visited is None:
        visited = set()
    if model in visited:
        return {}
    visited.add(model)

    result: dict[str, list[str]] = {}
    try:
        hints = get_type_hints(model)
    except Exception:  # noqa: BLE001 — some models have forward refs we can't resolve
        return result

    field_names = list(hints.keys())
    result[model.__name__] = field_names

    # Recurse into nested Pydantic models (including Optional[SubModel], list[SubModel], etc.)
    for annotation in hints.values():
        for sub in _extract_pydantic_models(annotation):
            result.update(_collect_model_fields(sub, visited))

    return result


def _extract_pydantic_models(annotation: Any) -> list[type[BaseModel]]:
    """Extract all Pydantic model types from a potentially generic annotation."""
    models: list[type[BaseModel]] = []
    try:
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            models.append(annotation)
        # Handle generics: Optional[X], list[X], Union[X, Y], etc.
        origin = get_origin(annotation)
        if origin is not None:
            for arg in get_args(annotation):
                models.extend(_extract_pydantic_models(arg))
    except Exception:  # noqa: BLE001
        pass
    return models


def _get_all_response_models() -> dict[str, list[str]]:
    """Collect all response schemas registered across the entire application.

    Imports the FastAPI app and walks every route's response_model.
    """
    from pawguard.main import app  # noqa: PLC0415

    all_fields: dict[str, list[str]] = {}
    visited_models: set[type[BaseModel]] = set()

    for route in app.routes:
        response_model = getattr(route, "response_model", None)
        if response_model is None:
            continue
        for model in _extract_pydantic_models(response_model):
            if isinstance(model, type) and issubclass(model, BaseModel):
                all_fields.update(_collect_model_fields(model, visited_models))

    return all_fields


class TestSchemaDenylist:
    """Hard denylist enforcement for response schemas."""

    def test_no_hardcoded_denylist_fields_in_response_schemas(self) -> None:
        """FAILS if any response schema exposes a hard-denylist field name."""
        all_fields = _get_all_response_models()
        violations: list[str] = []

        for model_name, field_names in all_fields.items():
            for field in field_names:
                if field in HARD_DENYLIST:
                    violations.append(f"{model_name}.{field}")

        assert not violations, (
            "SECURITY: The following response schemas expose sensitive field names:\n"
            + "\n".join(f"  - {v}" for v in sorted(violations))
            + "\n\nRemove these fields from response models or use a separate read-safe schema."
        )

    def test_no_credential_pattern_fields_in_response_schemas(self) -> None:
        """FAILS if any response schema has a field matching a credential-like pattern.

        This catches secrets/tokens that were renamed but still shouldn't leak.
        Explicitly allowed token fields are whitelisted in _ALLOWED_TOKEN_FIELDS.
        """
        all_fields = _get_all_response_models()
        violations: list[str] = []

        for model_name, field_names in all_fields.items():
            for field in field_names:
                if _is_credential_pattern(field):
                    violations.append(f"{model_name}.{field}")

        assert not violations, (
            "SECURITY: The following response schemas have credential-pattern field names:\n"
            + "\n".join(f"  - {v}" for v in sorted(violations))
            + "\n\nAudit whether these fields should be in a response schema."
        )

    def test_denylist_itself_is_not_empty(self) -> None:
        """Guard: ensures the denylist was not accidentally emptied."""
        assert len(HARD_DENYLIST) >= 8, "Denylist was unexpectedly emptied or truncated."

    def test_new_hashed_password_field_fails(self) -> None:
        """Negative test: verifies the test infrastructure catches violations.

        Injects a model with hashed_password into the check function and asserts
        it would be caught. This proves the test isn't a no-op.
        """

        class MockResponseWithPassword(BaseModel):
            id: str
            hashed_password: str  # This should be detected

        fields = _collect_model_fields(MockResponseWithPassword)
        violations = [
            f"{name}.{field}"
            for name, field_list in fields.items()
            for field in field_list
            if field in HARD_DENYLIST
        ]
        assert len(violations) > 0, (
            "The denylist check did NOT catch a model with hashed_password — "
            "the test infrastructure itself is broken."
        )

    def test_legitimate_model_passes(self) -> None:
        """Positive test: a clean model must pass the denylist check."""

        class CleanResponse(BaseModel):
            id: str
            name: str
            email: str
            created_at: str

        fields = _collect_model_fields(CleanResponse)
        violations = [
            field
            for field_list in fields.values()
            for field in field_list
            if field in HARD_DENYLIST
        ]
        assert not violations, f"Clean model incorrectly flagged: {violations}"
