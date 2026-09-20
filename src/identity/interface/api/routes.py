from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status

from identity.application.identity_service import IdentityApplicationService
from identity.interface.api.dependencies import CurrentAuthDep, get_identity_service
from identity.interface.api.schemas import (
    MessageResponse,
    PasswordResetBody,
    PasswordResetRequestBody,
    PasswordResetResponse,
    RefreshRequest,
    RefreshResponse,
    RegisterRequest,
    RegisterResponse,
    RevokeAccessResponse,
    RevokeOthersResponse,
    RevokeSessionAdminResponse,
    TokenRequest,
    TokenResponse,
    VerifyEmailRequest,
    VerifyEmailResponse,
)
from shared.domain.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)

router = APIRouter(tags=["auth"])


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, NotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ValidationError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, ForbiddenError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, UnauthorizedError):
        return HTTPException(status_code=401, detail=str(exc))
    raise exc


@router.post("/auth/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    service: Annotated[IdentityApplicationService, Depends(get_identity_service)],
) -> RegisterResponse:
    try:
        result = await service.register_user(
            email=body.email,
            password=body.password,
            display_name=body.display_name,
            agreed_to_terms=body.agreed_to_terms,
        )
        return RegisterResponse(**result)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/auth/verify-email", response_model=VerifyEmailResponse)
async def verify_email(
    body: VerifyEmailRequest,
    service: Annotated[IdentityApplicationService, Depends(get_identity_service)],
) -> VerifyEmailResponse:
    try:
        result = await service.verify_email(email=body.email, otp_code=body.otp_code)
        return VerifyEmailResponse(**result)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/auth/token", response_model=TokenResponse)
async def login(
    body: TokenRequest,
    service: Annotated[IdentityApplicationService, Depends(get_identity_service)],
) -> TokenResponse:
    try:
        pair = await service.login(email=body.email, password=body.password, realm_hint=body.realm_hint)
        return TokenResponse(
            access_token=pair.access_token,
            refresh_token=pair.refresh_token,
            expires_in=pair.expires_in,
            session_id=str(pair.session_id),
            user_id=str(pair.user_id),
            principal_id=str(pair.principal_id),
        )
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/auth/token/refresh", response_model=RefreshResponse)
async def refresh_token(
    body: RefreshRequest,
    service: Annotated[IdentityApplicationService, Depends(get_identity_service)],
) -> RefreshResponse:
    try:
        result = await service.refresh_token(
            refresh_token=body.refresh_token, session_id=UUID(body.session_id)
        )
        return RefreshResponse(**result)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.delete("/auth/session", response_model=MessageResponse)
async def logout_self(
    auth: CurrentAuthDep,
    service: Annotated[IdentityApplicationService, Depends(get_identity_service)],
) -> MessageResponse:
    user, session, _ = auth
    try:
        result = await service.logout_self(session_id=session.id, actor_user_id=user.id)
        return MessageResponse(**result)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.delete("/auth/sessions/{session_id}", response_model=RevokeSessionAdminResponse)
async def revoke_session_admin(
    session_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[IdentityApplicationService, Depends(get_identity_service)],
    x_tenant_id: Annotated[str | None, Header()] = None,
) -> RevokeSessionAdminResponse:
    if not x_tenant_id:
        raise HTTPException(status_code=422, detail="X-Tenant-Id header required")
    caller, _, _ = auth
    try:
        result = await service.revoke_session_admin(
            session_id=session_id,
            caller_user_id=caller.id,
            tenant_id=UUID(x_tenant_id),
        )
        return RevokeSessionAdminResponse(**result)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.delete("/auth/sessions", response_model=RevokeOthersResponse)
async def revoke_other_sessions(
    auth: CurrentAuthDep,
    service: Annotated[IdentityApplicationService, Depends(get_identity_service)],
) -> RevokeOthersResponse:
    user, session, _ = auth
    try:
        result = await service.revoke_other_sessions(
            current_session_id=session.id, user_id=user.id
        )
        return RevokeOthersResponse(**result)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/auth/users/{user_id}/revoke-access", response_model=RevokeAccessResponse)
async def revoke_user_access(
    user_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[IdentityApplicationService, Depends(get_identity_service)],
    x_tenant_id: Annotated[str | None, Header()] = None,
) -> RevokeAccessResponse:
    """Tenant-admin: lock principal/user and revoke all sessions (immediate next-request denial)."""
    if not x_tenant_id:
        raise HTTPException(status_code=422, detail="X-Tenant-Id header required")
    caller, _, _ = auth
    try:
        result = await service.revoke_principal_access(
            target_user_id=user_id,
            caller_user_id=caller.id,
            tenant_id=UUID(x_tenant_id),
        )
        return RevokeAccessResponse(**result)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/auth/password/reset-request", response_model=MessageResponse)
async def password_reset_request(
    body: PasswordResetRequestBody,
    service: Annotated[IdentityApplicationService, Depends(get_identity_service)],
) -> MessageResponse:
    result = await service.password_reset_request(email=body.email)
    return MessageResponse(**result)


@router.post("/auth/password/reset", response_model=PasswordResetResponse)
async def password_reset(
    body: PasswordResetBody,
    service: Annotated[IdentityApplicationService, Depends(get_identity_service)],
) -> PasswordResetResponse:
    try:
        result = await service.password_reset(reset_token=body.reset_token, new_password=body.new_password)
        return PasswordResetResponse(**result)
    except Exception as exc:
        raise _http_error(exc) from exc
