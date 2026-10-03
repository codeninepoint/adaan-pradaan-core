from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.domain.security import utcnow
from identity.infrastructure.models import AuditLogRow
from marketplace.application.access import require_vendor_owner
from shared.domain.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from tenant.infrastructure.models import OrgMembershipRow, OrganizationRow
from vendor.infrastructure.models import (
    SupportRequestRow,
    VendorProfileRow,
    VendorSettingsRow,
    VendorVerificationRow,
)

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_IFSC = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")

REQUIREMENTS = ("business_registration_doc", "bank_account", "tax_id")


def _mask_account(value: str) -> str:
    if len(value) <= 4:
        return value
    return "X" * (len(value) - 4) + value[-4:]


@dataclass(frozen=True, slots=True)
class EligibilityResult:
    eligible: bool
    reasons: list[str]
    requirements: list[str]
    vendor_id: UUID | None = None
    vendor_status: str | None = None
    submitted_at: str | None = None
    verification_id: UUID | None = None
    verification_status: str | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class VendorProfileView:
    vendor_id: UUID
    org_id: UUID
    status: str
    legal_name: str


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
class VendorSettingsView:
    vendor_id: UUID
    status: str
    legal_name: str
    tax_id: str | None
    support_email: str
    bank_account_name: str
    bank_account_number: str
    bank_ifsc: str
    notify_install: bool
    notify_payout: bool


@dataclass(frozen=True, slots=True)
class SupportRequestView:
    request_id: UUID
    subject: str
    message: str
    status: str
    created_at: str


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
        vendor = (
            await self._session.execute(
                select(VendorProfileRow).where(VendorProfileRow.organization_id == org_id)
            )
        ).scalar_one_or_none()
        verification = None
        if vendor is not None:
            reasons.append("Organization already has a vendor profile")
            verification = (
                await self._session.execute(
                    select(VendorVerificationRow)
                    .where(VendorVerificationRow.vendor_id == vendor.id)
                    .order_by(VendorVerificationRow.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
        eligible = len(reasons) == 0
        return EligibilityResult(
            eligible=eligible,
            reasons=reasons,
            requirements=list(REQUIREMENTS) if eligible else [],
            vendor_id=vendor.id if vendor else None,
            vendor_status=vendor.status if vendor else None,
            submitted_at=vendor.created_at.isoformat() if vendor and vendor.created_at else None,
            verification_id=verification.id if verification else None,
            verification_status=verification.status if verification else None,
            notes=verification.notes if verification else None,
        )

    async def profile_for_org(self, *, org_id: UUID, caller_user_id: UUID) -> VendorProfileView:
        await self._require_org_owner(org_id, caller_user_id)
        vendor = (
            await self._session.execute(
                select(VendorProfileRow).where(VendorProfileRow.organization_id == org_id)
            )
        ).scalar_one_or_none()
        if vendor is None:
            raise NotFoundError("vendor not found")
        return VendorProfileView(
            vendor_id=vendor.id,
            org_id=vendor.organization_id,
            status=vendor.status,
            legal_name=vendor.legal_name,
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

    async def get_settings(self, *, vendor_id: UUID, caller_user_id: UUID) -> VendorSettingsView:
        vendor = await require_vendor_owner(self._session, vendor_id, caller_user_id)
        row = await self._session.get(VendorSettingsRow, vendor_id)
        return self._settings_view(vendor, row)

    async def update_settings(
        self,
        *,
        vendor_id: UUID,
        caller_user_id: UUID,
        support_email: str | None = None,
        bank_account_name: str | None = None,
        bank_account_number: str | None = None,
        bank_ifsc: str | None = None,
        notify_install: bool | None = None,
        notify_payout: bool | None = None,
    ) -> VendorSettingsView:
        vendor = await require_vendor_owner(self._session, vendor_id, caller_user_id)
        row = await self._session.get(VendorSettingsRow, vendor_id)
        if row is None:
            row = VendorSettingsRow(
                vendor_id=vendor.id,
                support_email="",
                bank_account_name="",
                bank_account_number="",
                bank_ifsc="",
                notify_install=True,
                notify_payout=True,
            )
            self._session.add(row)
        if support_email is not None:
            email = support_email.strip()
            if not _EMAIL.match(email):
                raise ValidationError("invalid email")
            row.support_email = email
        if bank_account_name is not None:
            name = bank_account_name.strip()
            if not name:
                raise ValidationError("bank account name is required")
            row.bank_account_name = name
        if bank_account_number is not None:
            number = bank_account_number.strip()
            if number != _mask_account(row.bank_account_number):
                if len(number) < 4:
                    raise ValidationError("bank account number is invalid")
                row.bank_account_number = number
        if bank_ifsc is not None:
            ifsc = bank_ifsc.strip().upper()
            if not _IFSC.match(ifsc):
                raise ValidationError("invalid IFSC")
            row.bank_ifsc = ifsc
        if notify_install is not None:
            row.notify_install = notify_install
        if notify_payout is not None:
            row.notify_payout = notify_payout
        row.updated_at = utcnow()
        self._session.add(
            AuditLogRow(
                id=uuid.uuid4(),
                event_action="vendor.settings_updated",
                actor_user_id=caller_user_id,
                payload_json={"vendor_id": str(vendor.id)},
            )
        )
        view = self._settings_view(vendor, row)
        await self._session.commit()
        return view

    async def create_support_request(
        self, *, vendor_id: UUID, caller_user_id: UUID, subject: str, message: str
    ) -> SupportRequestView:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        subject = subject.strip()
        message = message.strip()
        if not subject or not message:
            raise ValidationError("subject and message are required")
        created_at = utcnow()
        row = SupportRequestRow(
            id=uuid.uuid4(),
            vendor_id=vendor_id,
            subject=subject,
            message=message,
            status="open",
            created_at=created_at,
        )
        self._session.add(row)
        self._session.add(
            AuditLogRow(
                id=uuid.uuid4(),
                event_action="vendor.support_requested",
                actor_user_id=caller_user_id,
                payload_json={"vendor_id": str(vendor_id), "request_id": str(row.id)},
            )
        )
        await self._session.commit()
        return SupportRequestView(
            request_id=row.id,
            subject=subject,
            message=message,
            status="open",
            created_at=created_at.isoformat(),
        )

    async def list_support_requests(
        self, *, vendor_id: UUID, caller_user_id: UUID
    ) -> list[SupportRequestView]:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        rows = (
            await self._session.execute(
                select(SupportRequestRow)
                .where(SupportRequestRow.vendor_id == vendor_id)
                .order_by(SupportRequestRow.created_at.desc())
            )
        ).scalars().all()
        return [
            SupportRequestView(
                request_id=row.id,
                subject=row.subject,
                message=row.message,
                status=row.status,
                created_at=row.created_at.isoformat() if row.created_at else "",
            )
            for row in rows
        ]

    def _settings_view(self, vendor: VendorProfileRow, row: VendorSettingsRow | None) -> VendorSettingsView:
        return VendorSettingsView(
            vendor_id=vendor.id,
            status=vendor.status,
            legal_name=vendor.legal_name,
            tax_id=vendor.tax_id,
            support_email=row.support_email if row else "",
            bank_account_name=row.bank_account_name if row else "",
            bank_account_number=_mask_account(row.bank_account_number) if row else "",
            bank_ifsc=row.bank_ifsc if row else "",
            notify_install=row.notify_install if row else True,
            notify_payout=row.notify_payout if row else True,
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
