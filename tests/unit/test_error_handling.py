"""Unit tests for centralized error detection, classification, and traceable response contracts."""

import uuid

import pytest
from fastapi import FastAPI
from fastapi.exceptions import ResponseValidationError
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field
from sqlalchemy.exc import (
    DisconnectionError,
    IntegrityError,
    ProgrammingError,
    SQLAlchemyError,
)

from pawguard.core.exceptions import (
    ConflictError,
    ErrorCategory,
    ErrorLayer,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    register_exception_handlers,
)
from pawguard.core.middleware import RequestIDMiddleware


@pytest.fixture
def test_app() -> FastAPI:
    """Create a minimal FastAPI app configured with PawGuard exception handlers & middleware."""
    app = FastAPI(title="PawGuard Error Testing")
    app.add_middleware(RequestIDMiddleware)
    register_exception_handlers(app)

    class ItemPayload(BaseModel):
        name: str = Field(..., min_length=2)
        quantity: int = Field(..., gt=0)

    class ResponseModel(BaseModel):
        id: uuid.UUID
        name: str

    @app.get("/test/resource/{item_id}")
    async def get_resource(item_id: str):
        if item_id == "missing":
            raise NotFoundError("The requested entity with ID 'missing' was not found.")
        return {"success": True, "data": {"id": item_id}}

    @app.post("/test/validation")
    async def validate_endpoint(payload: ItemPayload):
        return {"success": True, "data": payload.model_dump()}

    @app.get("/test/auth-required")
    async def auth_required():
        raise UnauthorizedError("No authentication credentials were provided.")

    @app.get("/test/forbidden")
    async def forbidden_endpoint():
        raise ForbiddenError("User lacks required 'system:admin' permission.")

    @app.get("/test/conflict")
    async def conflict_endpoint():
        raise ConflictError("A record with this identifier already exists.")

    @app.get("/test/db-query-error")
    async def db_query_error():
        raise SQLAlchemyError("SELECT * FROM dogs WHERE syntax error at or near 'WHERE'")

    @app.get("/test/db-connection-error")
    async def db_conn_error():
        raise DisconnectionError("Connection closed by server / connection refused")

    @app.get("/test/db-schema-error")
    async def db_schema_error():
        orig_err = Exception("relation 'dogs' does not exist")
        err = ProgrammingError("SELECT * FROM dogs", {}, orig_err)
        raise err

    @app.get("/test/db-unique-error")
    async def db_unique_error():
        orig_err = Exception("Key (email)=(test@example.com) already exists.")
        err = IntegrityError("INSERT INTO users", {}, orig_err)
        raise err

    @app.get("/test/db-foreign-key-error")
    async def db_fk_error():
        orig_err = Exception("violates foreign key constraint 'fk_shelter_facility'")
        err = IntegrityError("INSERT INTO kennels", {}, orig_err)
        raise err

    @app.get("/test/db-check-constraint-error")
    async def db_check_error():
        orig_err = Exception("violates check constraint 'ck_positive_weight'")
        err = IntegrityError("INSERT INTO weights", {}, orig_err)
        raise err

    @app.get("/test/serialization-error")
    async def serialization_error():
        raise ResponseValidationError(
            errors=[{"loc": ("response", "id"), "msg": "Invalid UUID", "type": "uuid_parsing"}]
        )

    @app.get("/test/unhandled-exception")
    async def unhandled_exception():
        raise AttributeError("'NoneType' object has no attribute 'execute_transaction'")

    return app


@pytest.fixture
def client(test_app: FastAPI) -> TestClient:
    return TestClient(test_app, raise_server_exceptions=False)


