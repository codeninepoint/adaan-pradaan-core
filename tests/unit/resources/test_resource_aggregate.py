from __future__ import annotations

import uuid

import pytest

from resources.domain.aggregate import Resource
from shared.domain.exceptions import ValidationError


def test_resource_create_records_event() -> None:
    tenant_id = uuid.uuid4()
    principal_id = uuid.uuid4()
    resource = Resource.create(
        tenant_id=tenant_id,
        name=" db-1 ",
        resource_type="storage.volume",
        created_by_principal_id=principal_id,
    )
    assert resource.name == "db-1"
    assert resource.tenant_id == tenant_id
    assert resource.status == "active"
    events = resource.pull_events()
    assert len(events) == 1
    assert events[0].event_type == "resource.created"


def test_resource_create_rejects_blank_name() -> None:
    with pytest.raises(ValidationError):
        Resource.create(
            tenant_id=uuid.uuid4(),
            name="  ",
            resource_type="compute.cluster",
            created_by_principal_id=uuid.uuid4(),
        )
