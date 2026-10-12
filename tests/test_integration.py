import os
import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def database_url():
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not configured")
    return url


def test_health_checks_real_services(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["postgres"] is True
    assert response.json()["redis"] is True


def test_create_order_and_verify_in_postgres(client, database_url):
    customer = "ci-" + uuid.uuid4().hex[:10]

    response = client.post(
        "/orders",
        json={
            "customer": customer,
            "restaurant": "CI Test Kitchen",
            "items": [
                {"name": "Test Meal", "paise": 12500}
            ],
        },
    )

    assert response.status_code == 201
    order = response.json()
    order_id = order["id"]

    try:
        assert order["customer"] == customer
        assert order["status"] == "placed"
        assert order["total_paise"] == 12500

        with psycopg.connect(database_url) as connection:
            row = connection.execute(
                "SELECT customer, status, total_paise "
                "FROM orders WHERE id = %s",
                (order_id,),
            ).fetchone()

        assert row == (customer, "placed", 12500)

        get_response = client.get(f"/orders/{order_id}")
        assert get_response.status_code == 200
        assert get_response.json()["id"] == order_id

    finally:
        with psycopg.connect(database_url) as connection:
            connection.execute(
                "DELETE FROM orders WHERE id = %s",
                (order_id,),
            )