class TestCentralizedErrorContract:
    def test_missing_route_returns_404_route_not_found(self, client: TestClient):
        """Test A: Non-existent route returns 404 ROUTE_NOT_FOUND under category ROUTING."""
        res = client.get("/api/v1/nonexistent-endpoint-url")
        assert res.status_code == 404
        data = res.json()
        assert data["success"] is False
        err = data["error"]
        assert err["code"] == "ROUTE_NOT_FOUND"
        assert err["category"] == ErrorCategory.ROUTING
        assert err["layer"] == ErrorLayer.ROUTER
        assert "does not exist on this server" in err["message"]
        assert err["endpoint"] == "/api/v1/nonexistent-endpoint-url"
        assert err["method"] == "GET"
        assert err["requestId"] is not None
        assert res.headers["X-Request-ID"] == err["requestId"]

    def test_missing_resource_returns_404_resource_not_found(self, client: TestClient):
        """Test B: Existent route with missing resource returns 404 RESOURCE_NOT_FOUND under category RESOURCE."""
        res = client.get("/test/resource/missing")
        assert res.status_code == 404
        data = res.json()
        assert data["success"] is False
        err = data["error"]
        assert err["code"] == "RESOURCE_NOT_FOUND"
        assert err["category"] == ErrorCategory.RESOURCE
        assert err["layer"] == ErrorLayer.SERVICE
        assert "was not found" in err["message"]
        assert err["endpoint"] == "/test/resource/missing"
        assert err["requestId"] is not None

    def test_validation_error_returns_422_validation_error(self, client: TestClient):
        """Test C: Invalid request payload returns 422 VALIDATION_ERROR under category VALIDATION."""
        res = client.post("/test/validation", json={"name": "a", "quantity": -5})
        assert res.status_code == 422
        data = res.json()
        assert data["success"] is False
        err = data["error"]
        assert err["code"] == "VALIDATION_ERROR"
        assert err["category"] == ErrorCategory.VALIDATION
        assert err["layer"] == ErrorLayer.VALIDATION
        assert isinstance(err["details"], list)
        assert len(err["details"]) > 0
        assert err["requestId"] is not None

    def test_authentication_required_returns_401(self, client: TestClient):
        """Test D: Missing authentication returns 401 AUTHENTICATION_REQUIRED under category AUTHENTICATION."""
        res = client.get("/test/auth-required")
        assert res.status_code == 401
        data = res.json()
        assert data["success"] is False
        err = data["error"]
        assert err["code"] == "AUTHENTICATION_REQUIRED"
        assert err["category"] == ErrorCategory.AUTHENTICATION
        assert err["layer"] == ErrorLayer.AUTHENTICATION
        assert err["requestId"] is not None

    def test_authorization_failed_returns_403(self, client: TestClient):
        """Test E: Insufficient permissions returns 403 AUTHORIZATION_FAILED under category AUTHORIZATION."""
        res = client.get("/test/forbidden")
        assert res.status_code == 403
        data = res.json()
        assert data["success"] is False
        err = data["error"]
        assert err["code"] == "AUTHORIZATION_FAILED"
        assert err["category"] == ErrorCategory.AUTHORIZATION
        assert err["layer"] == ErrorLayer.AUTHORIZATION
        assert err["requestId"] is not None

    def test_database_query_error_returns_500(self, client: TestClient):
        """Test F: Database query failure returns 500 DATABASE_QUERY_FAILED under category DATABASE."""
        res = client.get("/test/db-query-error")
        assert res.status_code == 500
        data = res.json()
        assert data["success"] is False
        err = data["error"]
        assert err["code"] == "DATABASE_QUERY_FAILED"
        assert err["category"] == ErrorCategory.DATABASE
        assert err["layer"] == ErrorLayer.DATABASE
        # Verify raw SQL is not exposed to frontend
        assert "syntax error at or near" not in err["message"]
        assert "A database query execution error occurred" in err["message"]
        assert err["requestId"] is not None

    def test_database_connection_error_returns_503(self, client: TestClient):
        """Test G: Database unreachable/connection error returns 503 DATABASE_CONNECTION_FAILED."""
        res = client.get("/test/db-connection-error")
        assert res.status_code == 503
        data = res.json()
        assert data["success"] is False
        err = data["error"]
        assert err["code"] == "DATABASE_CONNECTION_FAILED"
        assert err["category"] == ErrorCategory.DATABASE
        assert err["layer"] == ErrorLayer.DATABASE
        assert "database service is currently unavailable" in err["message"]
        assert err["requestId"] is not None

    def test_database_schema_error_returns_500(self, client: TestClient):
        """Test H: Database missing table/column / pending migration returns 500 DATABASE_SCHEMA_ERROR."""
        res = client.get("/test/db-schema-error")
        assert res.status_code == 500
        data = res.json()
        assert data["success"] is False
        err = data["error"]
        assert err["code"] == "DATABASE_SCHEMA_ERROR"
        assert err["category"] == ErrorCategory.DATABASE
        assert err["layer"] == ErrorLayer.DATABASE
        assert "schema mismatch or pending migration" in err["message"]
        assert err["requestId"] is not None

    def test_database_unique_constraint_returns_409_duplicate(self, client: TestClient):
        """Test I: Unique violation returns 409 DUPLICATE_RESOURCE with field info."""
        res = client.get("/test/db-unique-error")
        assert res.status_code == 409
        data = res.json()
        assert data["success"] is False
        err = data["error"]
        assert err["code"] == "DUPLICATE_RESOURCE"
        assert err["category"] == ErrorCategory.DATABASE
        assert "email" in err["message"]
        assert err["details"]["constraint"] == "unique_violation"

    def test_database_foreign_key_returns_409_constraint_failed(self, client: TestClient):
        """Test J: Foreign key violation returns 409 DATABASE_CONSTRAINT_FAILED."""
        res = client.get("/test/db-foreign-key-error")
        assert res.status_code == 409
        data = res.json()
        assert data["success"] is False
        err = data["error"]
        assert err["code"] == "DATABASE_CONSTRAINT_FAILED"
        assert err["category"] == ErrorCategory.DATABASE
        assert err["details"]["constraint"] == "foreign_key_violation"

    def test_database_check_constraint_returns_422(self, client: TestClient):
        """Test K: Check constraint violation returns 422 VALIDATION_ERROR."""
        res = client.get("/test/db-check-constraint-error")
        assert res.status_code == 422
        data = res.json()
        assert data["success"] is False
        err = data["error"]
        assert err["code"] == "VALIDATION_ERROR"
        assert err["category"] == ErrorCategory.VALIDATION
        assert err["details"]["constraint"] == "check_violation"

    def test_serialization_error_returns_500(self, client: TestClient):
        """Test L: Pydantic response formatting error returns 500 RESPONSE_SERIALIZATION_FAILED."""
        res = client.get("/test/serialization-error")
        assert res.status_code == 500
        data = res.json()
        assert data["success"] is False
        err = data["error"]
        assert err["code"] == "RESPONSE_SERIALIZATION_FAILED"
        assert err["category"] == ErrorCategory.SYSTEM
        assert err["layer"] == ErrorLayer.SERIALIZATION
        assert "formatting response data model" in err["message"]

    def test_unhandled_exception_returns_500_with_safe_details(self, client: TestClient):
        """Test M: Unhandled exception returns 500 INTERNAL_SERVER_ERROR without exposing raw stack trace."""
        res = client.get("/test/unhandled-exception")
        assert res.status_code == 500
        data = res.json()
        assert data["success"] is False
        err = data["error"]
        assert err["code"] == "INTERNAL_SERVER_ERROR"
        assert err["category"] == ErrorCategory.SYSTEM
        assert err["layer"] == ErrorLayer.SYSTEM
        # Verify raw traceback is not in message or details
        assert "Traceback" not in err["message"]
        assert "Traceback" not in str(err["details"])
        assert "AttributeError" in err["details"]
        assert err["requestId"] is not None

    def test_request_id_correlation_preserved_from_client_header(self, client: TestClient):
        """Test N: Valid client-supplied X-Request-ID is preserved and echoed in headers and body."""
        custom_id = "req_custom_trace_12345"
        res = client.get("/test/resource/missing", headers={"X-Request-ID": custom_id})
        assert res.status_code == 404
        assert res.headers["X-Request-ID"] == custom_id
        assert res.json()["error"]["requestId"] == custom_id
