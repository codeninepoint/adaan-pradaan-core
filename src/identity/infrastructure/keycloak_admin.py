"""Keycloak Admin REST client (real IdP)."""

from __future__ import annotations

import time
from urllib.parse import quote

import httpx
from jose import jwt


class KeycloakUnavailable(Exception):
    """Transient Keycloak/admin API failure — safe to retry."""


class RealKeycloakClient:
    """Talks to a running Keycloak via the Admin API and direct-access grants."""

    def __init__(
        self,
        *,
        base_url: str,
        admin_username: str,
        admin_password: str,
        client_id: str,
    ) -> None:
        if not base_url:
            raise RuntimeError("TENANT_KEYCLOAK_BASE_URL is required when TENANT_KEYCLOAK_MODE=real")
        self._base = base_url.rstrip("/")
        self._admin_username = admin_username
        self._admin_password = admin_password
        self._client_id = client_id
        self._http = httpx.AsyncClient(base_url=self._base, timeout=30.0)
        self._admin_token: str | None = None
        self._admin_token_exp: float = 0.0

    async def _admin_headers(self) -> dict[str, str]:
        now = time.time()
        if not self._admin_token or now >= self._admin_token_exp:
            try:
                response = await self._http.post(
                    "/realms/master/protocol/openid-connect/token",
                    data={
                        "grant_type": "password",
                        "client_id": "admin-cli",
                        "username": self._admin_username,
                        "password": self._admin_password,
                    },
                )
            except httpx.HTTPError as exc:
                raise KeycloakUnavailable(str(exc)) from exc
            if response.status_code >= 500:
                raise KeycloakUnavailable(response.text[:300])
            if response.status_code >= 400:
                raise ValueError(f"Keycloak admin login failed: {response.status_code}")
            body = response.json()
            self._admin_token = body["access_token"]
            self._admin_token_exp = now + max(int(body.get("expires_in", 60)) - 10, 5)
        return {"Authorization": f"Bearer {self._admin_token}"}

    async def _admin(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        params: dict | None = None,
    ) -> httpx.Response:
        headers = await self._admin_headers()
        if json is not None:
            headers = {**headers, "Content-Type": "application/json"}
        try:
            response = await self._http.request(method, path, headers=headers, json=json, params=params)
        except httpx.HTTPError as exc:
            raise KeycloakUnavailable(str(exc)) from exc
        if response.status_code >= 500:
            raise KeycloakUnavailable(response.text[:300])
        return response

    async def create_realm(self, realm_name: str) -> str:
        name = realm_name.strip().lower()
        if not name:
            raise ValueError("realm name required")
        response = await self._admin("POST", "/admin/realms", json={"realm": name, "enabled": True, "displayName": name})
        if response.status_code not in (201, 409):
            raise ValueError(f"create realm failed: {response.status_code} {response.text[:200]}")
        await self._ensure_direct_grant_client(name)
        return name

    async def _ensure_direct_grant_client(self, realm: str) -> None:
        listed = await self._admin(
            "GET",
            f"/admin/realms/{quote(realm)}/clients",
            params={"clientId": self._client_id},
        )
        if listed.status_code >= 400:
            raise ValueError(f"list clients failed: {listed.status_code}")
        if listed.json():
            return
        created = await self._admin(
            "POST",
            f"/admin/realms/{quote(realm)}/clients",
            json={
                "clientId": self._client_id,
                "enabled": True,
                "publicClient": True,
                "directAccessGrantsEnabled": True,
                "standardFlowEnabled": False,
                "protocol": "openid-connect",
            },
        )
        if created.status_code not in (201, 409):
            raise ValueError(f"create client failed: {created.status_code} {created.text[:200]}")

    async def create_user(self, realm: str, email: str, password: str) -> str:
        normalized = email.strip().lower()
        response = await self._admin(
            "POST",
            f"/admin/realms/{quote(realm)}/users",
            json={
                "username": normalized,
                "email": normalized,
                "enabled": True,
                "emailVerified": False,
                "credentials": [{"type": "password", "value": password, "temporary": False}],
            },
        )
        if response.status_code == 404:
            await self.create_realm(realm)
            response = await self._admin(
                "POST",
                f"/admin/realms/{quote(realm)}/users",
                json={
                    "username": normalized,
                    "email": normalized,
                    "enabled": True,
                    "emailVerified": False,
                    "credentials": [{"type": "password", "value": password, "temporary": False}],
                },
            )
        if response.status_code == 409:
            raise ValueError("Keycloak user already exists")
        if response.status_code != 201:
            raise ValueError(f"create user failed: {response.status_code} {response.text[:200]}")
        location = response.headers.get("Location", "")
        subject = location.rstrip("/").split("/")[-1]
        if not subject:
            raise ValueError("Keycloak did not return a user id")
        return subject

    async def delete_user(self, realm: str, subject: str) -> None:
        response = await self._admin("DELETE", f"/admin/realms/{quote(realm)}/users/{quote(subject)}")
        if response.status_code not in (204, 404):
            raise ValueError(f"delete user failed: {response.status_code}")

    async def authenticate(self, realm: str, email: str, password: str) -> str:
        try:
            response = await self._http.post(
                f"/realms/{quote(realm)}/protocol/openid-connect/token",
                data={
                    "grant_type": "password",
                    "client_id": self._client_id,
                    "username": email.strip().lower(),
                    "password": password,
                },
            )
        except httpx.HTTPError as exc:
            raise KeycloakUnavailable(str(exc)) from exc
        if response.status_code == 404:
            await self.create_realm(realm)
            try:
                response = await self._http.post(
                    f"/realms/{quote(realm)}/protocol/openid-connect/token",
                    data={
                        "grant_type": "password",
                        "client_id": self._client_id,
                        "username": email.strip().lower(),
                        "password": password,
                    },
                )
            except httpx.HTTPError as exc:
                raise KeycloakUnavailable(str(exc)) from exc
        if response.status_code >= 500:
            raise KeycloakUnavailable(response.text[:300])
        if response.status_code >= 400:
            raise ValueError("Invalid credentials")
        token = response.json().get("access_token")
        if not token:
            raise ValueError("Invalid credentials")
        claims = jwt.get_unverified_claims(token)
        subject = claims.get("sub")
        if not subject:
            raise ValueError("Invalid credentials")
        return str(subject)

    async def set_password(
        self, realm: str, subject: str, password: str, *, email: str | None = None
    ) -> str:
        target = subject
        response = await self._admin(
            "PUT",
            f"/admin/realms/{quote(realm)}/users/{quote(target)}/reset-password",
            json={"type": "password", "value": password, "temporary": False},
        )
        if response.status_code in (204, 200):
            return target
        if response.status_code != 404 or not email:
            raise ValueError("Subject not found")
        found = await self._admin(
            "GET",
            f"/admin/realms/{quote(realm)}/users",
            params={"email": email.strip().lower(), "exact": "true"},
        )
        users = found.json() if found.status_code == 200 else []
        if users:
            target = users[0]["id"]
        else:
            return await self.create_user(realm, email, password)
        reset = await self._admin(
            "PUT",
            f"/admin/realms/{quote(realm)}/users/{quote(target)}/reset-password",
            json={"type": "password", "value": password, "temporary": False},
        )
        if reset.status_code not in (204, 200):
            raise ValueError("Subject not found")
        return target
