from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass
class FakeKeycloakClient:
    """In-memory Keycloak stand-in for integration tests and local dev."""

    _users: dict[tuple[str, str], str] = field(default_factory=dict)
    _passwords: dict[tuple[str, str], str] = field(default_factory=dict)
    _subjects: set[str] = field(default_factory=set)
    _realms: set[str] = field(default_factory=lambda: {"platform"})

    async def create_realm(self, realm_name: str) -> str:
        name = realm_name.strip().lower()
        if not name:
            raise ValueError("realm name required")
        self._realms.add(name)
        return name

    async def create_user(self, realm: str, email: str, password: str) -> str:
        key = (realm, email.lower())
        if key in self._users:
            raise ValueError("Keycloak user already exists")
        subject = f"kc-{uuid.uuid4()}"
        self._users[key] = subject
        self._passwords[key] = password
        self._subjects.add(subject)
        self._realms.add(realm)
        return subject

    async def delete_user(self, realm: str, subject: str) -> None:
        self._subjects.discard(subject)
        for key, sub in list(self._users.items()):
            if sub == subject and key[0] == realm:
                del self._users[key]
                self._passwords.pop(key, None)

    async def authenticate(self, realm: str, email: str, password: str) -> str:
        key = (realm, email.lower())
        if key not in self._users or self._passwords.get(key) != password:
            raise ValueError("Invalid credentials")
        return self._users[key]

    async def set_password(
        self, realm: str, subject: str, password: str, *, email: str | None = None
    ) -> str:
        for key, sub in self._users.items():
            if sub == subject and key[0] == realm:
                self._passwords[key] = password
                return subject
        if email:
            key = (realm, email.lower())
            self._users[key] = subject
            self._passwords[key] = password
            self._subjects.add(subject)
            self._realms.add(realm)
            return subject
        raise ValueError("Subject not found")
