"""Pydantic request/response shapes. Kept next to the SQL so the schema package is
the single source; TS types for /web are generated from the OpenAPI spec."""
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

Stage = Literal["pre_seed", "seed", "series_a", "series_b", "later"]
JobType = Literal["post", "reply", "page", "launch_task", "outreach", "site_change", "tool", "heartbeat"]
JobState = Literal["pending", "approved", "edited", "rejected", "executed", "failed"]
Channel = Literal["linkedin", "x", "web", "email", "internal"]


class CompanyIn(BaseModel):
    name: str
    domain: str | None = None
    stage: Stage | None = None
    founders: list[dict] = Field(default_factory=list)


class CompanyOut(CompanyIn):
    id: UUID
    product_summary: str | None = None
    plan_tier: str
    status: str
    created_at: datetime


class JobIn(BaseModel):
    company_id: UUID
    type: JobType
    channel: Channel | None = None
    format: str | None = None
    input: dict = Field(default_factory=dict)
    output: dict = Field(default_factory=dict)
    founder_id: UUID | None = None
    plan_id: UUID | None = None
    scheduled_for: datetime | None = None


class JobOut(BaseModel):
    id: UUID
    company_id: UUID
    type: str
    channel: str | None
    format: str | None
    input: dict
    output: dict
    state: str
    voice_match: float | None
    scheduled_for: datetime | None
    executed_at: datetime | None
    platform_ref: str | None
    error: str | None
    created_at: datetime


class JobDecision(BaseModel):
    """The founder's one tap. `edited_output` present ⇒ state 'edited' and a diff is stored."""
    decision: Literal["approve", "reject"]
    edited_output: dict | None = None


class MetricOut(BaseModel):
    date: date
    name: str
    value: float
    source: str
    job_id: UUID | None = None
