from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.application.ports.bootstrap import AuthzQueryPort, TenantBootstrapPort
from identity.application.ports.keycloak import KeycloakClient
from identity.domain.security import (
    generate_otp,
    hash_secret,
    make_reset_token_composite,
    otp_expires_at,
    refresh_expires_at,
    split_reset_token,
    utcnow,
    verify_secret,
)
from identity.domain.validators import validate_display_name, validate_email, validate_password
from identity.infrastructure.bootstrap_adapters import AuthzReader, TenantBootstrapAdapter
from identity.infrastructure.models import (
    AuditLogRow,
    CredentialRow,
    DeliverySecretRow,
    IdentityRealmRow,
    PasswordResetTokenRow,
    PrincipalRow,
    SessionRow,
    UserRow,
    VerificationTokenRow,
)
from shared.domain.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)
from shared.infrastructure.models import OutboxEventRow
from shared.settings import settings


@dataclass
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int
    session_id: UUID
    user_id: UUID
    principal_id: UUID


class IdentityApplicationService:
    """
    Identity application service.

    Persistence still uses the request session (pragmatic). Domain security helpers and
    bootstrap/authz ports keep infrastructure coupling at the edges (M4 incremental).
    """

    def __init__(
        self,
        session: AsyncSession,
        keycloak: KeycloakClient,
        *,
        bootstrap: TenantBootstrapPort | None = None,
        authz: AuthzQueryPort | None = None,
    ) -> None:
        self._session = session
        self._keycloak = keycloak
        self._bootstrap: TenantBootstrapPort = bootstrap or TenantBootstrapAdapter(session)
        self._authz: AuthzQueryPort = authz or AuthzReader(session)

    async def register_user(
        self, *, email: str, password: str, display_name: str, agreed_to_terms: bool
    ) -> dict:
        validate_email(email)
        validate_password(password)
        validate_display_name(display_name)
        if not agreed_to_terms:
            raise ValidationError("terms of service must be accepted")

        normalized = email.lower()
        existing = await self._session.execute(
            select(UserRow).where(UserRow.normalized_email == normalized)
        )
        if existing.scalar_one_or_none():
            raise ConflictError("email already registered")

        realm = await self._get_platform_realm()
        kc_subject: str | None = None
        try:
            kc_subject = await self._keycloak.create_user(realm.realm_name, email, password)
            # I1: principal inactive until email verified
            principal = PrincipalRow(
                id=uuid.uuid4(),
                principal_type="user",
                status="inactive",
            )
            self._session.add(principal)
            await self._session.flush()

            user = UserRow(
                id=uuid.uuid4(),
                principal_id=principal.id,
                email=normalized,
                normalized_email=normalized,
                display_name=display_name.strip(),
                status="pending_verification",
            )
            self._session.add(user)
            await self._session.flush()

            self._session.add(
                CredentialRow(
                    id=uuid.uuid4(),
                    principal_id=principal.id,
                    identity_realm_id=realm.id,
                    keycloak_subject=kc_subject,
                    credential_type="password_delegated",
                    status="active",
                )
            )

            bootstrap = await self._bootstrap.bootstrap_individual_org(
                user_id=user.id,
                principal_id=principal.id,
                email=email,
                display_name=display_name,
            )

            otp = generate_otp()
            verification = VerificationTokenRow(
                id=uuid.uuid4(),
                user_id=user.id,
                otp_hash=hash_secret(otp),
                expires_at=otp_expires_at(),
            )
            self._session.add(verification)
            await self._session.flush()

            delivery = DeliverySecretRow(
                id=uuid.uuid4(),
                purpose="verification_email",
                secret_plain=otp,
                expires_at=otp_expires_at(),
            )
            self._session.add(delivery)
            self._session.add(
                OutboxEventRow(
                    id=uuid.uuid4(),
                    type="send_verification_email",
                    payload_json={
                        "email": user.email,
                        "user_id": str(user.id),
                        "verification_token_id": str(verification.id),
                        "delivery_secret_id": str(delivery.id),
                    },
                    status="pending",
                )
            )

            await self._audit("user.registered", actor_user_id=user.id, tenant_id=bootstrap.tenant_id)
            await self._audit("credential.created", actor_user_id=user.id)
            await self._audit("org.created", actor_user_id=user.id, tenant_id=bootstrap.tenant_id)
            await self._audit("tenant.created", actor_user_id=user.id, tenant_id=bootstrap.tenant_id)
            await self._audit("roles.seeded", actor_user_id=user.id, tenant_id=bootstrap.tenant_id)
            await self._audit("role_binding.created", actor_user_id=user.id, tenant_id=bootstrap.tenant_id)

            await self._session.commit()
            return {
                "user_id": str(user.id),
                "org_id": str(bootstrap.org_id),
                "tenant_id": str(bootstrap.tenant_id),
                "status": user.status,
                "verification_email_sent": True,
            }
        except Exception:
            await self._session.rollback()
            if kc_subject:
                await self._keycloak.delete_user(settings.platform_realm_name, kc_subject)
            raise

    async def verify_email(self, *, email: str, otp_code: str) -> dict:
        # L1: avoid user enumeration
        user = await self._get_user_by_email(email)
        if not user:
            raise ValidationError("invalid or expired OTP")
        if user.status == "active":
            raise ConflictError("user already verified")
        if user.status != "pending_verification":
            raise ForbiddenError("account is not accessible")

        token_row = await self._latest_verification_token(user.id)
        if not token_row or token_row.expires_at < utcnow() or not verify_secret(otp_code, token_row.otp_hash):
            raise ValidationError("invalid or expired OTP")

        user.status = "active"
        principal = await self._session.get(PrincipalRow, user.principal_id)
        if principal:
            principal.status = "active"
        await self._audit("user.email_verified", actor_user_id=user.id)
        await self._session.commit()
        return {
            "user_id": str(user.id),
            "status": user.status,
            "message": "Email verified. You can now log in.",
        }

    async def login(self, *, email: str, password: str, realm_hint: str | None = None) -> TokenPair:
        # L1: generic credential failure
        user = await self._get_user_by_email(email)
        if not user:
            raise UnauthorizedError("invalid credentials")

        realm_name = realm_hint or settings.platform_realm_name
        realm = await self._get_realm_by_name(realm_name)
        if not realm:
            raise UnauthorizedError("invalid credentials")

        if user.status != "active":
            raise ForbiddenError("account is not accessible")

        principal = await self._session.get(PrincipalRow, user.principal_id)
        if not principal or principal.status != "active":
            raise ForbiddenError("account is not accessible")

        try:
            kc_subject = await self._keycloak.authenticate(realm.realm_name, email, password)
        except ValueError as exc:
            raise UnauthorizedError("invalid credentials") from exc

        cred = await self._session.execute(
            select(CredentialRow).where(
                CredentialRow.principal_id == user.principal_id,
                CredentialRow.keycloak_subject == kc_subject,
                CredentialRow.identity_realm_id == realm.id,
                CredentialRow.status == "active",
            )
        )
        if not cred.scalar_one_or_none():
            raise UnauthorizedError("invalid credentials")

        issuer = realm.issuer or realm.issuer_url
        return await self._issue_tokens(user, kc_subject, issuer)

    async def refresh_token(self, *, refresh_token: str, session_id: UUID) -> dict:
        """
        Rotate refresh token (J4). Reuse of an old refresh → revoke session (theft signal).
        Access JWT stays lean — no roles/permissions claims.
        """
        session = await self._session.get(SessionRow, session_id)
        if not session:
            raise UnauthorizedError("refresh token invalid / expired")
        if session.status == "revoked":
            raise UnauthorizedError("refresh token invalid / expired")
        if session.expires_at < utcnow():
            await self._revoke_session(session, session.user_id, clear_refresh=True)
            await self._session.commit()
            raise UnauthorizedError("refresh token invalid / expired")

        if not session.refresh_token_hash:
            raise UnauthorizedError("refresh token invalid / expired")

        if not verify_secret(refresh_token, session.refresh_token_hash):
            # Possible theft: someone already rotated; invalidate the session.
            await self._revoke_session(session, session.user_id, clear_refresh=True)
            await self._session.commit()
            raise UnauthorizedError("refresh token invalid / expired")

        user = await self._session.get(UserRow, session.user_id)
        if not user or user.status != "active":
            await self._revoke_session(session, session.user_id, clear_refresh=True)
            await self._session.commit()
            raise UnauthorizedError("refresh token invalid / expired")

        principal = await self._session.get(PrincipalRow, user.principal_id)
        if not principal or principal.status != "active":
            await self._revoke_session(session, session.user_id, clear_refresh=True)
            await self._session.commit()
            raise UnauthorizedError("refresh token invalid / expired")

        cred = await self._session.execute(
            select(CredentialRow)
            .where(
                CredentialRow.principal_id == user.principal_id,
                CredentialRow.status == "active",
            )
            .limit(1)
        )
        credential = cred.scalar_one_or_none()
        if not credential:
            raise UnauthorizedError("refresh token invalid / expired")

        realm = await self._session.get(IdentityRealmRow, credential.identity_realm_id)
        issuer = (realm.issuer or realm.issuer_url) if realm else settings.platform_issuer_url

        new_refresh = secrets.token_urlsafe(48)
        session.refresh_token_hash = hash_secret(new_refresh)
        session.last_active_at = utcnow()
        session.expires_at = refresh_expires_at()

        access = self._build_access_token(
            sub=credential.keycloak_subject,
            iss=issuer,
            sid=session.id,
            typ="user",
            uid=str(user.id),
            pid=str(user.principal_id),
        )
        await self._session.commit()
        return {
            "access_token": access,
            "refresh_token": new_refresh,
            "expires_in": settings.jwt_access_ttl_seconds,
            "session_id": str(session.id),
        }

    async def logout_self(self, *, session_id: UUID, actor_user_id: UUID) -> dict:
        session = await self._session.get(SessionRow, session_id)
        if not session or session.user_id != actor_user_id:
            raise NotFoundError("session not found")
        await self._revoke_session(session, actor_user_id, clear_refresh=True)
        await self._session.commit()
        return {"message": "Session revoked. Please log in again."}

    async def revoke_session_admin(
        self, *, session_id: UUID, caller_user_id: UUID, tenant_id: UUID
    ) -> dict:
        if not await self._authz.has_tenant_permission(caller_user_id, tenant_id, "tenant.admin"):
            raise ForbiddenError("forbidden")
        session = await self._session.get(SessionRow, session_id)
        if not session:
            raise NotFoundError("session not found")
        if not await self._authz.session_belongs_to_tenant(session.user_id, tenant_id):
            raise ForbiddenError("forbidden")
        await self._revoke_session(session, caller_user_id, clear_refresh=True)
        await self._session.commit()
        return {
            "session_id": str(session.id),
            "status": session.status,
            "revoked_at": session.revoked_at.isoformat() if session.revoked_at else None,
        }

    async def revoke_other_sessions(self, *, current_session_id: UUID, user_id: UUID) -> dict:
        result = await self._session.execute(
            select(SessionRow).where(
                SessionRow.user_id == user_id,
                SessionRow.status == "active",
                SessionRow.id != current_session_id,
            )
        )
        sessions = result.scalars().all()
        for session in sessions:
            await self._revoke_session(session, user_id, clear_refresh=True)
        await self._session.commit()
        return {"revoked_count": len(sessions), "message": f"{len(sessions)} sessions revoked"}

    async def revoke_principal_access(
        self, *, target_user_id: UUID, caller_user_id: UUID, tenant_id: UUID
    ) -> dict:
        """
        Tenant-admin hard revoke: lock principal + user and kill all sessions/refresh tokens.
        Next API call fails resolve; AuthZ also denies inactive principal.
        """
        if not await self._authz.has_tenant_permission(caller_user_id, tenant_id, "tenant.admin"):
            raise ForbiddenError("forbidden")
        if not await self._authz.session_belongs_to_tenant(target_user_id, tenant_id):
            raise ForbiddenError("forbidden")

        user = await self._session.get(UserRow, target_user_id)
        if not user:
            raise NotFoundError("user not found")

        principal = await self._session.get(PrincipalRow, user.principal_id)
        if principal:
            principal.status = "locked"
        user.status = "locked"

        result = await self._session.execute(
            select(SessionRow).where(SessionRow.user_id == user.id, SessionRow.status == "active")
        )
        sessions = result.scalars().all()
        for session in sessions:
            await self._revoke_session(session, caller_user_id, clear_refresh=True)

        await self._audit("user.access_revoked", actor_user_id=caller_user_id, tenant_id=tenant_id)
        await self._session.commit()
        return {
            "user_id": str(user.id),
            "principal_id": str(user.principal_id),
            "status": user.status,
            "sessions_revoked": len(sessions),
            "message": "Access revoked. Existing access tokens fail on next request.",
        }

    async def password_reset_request(self, *, email: str) -> dict:
        user = await self._get_user_by_email(email)
        if user and user.status == "active":
            token_id = uuid.uuid4()
            secret = secrets.token_urlsafe(32)
            composite = make_reset_token_composite(str(token_id), secret)
            self._session.add(
                PasswordResetTokenRow(
                    id=token_id,
                    user_id=user.id,
                    token_hash=hash_secret(secret),
                    expires_at=utcnow() + timedelta(minutes=settings.reset_token_ttl_minutes),
                )
            )
            delivery = DeliverySecretRow(
                id=uuid.uuid4(),
                purpose="password_reset_email",
                secret_plain=composite,
                expires_at=utcnow() + timedelta(minutes=settings.reset_token_ttl_minutes),
            )
            self._session.add(delivery)
            self._session.add(
                OutboxEventRow(
                    id=uuid.uuid4(),
                    type="send_password_reset_email",
                    payload_json={
                        "email": user.email,
                        "reset_token_id": str(token_id),
                        "delivery_secret_id": str(delivery.id),
                    },
                    status="pending",
                )
            )
            await self._session.commit()
        return {"message": "If that email exists, a reset link has been sent."}

    async def password_reset(self, *, reset_token: str, new_password: str) -> dict:
        """C2: commit local revoke/token-used first, then Keycloak set_password."""
        validate_password(new_password)
        token_row = await self._find_valid_reset_token(reset_token)
        if not token_row:
            raise ValidationError("token invalid or expired")

        user = await self._session.get(UserRow, token_row.user_id)
        if not user:
            raise ValidationError("token invalid or expired")

        cred = await self._session.execute(
            select(CredentialRow)
            .where(CredentialRow.principal_id == user.principal_id, CredentialRow.status == "active")
            .limit(1)
        )
        credential = cred.scalar_one_or_none()
        if not credential:
            raise ValidationError("token invalid or expired")

        realm = await self._session.get(IdentityRealmRow, credential.identity_realm_id)
        if not realm:
            raise ValidationError("token invalid or expired")

        now = utcnow()
        token_row.used_at = now
        result = await self._session.execute(
            select(SessionRow).where(SessionRow.user_id == user.id, SessionRow.status == "active")
        )
        sessions = result.scalars().all()
        for session in sessions:
            session.status = "revoked"
            session.revoked_at = now
            session.refresh_token_hash = None

        user.updated_at = now
        await self._audit("user.password_reset", actor_user_id=user.id)
        if sessions:
            await self._audit("user.sessions_revoked", actor_user_id=user.id)

        try:
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise

        try:
            await self._keycloak.set_password(realm.realm_name, credential.keycloak_subject, new_password)
        except Exception:
            self._session.add(
                OutboxEventRow(
                    id=uuid.uuid4(),
                    type="retry_keycloak_set_password",
                    payload_json={
                        "user_id": str(user.id),
                        "realm": realm.realm_name,
                        "subject": credential.keycloak_subject,
                    },
                    status="pending",
                )
            )
            await self._session.commit()
            raise

        return {
            "message": "Password updated. All sessions revoked. Please log in again.",
            "sessions_revoked": len(sessions),
        }

    async def resolve_user_from_access_token(self, token: str) -> tuple[UserRow, SessionRow, CredentialRow]:
        try:
            unverified = jwt.get_unverified_claims(token)
            issuer = unverified.get("iss")
            decode_kwargs: dict = {
                "algorithms": [settings.jwt_algorithm],
                "options": {"verify_exp": True},
            }
            if issuer:
                decode_kwargs["issuer"] = issuer
            payload = jwt.decode(token, settings.jwt_secret, **decode_kwargs)
        except JWTError as exc:
            raise UnauthorizedError("invalid token") from exc

        sid = payload.get("sid")
        sub = payload.get("sub")
        iss = payload.get("iss")
        if not sid or not sub or not iss:
            raise UnauthorizedError("invalid token")

        realm = await self._session.execute(
            select(IdentityRealmRow).where(
                (IdentityRealmRow.issuer == iss) | (IdentityRealmRow.issuer_url == iss)
            )
        )
        realm_row = realm.scalar_one_or_none()
        if not realm_row:
            raise UnauthorizedError("invalid token")

        session = await self._session.get(SessionRow, UUID(str(sid)))
        if not session or session.status != "active":
            raise UnauthorizedError("invalid token")
        if session.expires_at < utcnow():
            raise UnauthorizedError("invalid token")

        cred_result = await self._session.execute(
            select(CredentialRow).where(
                CredentialRow.keycloak_subject == sub,
                CredentialRow.identity_realm_id == realm_row.id,
                CredentialRow.status == "active",
            )
        )
        credential = cred_result.scalar_one_or_none()
        if not credential:
            raise UnauthorizedError("invalid token")

        user = await self._session.execute(
            select(UserRow).where(UserRow.principal_id == credential.principal_id)
        )
        user_row = user.scalar_one_or_none()
        if not user_row or user_row.status != "active":
            raise UnauthorizedError("invalid token")
        if session.user_id != user_row.id:
            raise UnauthorizedError("invalid token")

        principal = await self._session.get(PrincipalRow, user_row.principal_id)
        if not principal or principal.status != "active":
            raise UnauthorizedError("invalid token")

        return user_row, session, credential

    async def _issue_tokens(self, user: UserRow, kc_subject: str, issuer: str) -> TokenPair:
        """
        Multi-tenant marketplace login tokens:
        - access JWT is lean (sub/iss/exp/sid/typ/uid/pid) — NEVER roles or permissions
        - refresh is opaque, stored hashed, rotated on use
        """
        refresh = secrets.token_urlsafe(48)
        session = SessionRow(
            id=uuid.uuid4(),
            user_id=user.id,
            status="active",
            refresh_token_hash=hash_secret(refresh),
            expires_at=refresh_expires_at(),
            last_active_at=utcnow(),
        )
        self._session.add(session)

        user.last_login_at = utcnow()
        access = self._build_access_token(
            sub=kc_subject,
            iss=issuer,
            sid=session.id,
            typ="user",
            uid=str(user.id),
            pid=str(user.principal_id),
        )
        await self._audit("user.login", actor_user_id=user.id)
        await self._session.commit()

        return TokenPair(
            access_token=access,
            refresh_token=refresh,
            expires_in=settings.jwt_access_ttl_seconds,
            session_id=session.id,
            user_id=user.id,
            principal_id=user.principal_id,
        )

    def _build_access_token(
        self, *, sub: str, iss: str, sid: UUID, typ: str, uid: str, pid: str
    ) -> str:
        expire = utcnow() + timedelta(seconds=settings.jwt_access_ttl_seconds)
        return jwt.encode(
            {
                "sub": sub,
                "iss": iss,
                "exp": expire,
                "sid": str(sid),
                "typ": typ,
                # Identity anchors for clients — not authorization grants
                "uid": uid,
                "pid": pid,
            },
            settings.jwt_secret,
            algorithm=settings.jwt_algorithm,
        )

    async def _revoke_session(
        self, session: SessionRow, actor_user_id: UUID, *, clear_refresh: bool = True
    ) -> None:
        session.status = "revoked"
        session.revoked_at = utcnow()
        if clear_refresh:
            session.refresh_token_hash = None
        await self._audit("user.session_revoked", actor_user_id=actor_user_id)

    async def _get_platform_realm(self) -> IdentityRealmRow:
        realm = await self._get_realm_by_name(settings.platform_realm_name)
        if not realm:
            raise NotFoundError("platform realm not configured")
        return realm

    async def _get_realm_by_name(self, realm_name: str) -> IdentityRealmRow | None:
        result = await self._session.execute(
            select(IdentityRealmRow).where(IdentityRealmRow.realm_name == realm_name)
        )
        return result.scalar_one_or_none()

    async def _get_user_by_email(self, email: str) -> UserRow | None:
        result = await self._session.execute(
            select(UserRow).where(UserRow.normalized_email == email.lower())
        )
        return result.scalar_one_or_none()

    async def _latest_verification_token(self, user_id: UUID) -> VerificationTokenRow | None:
        result = await self._session.execute(
            select(VerificationTokenRow)
            .where(VerificationTokenRow.user_id == user_id)
            .order_by(VerificationTokenRow.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _find_valid_reset_token(self, reset_token: str) -> PasswordResetTokenRow | None:
        parts = split_reset_token(reset_token)
        if not parts:
            return None
        token_id_str, secret = parts
        try:
            token_id = UUID(token_id_str)
        except ValueError:
            return None
        row = await self._session.get(PasswordResetTokenRow, token_id)
        if not row or row.used_at is not None:
            return None
        if row.expires_at < utcnow():
            return None
        if not verify_secret(secret, row.token_hash):
            return None
        return row

    async def _audit(
        self,
        event_action: str,
        *,
        actor_user_id: UUID | None = None,
        tenant_id: UUID | None = None,
    ) -> None:
        self._session.add(
            AuditLogRow(
                id=uuid.uuid4(),
                event_action=event_action,
                actor_user_id=actor_user_id,
                tenant_id=tenant_id,
                payload_json={},
            )
        )
