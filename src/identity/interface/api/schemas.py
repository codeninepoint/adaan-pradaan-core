from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    display_name: str
    agreed_to_terms: bool


class RegisterResponse(BaseModel):
    user_id: str
    org_id: str
    tenant_id: str
    status: str
    verification_email_sent: bool
    # Present only when TENANT_APP_ENV is dev/test (email delivery not wired).
    dev_otp: str | None = None


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    otp_code: str = Field(min_length=6, max_length=6)


class VerifyEmailResponse(BaseModel):
    user_id: str
    status: str
    message: str


class TokenRequest(BaseModel):
    email: EmailStr
    password: str
    realm_hint: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int
    session_id: str
    user_id: str
    principal_id: str


class RefreshRequest(BaseModel):
    refresh_token: str
    session_id: str


class RefreshResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    session_id: str


class MessageResponse(BaseModel):
    message: str


class RevokeSessionAdminResponse(BaseModel):
    session_id: str
    status: str
    revoked_at: str | None


class RevokeOthersResponse(BaseModel):
    revoked_count: int
    message: str


class RevokeAccessResponse(BaseModel):
    user_id: str
    principal_id: str
    status: str
    sessions_revoked: int
    message: str


class PasswordResetRequestBody(BaseModel):
    email: EmailStr


class PasswordResetRequestResponse(BaseModel):
    message: str
    # Present only when TENANT_APP_ENV is dev/test (email delivery not wired).
    dev_reset_token: str | None = None


class PasswordResetBody(BaseModel):
    reset_token: str
    new_password: str


class PasswordResetResponse(BaseModel):
    message: str
    sessions_revoked: int | None = None


class MeOrganization(BaseModel):
    org_id: str
    name: str
    org_type: str
    participation: str = "consumer"
    keycloak_realm_ref: str | None = None
    membership_role: str
    status: str


class MeTenant(BaseModel):
    tenant_id: str
    org_id: str
    name: str
    slug: str
    status: str
    membership_status: str


class MeResponse(BaseModel):
    user_id: str
    principal_id: str
    email: str
    display_name: str
    status: str
    is_platform_operator: bool = False
    organizations: list[MeOrganization]
    tenants: list[MeTenant]
