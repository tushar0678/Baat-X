"""HTTP-level auth, RBAC and tenant isolation."""

from __future__ import annotations

import uuid

import pytest


async def signup(client, email: str, business: str) -> dict:  # noqa: ANN001
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "full_name": "Owner",
            "email": email,
            "password": "StrongPassw0rd!",
            "business_name": business,
            "vertical": "real_estate",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def auth_headers(token: dict) -> dict:
    return {
        "Authorization": f"Bearer {token['access_token']}",
        "X-Business-Id": str(token["active_business_id"]),
    }


@pytest.mark.anyio
async def test_signup_login_and_me(client) -> None:  # noqa: ANN001
    token = await signup(client, "owner@baatx.example.com", "Sharma Properties")
    assert token["user"]["businesses"][0]["role"] == "owner"

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@baatx.example.com", "password": "StrongPassw0rd!"},
    )
    assert login.status_code == 200

    me = await client.get("/api/v1/auth/me", headers=auth_headers(login.json()))
    assert me.json()["email"] == "owner@baatx.example.com"


@pytest.mark.anyio
async def test_wrong_password_is_generic(client) -> None:  # noqa: ANN001
    await signup(client, "owner2@baatx.example.com", "B2")
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "owner2@baatx.example.com", "password": "wrong-password"},
    )
    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "unauthenticated"
    assert body["message"] == "Incorrect email or password."


@pytest.mark.anyio
async def test_unauthenticated_request_is_rejected(client) -> None:  # noqa: ANN001
    assert (await client.get("/api/v1/customers")).status_code == 401


@pytest.mark.anyio
async def test_customer_is_invisible_across_tenants(client) -> None:  # noqa: ANN001
    tenant_a = await signup(client, "a@baatx.example.com", "Tenant A")
    tenant_b = await signup(client, "b@baatx.example.com", "Tenant B")

    created = await client.post(
        "/api/v1/customers",
        headers=auth_headers(tenant_a),
        json={"name": "Rajesh", "phone": "9876543210", "requirement": "2BHK"},
    )
    assert created.status_code == 201
    customer_id = created.json()["id"]

    # The same phone number is allowed in the other business...
    duplicate = await client.post(
        "/api/v1/customers",
        headers=auth_headers(tenant_b),
        json={"name": "Rajesh", "phone": "9876543210"},
    )
    assert duplicate.status_code == 201
    assert duplicate.json()["id"] != customer_id

    # ...but tenant B can never read tenant A's row.
    leak = await client.get(f"/api/v1/customers/{customer_id}", headers=auth_headers(tenant_b))
    assert leak.status_code == 404

    listing = await client.get("/api/v1/customers", headers=auth_headers(tenant_b))
    assert all(item["id"] != customer_id for item in listing.json()["items"])


@pytest.mark.anyio
async def test_duplicate_phone_inside_a_tenant_is_blocked(client) -> None:  # noqa: ANN001
    tenant = await signup(client, "dup@baatx.example.com", "Dup Co")
    payload = {"name": "Rajesh", "phone": "+91 98765 43210"}
    assert (
        await client.post("/api/v1/customers", headers=auth_headers(tenant), json=payload)
    ).status_code == 201
    conflict = await client.post("/api/v1/customers", headers=auth_headers(tenant), json=payload)
    assert conflict.status_code == 409
    assert "already exists" in conflict.json()["message"]


@pytest.mark.anyio
async def test_business_header_must_match_a_membership(client) -> None:  # noqa: ANN001
    tenant = await signup(client, "hdr@baatx.example.com", "Header Co")
    headers = {
        "Authorization": f"Bearer {tenant['access_token']}",
        "X-Business-Id": str(uuid.uuid4()),
    }
    assert (await client.get("/api/v1/customers", headers=headers)).status_code == 403


@pytest.mark.anyio
async def test_validation_errors_are_human_readable(client) -> None:  # noqa: ANN001
    tenant = await signup(client, "val@baatx.example.com", "Val Co")
    response = await client.post(
        "/api/v1/customers",
        headers=auth_headers(tenant),
        json={"budget_min": 100, "budget_max": 10},
    )
    assert response.status_code == 422
    assert response.json()["message"] == (
        "Some details are missing or invalid. Please check and try again."
    )


@pytest.mark.anyio
async def test_health_and_readiness(client) -> None:  # noqa: ANN001
    assert (await client.get("/health")).json()["status"] == "ok"
    assert (await client.get("/ready")).json()["database"] in {"ok", "unavailable"}
