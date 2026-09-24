"""SQLAlchemy models mirroring packages/schema/migrations. The SQL is the source of
truth; these are typed handles for the API and workers. Keep column names identical."""
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, REAL, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _uuid() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _ts() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default="now()")


class Company(Base):
    __tablename__ = "company"
    id: Mapped[uuid.UUID] = _uuid()
    name: Mapped[str] = mapped_column(Text)
    domain: Mapped[str | None] = mapped_column(Text)
    stage: Mapped[str | None] = mapped_column(Text)
    product_summary: Mapped[str | None] = mapped_column(Text)
    product_data_sources: Mapped[list] = mapped_column(JSONB, default=list)
    founders: Mapped[list] = mapped_column(JSONB, default=list)
    plan_tier: Mapped[str] = mapped_column(Text, default="design_partner")
    status: Mapped[str] = mapped_column(Text, default="onboarding")
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class Founder(Base):
    __tablename__ = "founder"
    id: Mapped[uuid.UUID] = _uuid()
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("company.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    linkedin_handle: Mapped[str | None] = mapped_column(Text)
    x_handle: Mapped[str | None] = mapped_column(Text)
    voice_profile_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class ICP(Base):
    __tablename__ = "icp"
    id: Mapped[uuid.UUID] = _uuid()
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("company.id", ondelete="CASCADE"))
    description: Mapped[str | None] = mapped_column(Text)
    best_customers: Mapped[list] = mapped_column(JSONB, default=list)
    firmographics: Mapped[dict] = mapped_column(JSONB, default=dict)
    personas: Mapped[list] = mapped_column(JSONB, default=list)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class VoiceProfile(Base):
    __tablename__ = "voice_profile"
    id: Mapped[uuid.UUID] = _uuid()
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("company.id", ondelete="CASCADE"))
    founder_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("founder.id", ondelete="CASCADE"))
    samples: Mapped[list] = mapped_column(JSONB, default=list)
    rules: Mapped[dict] = mapped_column(JSONB, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class Plan(Base):
    __tablename__ = "plan"
    id: Mapped[uuid.UUID] = _uuid()
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("company.id", ondelete="CASCADE"))
    week_start: Mapped[date] = mapped_column(Date)
    scorecard: Mapped[dict] = mapped_column(JSONB, default=dict)
    sequence: Mapped[list] = mapped_column(JSONB, default=list)
    targets: Mapped[dict] = mapped_column(JSONB, default=dict)
    generated_by: Mapped[str] = mapped_column(Text)
    rules_version: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class Job(Base):
    __tablename__ = "job"
    id: Mapped[uuid.UUID] = _uuid()
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("company.id", ondelete="CASCADE"))
    plan_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("plan.id", ondelete="SET NULL"))
    founder_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("founder.id", ondelete="SET NULL"))
    type: Mapped[str] = mapped_column(Text)
    channel: Mapped[str | None] = mapped_column(Text)
    format: Mapped[str | None] = mapped_column(Text)
    input: Mapped[dict] = mapped_column(JSONB, default=dict)
    output: Mapped[dict] = mapped_column(JSONB, default=dict)
    state: Mapped[str] = mapped_column(Text, default="pending")
    voice_match: Mapped[float | None] = mapped_column(REAL)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    platform_ref: Mapped[str | None] = mapped_column(Text)
    approval_diff: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class Metric(Base):
    __tablename__ = "metric"
    id: Mapped[uuid.UUID] = _uuid()
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("company.id", ondelete="CASCADE"))
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("job.id", ondelete="SET NULL"))
    date: Mapped[date] = mapped_column(Date)
    name: Mapped[str] = mapped_column(Text)
    value: Mapped[float] = mapped_column(Numeric)
    source: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class Account(Base):
    __tablename__ = "account"
    id: Mapped[uuid.UUID] = _uuid()
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("company.id", ondelete="CASCADE"))
    platform: Mapped[str] = mapped_column(Text)
    handle: Mapped[str] = mapped_column(Text)
    name: Mapped[str | None] = mapped_column(Text)
    headline: Mapped[str | None] = mapped_column(Text)
    org: Mapped[str | None] = mapped_column(Text)
    cluster: Mapped[str | None] = mapped_column(Text)
    icp_match_score: Mapped[float | None] = mapped_column(REAL)
    follows_count: Mapped[int | None] = mapped_column(Integer)
    interaction: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class Page(Base):
    __tablename__ = "page"
    id: Mapped[uuid.UUID] = _uuid()
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("company.id", ondelete="CASCADE"))
    template_id: Mapped[str] = mapped_column(Text)
    slug: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JSONB, default=dict)
    html_ref: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="draft")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class Outcome(Base):
    __tablename__ = "outcome"
    id: Mapped[uuid.UUID] = _uuid()
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("company.id", ondelete="CASCADE"))
    plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("plan.id", ondelete="CASCADE"))
    week_start: Mapped[date] = mapped_column(Date)
    targets: Mapped[dict] = mapped_column(JSONB, default=dict)
    actuals: Mapped[dict] = mapped_column(JSONB, default=dict)
    delta: Mapped[dict] = mapped_column(JSONB, default=dict)
    approval_rate: Mapped[float | None] = mapped_column(REAL)
    edit_rate: Mapped[float | None] = mapped_column(REAL)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class SignupSource(Base):
    __tablename__ = "signup_source"
    id: Mapped[uuid.UUID] = _uuid()
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("company.id", ondelete="CASCADE"))
    signup_id: Mapped[str | None] = mapped_column(Text)
    answer_text: Mapped[str] = mapped_column(Text)
    classified_channel: Mapped[str | None] = mapped_column(Text)
    classified_by: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()
