from __future__ import annotations

from pydantic import BaseModel, Field


class VendorEligibilityResponse(BaseModel):
    eligible: bool
    reasons: list[str]
    requirements: list[str]


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


class VendorDecisionResponse(BaseModel):
    verification_id: str
    vendor_id: str
    status: str
    decided_by: str
    decided_at: str
