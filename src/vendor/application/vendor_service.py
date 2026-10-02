from __future__ import annotations

import uuid
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.domain.security import utcnow
from identity.infrastructure.models import AuditLogRow
from shared.domain.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from tenant.infrastructure.models import OrgMembershipRow, OrganizationRow
from vendor.infrastructure.models import VendorProfileRow, VendorVerificationRow

REQUIREMENTS = ("business_registration_doc", "bank_account", "tax_id")


@dataclass(frozen=True, slots=True)
class EligibilityResult:
    eligible: bool
    reasons: list[str]
    requirements: list[str]


@dataclass(frozen=True, slots=True)
class VendorRegisterResult:
    vendor_id: UUID
    org_id: UUID
    status: str
    verification_id: UUID


@dataclass(frozen=True, slots=True)
class VerificationStatus:
    vendor_id: UUID
    status: str
    submitted_at: str
    verification_id: UUID | None
    verification_status: str | None
    notes: str | None


@dataclass(frozen=True, slots=True)
class QueuedVerification:
    verification_id: UUID
    vendor_id: UUID
    legal_name: str
    contact_email: str
    org_id: UUID
    status: str
    submitted_at: str
    business_doc_url: str | None


@dataclass(frozen=True, slots=True)
class VerificationDecision:
    verification_id: UUID
    vendor_id: UUID
    status: str
    decided_by: UUID
    decided_at: str


