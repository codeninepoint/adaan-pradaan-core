from __future__ import annotations

from pydantic import BaseModel, Field


class CreateResourceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    resource_type: str = Field(min_length=1, max_length=128)
    external_ref: str | None = Field(default=None, max_length=512)


class CreateResourceResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    resource_type: str
    status: str
