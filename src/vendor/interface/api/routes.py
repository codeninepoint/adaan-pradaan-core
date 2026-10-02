from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from identity.interface.api.dependencies import CurrentAuthDep, get_session
from vendor.application.vendor_service import VendorService
from vendor.interface.api.schemas import (
    VendorDecisionRequest,
    VendorDecisionResponse,
    VendorEligibilityResponse,
    VendorProfileResponse,
    VendorRegisterRequest,
    VendorRegisterResponse,
    VendorVerificationQueueItem,
    VendorVerificationQueueResponse,
    VendorVerificationResponse,
)

router = APIRouter(prefix="/api/v1", tags=["vendor"])


def get_vendor_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> VendorService:
    return VendorService(session)


@router.get(
    "/organizations/{org_id}/vendor-eligibility",
    response_model=VendorEligibilityResponse,
)
async def vendor_eligibility(
    org_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[VendorService, Depends(get_vendor_service)],
) -> VendorEligibilityResponse:
    user, _session, _credential = auth
    result = await service.eligibility(org_id=org_id, caller_user_id=user.id)
    return VendorEligibilityResponse(
        eligible=result.eligible,
        reasons=result.reasons,
        requirements=result.requirements,
    )


@router.get(
    "/organizations/{org_id}/vendor",
    response_model=VendorProfileResponse,
)
async def vendor_profile(
    org_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[VendorService, Depends(get_vendor_service)],
) -> VendorProfileResponse:
    user, _session, _credential = auth
    result = await service.profile_for_org(org_id=org_id, caller_user_id=user.id)
    return VendorProfileResponse(
        vendor_id=str(result.vendor_id),
        org_id=str(result.org_id),
        status=result.status,
        legal_name=result.legal_name,
    )


@router.post(
    "/organizations/{org_id}/vendor/register",
    response_model=VendorRegisterResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def vendor_register(
    org_id: UUID,
    body: VendorRegisterRequest,
    auth: CurrentAuthDep,
    service: Annotated[VendorService, Depends(get_vendor_service)],
) -> VendorRegisterResponse:
    user, _session, _credential = auth
    result = await service.register(
        org_id=org_id,
        caller_user_id=user.id,
        legal_name=body.legal_name,
        tax_id=body.tax_id,
        payout_bank_account=body.payout_bank_account,
        contact_email=body.contact_email,
        business_doc_url=body.business_doc_url,
    )
    return VendorRegisterResponse(
        vendor_id=str(result.vendor_id),
        org_id=str(result.org_id),
        status=result.status,
        verification_id=str(result.verification_id),
    )


@router.get(
    "/vendors/{vendor_id}/verification",
    response_model=VendorVerificationResponse,
)
async def vendor_verification(
    vendor_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[VendorService, Depends(get_vendor_service)],
) -> VendorVerificationResponse:
    user, _session, _credential = auth
    result = await service.get_verification(vendor_id=vendor_id, caller_user_id=user.id)
    return VendorVerificationResponse(
        vendor_id=str(result.vendor_id),
        status=result.status,
        submitted_at=result.submitted_at,
        verification_id=str(result.verification_id) if result.verification_id else None,
        verification_status=result.verification_status,
        notes=result.notes,
    )


@router.get(
    "/admin/vendor-verifications",
    response_model=VendorVerificationQueueResponse,
)
async def list_vendor_verifications(
    auth: CurrentAuthDep,
    service: Annotated[VendorService, Depends(get_vendor_service)],
) -> VendorVerificationQueueResponse:
    user, _session, _credential = auth
    rows = await service.list_queued(caller_user_id=user.id)
    return VendorVerificationQueueResponse(
        items=[
            VendorVerificationQueueItem(
                verification_id=str(row.verification_id),
                vendor_id=str(row.vendor_id),
                legal_name=row.legal_name,
                contact_email=row.contact_email,
                org_id=str(row.org_id),
                status=row.status,
                submitted_at=row.submitted_at,
                business_doc_url=row.business_doc_url,
            )
            for row in rows
        ]
    )


@router.post(
    "/admin/vendor-verifications/{verification_id}/decision",
    response_model=VendorDecisionResponse,
)
async def vendor_verification_decision(
    verification_id: UUID,
    body: VendorDecisionRequest,
    auth: CurrentAuthDep,
    service: Annotated[VendorService, Depends(get_vendor_service)],
) -> VendorDecisionResponse:
    user, _session, _credential = auth
    result = await service.decide_verification(
        verification_id=verification_id,
        caller_user_id=user.id,
        decision=body.decision,
        notes=body.notes,
    )
    return VendorDecisionResponse(
        verification_id=str(result.verification_id),
        vendor_id=str(result.vendor_id),
        status=result.status,
        decided_by=str(result.decided_by),
        decided_at=result.decided_at,
    )
