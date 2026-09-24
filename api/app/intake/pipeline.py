"""Intake pipeline (Component 1).

  connect accounts + site + 3 best customers
      -> crawl site        -> product summary            (LLM)
      -> enrich customers  -> firmographic pattern       (Enrichment)
      -> ICP description + personas                      (LLM, editable)
      -> embeddings for ICP and each customer            (LLM.embed)
      -> founder past posts -> voice samples             (Social; fakes for now)

Everything is stored; nothing is decided. The scorecard (Component 2) reads from here.
"""
import json
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..interfaces import get_enrichment, get_llm, get_social
from ..models import ICP, Company, Founder, VoiceProfile
from .crawl import crawl

PRODUCT_SUMMARY_SYS = """You are a precise product analyst. From a company's public website text,
write a product summary for internal use by a marketing engineer. Be concrete and literal;
do not invent. Return JSON with keys:
  one_liner (string, <= 20 words),
  what_it_does (string, 2-3 sentences),
  who_it_is_for (string),
  key_features (list of <= 6 strings),
  proof_points (list of strings: customers, numbers, logos, awards found in the text),
  data_assets (list of strings: any data the product generates or exposes that could power pages/tools),
  competitors_mentioned (list of strings),
  tone_of_site (string, one line)."""

ICP_SYS = """You are a B2B go-to-market analyst. Given a product summary and three real customers
(with enrichment), describe the ideal customer profile. Be specific and falsifiable. Return JSON:
  description (string, 3-5 sentences describing who buys and why),
  firmographics ({industry: [..], size_band: string, stage: string, geography: string, tech_signals: [..]}),
  personas (list of 2-3 {title, cares_about, objection, where_they_pay_attention}),
  narrow_segment (string: the single narrowest segment to target first, one line),
  disqualifiers (list of strings)."""


@dataclass
class IntakeInput:
    company_id: uuid.UUID
    site_url: str
    docs_urls: list[str]
    best_customers: list[dict]      # [{company, domain?, person?, role?, why_they_bought?}]
    founder_handles: list[dict]     # [{founder_id, linkedin_handle?, x_handle?}]
    site_text: str | None = None    # fallback when the site blocks fetches: founder pastes it


def _json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text}


def run_intake(db: Session, inp: IntakeInput) -> dict:
    llm, enrich, social = get_llm(), get_enrichment(), get_social()
    company = db.get(Company, inp.company_id)
    if not company:
        raise ValueError("company not found")

    # 1. crawl -> product summary
    crawled = crawl(inp.site_url, inp.docs_urls)
    site_text = crawled.text or (inp.site_text or "")
    if not site_text:
        raise ValueError(f"could not fetch {inp.site_url} ({crawled.errors[:1]}); pass site_text instead")
    summary = _json(llm.complete(PRODUCT_SUMMARY_SYS, site_text[:40000],
                                 purpose="product_summary", json_mode=True, max_tokens=1200).text)
    company.product_summary = json.dumps(summary)
    company.product_data_sources = [{"type": "site", "url": inp.site_url}] + [
        {"type": "docs", "url": u} for u in inp.docs_urls]

    # 2. enrich the three customers
    enriched = []
    for c in inp.best_customers:
        org = enrich.org(c.get("domain") or c.get("company", "").lower().replace(" ", "") + ".com")
        enriched.append({**c, "enriched": {
            "industry": org.industry if org else None, "employees": org.employees if org else None,
            "stage": org.stage if org else None, "description": org.description if org else None}})

    # 3. ICP
    icp_json = _json(llm.complete(
        ICP_SYS, json.dumps({"product": summary, "customers": enriched}, indent=1),
        purpose="icp", json_mode=True, max_tokens=1200).text)
    icp = ICP(company_id=company.id, description=icp_json.get("description"),
              best_customers=enriched, firmographics=icp_json.get("firmographics", {}),
              personas=icp_json.get("personas", []))
    db.add(icp)
    db.flush()

    # 4. embeddings (stored via raw SQL because pgvector type isn't in the ORM model)
    texts = [icp.description or ""] + [json.dumps(c) for c in enriched]
    vecs = llm.embed(texts, purpose="icp")
    db.execute(__import__("sqlalchemy").text("UPDATE icp SET embedding = :v WHERE id = :id"),
               {"v": str(vecs[0]), "id": str(icp.id)})
    sims = [_cos(vecs[0], v) for v in vecs[1:]]

    # 5. founder past posts -> voice samples
    voice_ids = []
    for fh in inp.founder_handles:
        f = db.get(Founder, uuid.UUID(str(fh["founder_id"])))
        if not f:
            continue
        f.linkedin_handle = fh.get("linkedin_handle") or f.linkedin_handle
        f.x_handle = fh.get("x_handle") or f.x_handle
        samples = []
        for ch in ("linkedin", "x"):
            try:
                stats = social.account_stats(founder_id=str(f.id), channel=ch)
                for p in stats.get("recent_posts", []):
                    samples.append({"text": p["text"], "platform": ch, "source": "past_post",
                                    "metrics": {k: p.get(k) for k in ("impressions", "reactions")}})
            except Exception:  # noqa: BLE001
                pass
        vp = VoiceProfile(company_id=company.id, founder_id=f.id, samples=samples,
                          rules={"banned_phrases": DEFAULT_BANNED, "casing": None, "tone": None})
        db.add(vp)
        db.flush()
        f.voice_profile_id = vp.id
        voice_ids.append(str(vp.id))

    company.status = "active"
    db.commit()
    return {"company_id": str(company.id), "product_summary": summary, "icp_id": str(icp.id),
            "icp": icp_json, "customer_similarity": sims, "voice_profile_ids": voice_ids,
            "pages_crawled": len(crawled.pages), "crawl_errors": crawled.errors[:3],
            "narrow_segment": icp_json.get("narrow_segment")}


def _cos(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


# The slop list. Every post is checked against it (Component 3). Founders can add their own.
DEFAULT_BANNED = [
    "delve", "in today's fast-paced world", "game-changer", "unlock", "unleash", "supercharge",
    "leverage", "seamless", "revolutionize", "elevate", "empower", "navigate the landscape",
    "it's not just", "here's the thing", "let that sink in", "thread 🧵", "🚀", "in conclusion",
    "buckle up", "dive deep", "double-edged sword", "a testament to", "tapestry",
]
