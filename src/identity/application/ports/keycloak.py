from __future__ import annotations

from typing import Protocol


class KeycloakClient(Protocol):
    async def create_user(self, realm: str, email: str, password: str) -> str: ...

    async def delete_user(self, realm: str, subject: str) -> None: ...

    async def authenticate(self, realm: str, email: str, password: str) -> str: ...

    async def set_password(
        self, realm: str, subject: str, password: str, *, email: str | None = None
    ) -> str: ...

    async def create_realm(self, realm_name: str) -> str: ...
