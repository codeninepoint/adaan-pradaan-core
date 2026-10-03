from __future__ import annotations

from pydantic import BaseModel, Field


class VendorEligibilityResponse(BaseModel):
    eligible: bool
    reasons: list[str]
    requirements: list[str]
    vendor_id: str | None = None
    vendor_status: str | None = None
    submitted_at: str | None = None
    verification_id: str | None = None
    verification_status: str | None = None
    notes: str | None = None


class VendorRegisterRequest(BaseModel):
    legal_name: str = Field(min_length=1, max_length=255)
    tax_id: str = Field(min_length=1, max_length=128)
    payout_bank_account: str = Field(min_length=1, max_length=255)
    contact_email: str = Field(min_length=3, max_length=255)
    business_doc_url: str = Field(min_length=1, max_length=1024)


class VendorProfileResponse(BaseModel):
    vendor_id: str
    org_id: str
    status: str
    legal_name: str


class VendorRegisterResponse(BaseModel):
    vendor_id: str
    org_id: str
    status: str
    verification_id: str


class VendorVerificationResponse(BaseModel):
    vendor_id: str
    status: str
    submitted_at: str
    verification_id: str | None = None
    verification_status: str | None = None
    notes: str | None = None


class VendorVerificationQueueItem(BaseModel):
    verification_id: str
    vendor_id: str
    legal_name: str
    contact_email: str
    org_id: str
    status: str
    submitted_at: str
    business_doc_url: str | None = None


class VendorVerificationQueueResponse(BaseModel):
    items: list[VendorVerificationQueueItem]


class VendorDecisionRequest(BaseModel):
    decision: str
    notes: str | None = None


class VendorSettingsResponse(BaseModel):
    vendor_id: str
    status: str
    legal_name: str
    tax_id: str | None
    support_email: str
    bank_account_name: str
    bank_account_number: str
    bank_ifsc: str
    notify_install: bool
    notify_payout: bool


class VendorSettingsPatch(BaseModel):
    support_email: str | None = None
    bank_account_name: str | None = None
    bank_account_number: str | None = None
    bank_ifsc: str | None = None
    notify_install: bool | None = None
    notify_payout: bool | None = None


class SupportRequestBody(BaseModel):
    subject: str = Field(min_length=1, max_length=255)
    message: str = Field(min_length=1, max_length=4000)


class SupportRequestResponse(BaseModel):
    request_id: str
    subject: str
    message: str
    status: str
    created_at: str


class SupportRequestListResponse(BaseModel):
    requests: list[SupportRequestResponse]


class VendorDecisionResponse(BaseModel):
    verification_id: str
    vendor_id: str
    status: str
    decided_by: str
    decided_at: str
