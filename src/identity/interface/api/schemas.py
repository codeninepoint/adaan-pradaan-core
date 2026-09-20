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


class PasswordResetBody(BaseModel):
    reset_token: str
    new_password: str


class PasswordResetResponse(BaseModel):
    message: str
    sessions_revoked: int | None = None
