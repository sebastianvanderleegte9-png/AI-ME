"""Signals: the observable facts the scorecard rules read. Gathered once per company
from intake data, account stats, search and a site walkthrough. Every field has a
default so a missing source degrades a score rather than crashing the diagnostic."""
from dataclasses import dataclass, field
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..interfaces import get_metrics_source, get_social
from ..models import ICP, Company, Founder, VoiceProfile


@dataclass
class FounderSignals:
    founder_id: str
    name: str
    linkedin_followers: int = 0
    linkedin_impressions_30d: int = 0
    linkedin_posts_30d: int = 0
    x_followers: int = 0
    x_impressions_30d: int = 0
    x_posts_30d: int = 0
    past_post_count: int = 0
    has_linkedin: bool = False
    has_x: bool = False


@dataclass
class Signals:
    company_name: str
    stage: str | None
    product_summary: dict = field(default_factory=dict)
    icp: dict = field(default_factory=dict)
    founders: list[FounderSignals] = field(default_factory=list)
    # search
    pages_indexed: int = 0
    search_impressions_30d: int = 0
    has_search_console: bool = False
    data_assets: list[str] = field(default_factory=list)
    # launches
    launches_12m: int = 0
    # onboarding (site walkthrough; Component 10 automates it fully)
    has_self_serve_signup: bool | None = None
    signup_steps: int | None = None
    has_signup_source_field: bool = False
    signups_30d: int = 0
    proof_points: list[str] = field(default_factory=list)


def gather(db: Session, company: Company) -> Signals:
    social, metrics = get_social(), get_metrics_source()
    summary = {}
    if company.product_summary:
        try:
            summary = json.loads(company.product_summary)
        except json.JSONDecodeError:
            summary = {"raw": company.product_summary}
    icp = db.scalars(select(ICP).where(ICP.company_id == company.id).order_by(ICP.version.desc())).first()
    sig = Signals(company_name=company.name, stage=company.stage, product_summary=summary,
                  icp={"description": icp.description, "firmographics": icp.firmographics,
                       "personas": icp.personas, "version": icp.version} if icp else {},
                  data_assets=summary.get("data_assets", []) if isinstance(summary, dict) else [],
                  proof_points=summary.get("proof_points", []) if isinstance(summary, dict) else [])

    for f in db.scalars(select(Founder).where(Founder.company_id == company.id)):
        fs = FounderSignals(founder_id=str(f.id), name=f.name,
                            has_linkedin=bool(f.linkedin_handle), has_x=bool(f.x_handle))
        for ch, prefix in (("linkedin", "linkedin"), ("x", "x")):
            if not getattr(fs, f"has_{ch}"):
                continue
            try:
                st = social.account_stats(founder_id=str(f.id), channel=ch)
                setattr(fs, f"{prefix}_followers", int(st.get("followers", 0)))
                setattr(fs, f"{prefix}_impressions_30d", int(st.get("impressions_30d", 0)))
                setattr(fs, f"{prefix}_posts_30d", int(st.get("posts_30d", 0)))
            except Exception:  # noqa: BLE001
                pass
        vp = db.scalars(select(VoiceProfile).where(VoiceProfile.founder_id == f.id)).first()
        fs.past_post_count = len(vp.samples) if vp else 0
        sig.founders.append(fs)

    # search + signups from the metrics source (fake until Search Console is connected)
    try:
        from datetime import date, timedelta
        pts = metrics.pull(company_id=str(company.id), since=date.today() - timedelta(days=30), until=date.today())
        sig.search_impressions_30d = int(sum(p.value for p in pts if p.name == "search_impressions"))
        sig.pages_indexed = int(max((p.value for p in pts if p.name == "pages_indexed"), default=0))
        sig.signups_30d = int(sum(p.value for p in pts if p.name == "signups"))
        sig.has_search_console = any(p.source.endswith("search_console") and not p.source.startswith("fake") for p in pts)
    except Exception:  # noqa: BLE001
        pass
    return sig