class VendorService:
    """J20–J22 vendor eligibility, registration, and verification."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def eligibility(self, *, org_id: UUID, caller_user_id: UUID) -> EligibilityResult:
        await self._require_org_owner(org_id, caller_user_id)
        reasons: list[str] = []
        existing = (
            await self._session.execute(
                select(VendorProfileRow.id).where(VendorProfileRow.organization_id == org_id)
            )
        ).scalar_one_or_none()
        if existing is not None:
            reasons.append("Organization already has a vendor profile")
        eligible = len(reasons) == 0
        return EligibilityResult(
            eligible=eligible,
            reasons=reasons,
            requirements=list(REQUIREMENTS) if eligible else [],
        )

    async def register(
        self,
        *,
        org_id: UUID,
        caller_user_id: UUID,
        legal_name: str,
        tax_id: str | None,
        payout_bank_account: str | None,
        contact_email: str,
        business_doc_url: str | None,
    ) -> VendorRegisterResult:
        org = await self._require_org_owner(org_id, caller_user_id)

        existing = (
            await self._session.execute(
                select(VendorProfileRow).where(VendorProfileRow.organization_id == org_id)
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise ConflictError("org already has a vendor profile")

        legal_name = legal_name.strip()
        contact_email = contact_email.strip().lower()
        if not legal_name or not contact_email or "@" not in contact_email:
            raise ValidationError("legal_name and contact_email are required")
        if not business_doc_url or not business_doc_url.strip():
            raise ValidationError("missing required document")
        if not tax_id or not tax_id.strip():
            raise ValidationError("tax_id is required")
        if not payout_bank_account or not payout_bank_account.strip():
            raise ValidationError("payout_bank_account is required")

        vendor = VendorProfileRow(
            id=uuid.uuid4(),
            organization_id=org_id,
            legal_name=legal_name,
            tax_id=tax_id.strip(),
            payout_bank_account=payout_bank_account.strip(),
            contact_email=contact_email,
            business_doc_url=business_doc_url.strip(),
            status="pending_verification",
        )
        self._session.add(vendor)
        await self._session.flush()

        verification = VendorVerificationRow(
            id=uuid.uuid4(),
            vendor_id=vendor.id,
            status="queued",
        )
        self._session.add(verification)

        org.participation = "consumer_and_vendor"

        self._session.add(
            AuditLogRow(
                id=uuid.uuid4(),
                event_action="vendor.registered",
                actor_user_id=caller_user_id,
                payload_json={
                    "vendor_id": str(vendor.id),
                    "org_id": str(org_id),
                    "verification_id": str(verification.id),
                },
            )
        )
        await self._session.commit()
        return VendorRegisterResult(
            vendor_id=vendor.id,
            org_id=org_id,
            status="pending_verification",
            verification_id=verification.id,
        )

    async def get_verification(
        self, *, vendor_id: UUID, caller_user_id: UUID
    ) -> VerificationStatus:
        vendor = await self._session.get(VendorProfileRow, vendor_id)
        if vendor is None:
            raise NotFoundError("vendor not found")
        await self._require_org_owner(vendor.organization_id, caller_user_id)
        verification = (
            await self._session.execute(
                select(VendorVerificationRow)
                .where(VendorVerificationRow.vendor_id == vendor_id)
                .order_by(VendorVerificationRow.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        return VerificationStatus(
            vendor_id=vendor.id,
            status=vendor.status,
            submitted_at=vendor.created_at.isoformat() if vendor.created_at else "",
            verification_id=verification.id if verification else None,
            verification_status=verification.status if verification else None,
            notes=verification.notes if verification else None,
        )

    async def list_queued(self, *, caller_user_id: UUID) -> list[QueuedVerification]:
        await self._require_platform_operator(caller_user_id)
        rows = (
            await self._session.execute(
                select(VendorVerificationRow, VendorProfileRow)
                .join(VendorProfileRow, VendorProfileRow.id == VendorVerificationRow.vendor_id)
                .where(VendorVerificationRow.status.in_(("queued", "pending")))
                .order_by(VendorVerificationRow.created_at.asc())
            )
        ).all()
        return [
            QueuedVerification(
                verification_id=verification.id,
                vendor_id=profile.id,
                legal_name=profile.legal_name,
                contact_email=profile.contact_email,
                org_id=profile.organization_id,
                status=verification.status,
                submitted_at=verification.created_at.isoformat() if verification.created_at else "",
                business_doc_url=profile.business_doc_url,
            )
            for verification, profile in rows
        ]

    async def decide_verification(
        self,
        *,
        verification_id: UUID,
        caller_user_id: UUID,
        decision: str,
        notes: str | None,
    ) -> VerificationDecision:
        """Dev/MVP decision path: caller must own a platform-operator org."""
        await self._require_platform_operator(caller_user_id)
        if decision not in ("approved", "rejected"):
            raise ValidationError("decision must be approved or rejected")

        verification = await self._session.get(VendorVerificationRow, verification_id)
        if verification is None:
            raise NotFoundError("verification not found")
        if verification.status not in ("queued", "pending"):
            raise ConflictError("already decided")

        vendor = await self._session.get(VendorProfileRow, verification.vendor_id)
        if vendor is None:
            raise NotFoundError("vendor not found")

        now = utcnow()
        verification.status = decision
        verification.notes = notes
        verification.decided_by = caller_user_id
        verification.decided_at = now

        if decision == "approved":
            vendor.status = "verified"
        else:
            vendor.status = "rejected"
            org = await self._session.get(OrganizationRow, vendor.organization_id)
            if org and org.participation == "consumer_and_vendor":
                org.participation = "consumer"

        self._session.add(
            AuditLogRow(
                id=uuid.uuid4(),
                event_action="vendor.verification_decided",
                actor_user_id=caller_user_id,
                payload_json={
                    "verification_id": str(verification_id),
                    "vendor_id": str(vendor.id),
                    "decision": decision,
                },
            )
        )
        await self._session.commit()
        return VerificationDecision(
            verification_id=verification.id,
            vendor_id=vendor.id,
            status=decision,
            decided_by=caller_user_id,
            decided_at=now.isoformat(),
        )

    async def _require_org_owner(self, org_id: UUID, user_id: UUID) -> OrganizationRow:
        org = await self._session.get(OrganizationRow, org_id)
        if org is None:
            raise NotFoundError("organization not found")
        membership = (
            await self._session.execute(
                select(OrgMembershipRow).where(
                    OrgMembershipRow.organization_id == org_id,
                    OrgMembershipRow.user_id == user_id,
                    OrgMembershipRow.role == "owner",
                    OrgMembershipRow.status == "active",
                )
            )
        ).scalar_one_or_none()
        if membership is None:
            raise ForbiddenError("org owner required")
        return org

    async def _require_platform_operator(self, user_id: UUID) -> None:
        row = (
            await self._session.execute(
                select(OrganizationRow.id)
                .join(OrgMembershipRow, OrgMembershipRow.organization_id == OrganizationRow.id)
                .where(
                    OrgMembershipRow.user_id == user_id,
                    OrgMembershipRow.status == "active",
                    OrganizationRow.is_platform_operator.is_(True),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if row is None:
            raise ForbiddenError("platform operator required")
