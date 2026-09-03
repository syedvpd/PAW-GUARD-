"""Unit tests for core exception handlers (IntegrityError, DataError, ValueError)."""

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy.exc import DataError, IntegrityError

from pawguard.core.exceptions import register_exception_handlers


@pytest.fixture
def app():
    test_app = FastAPI()
    register_exception_handlers(test_app)

    @test_app.get("/test-unique-integrity")
    async def route_unique(request: Request):
        raise IntegrityError(
            statement="INSERT INTO test",
            params={},
            orig=Exception(
                "duplicate key value violates unique constraint 'users_email_key'\nKey (email)=(test@example.com) already exists."
            ),
        )

    @test_app.get("/test-check-integrity")
    async def route_check(request: Request):
        raise IntegrityError(
            statement="INSERT INTO test",
            params={},
            orig=Exception(
                "new row for relation 'dog_sponsorships' violates check constraint 'ck_dog_sponsorships_monthly_amount_positive'"
            ),
        )

    @test_app.get("/test-data-error")
    async def route_data(request: Request):
        raise DataError(
            statement="INSERT INTO test",
            params={},
            orig=Exception("value too long for type character varying(3)"),
        )

    @test_app.get("/test-value-error")
    async def route_value(request: Request):
        raise ValueError("Invalid enum option provided.")

    return test_app


def test_unique_integrity_error_handled_as_409(app):
    client = TestClient(app)
    response = client.get("/test-unique-integrity")
    assert response.status_code == 409
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] in ("DUPLICATE_RESOURCE", "CONFLICT")
    assert "already exists" in body["error"]["message"]


def test_check_integrity_error_handled_as_422(app):
    client = TestClient(app)
    response = client.get("/test-check-integrity")
    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] in ("VALIDATION_ERROR", "VALIDATION_FAILED")


def test_data_error_handled_as_422(app):
    client = TestClient(app)
    response = client.get("/test-data-error")
    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] in ("VALIDATION_ERROR", "VALIDATION_FAILED")


def test_value_error_handled_as_422(app):
    client = TestClient(app)
    response = client.get("/test-value-error")
    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] in ("VALIDATION_ERROR", "VALIDATION_FAILED")
    assert "Invalid enum option provided." in body["error"]["message"]
