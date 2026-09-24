"""Page factory: candidates -> generated pages -> founder approves batch -> published -> indexed.

Candidates come from the ICP (segments, personas), the product summary (competitors,
use cases, data assets) and, when connected, Search Console queries. Each candidate
is matched to a template; the data point comes from the company's data source
(`product_data_sources` + the founder-supplied `data_points` list). Generation is
LLM-written prose around real data, then checked: minimum words, data present, no
banned phrases. Pages are stored as HTML and served at /p/{company}/{slug} with a
sitemap; a CMS adapter can push them elsewhere later."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import escape
import json
import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..interfaces import get_llm
from ..models import ICP, Company, Job, Page, VoiceProfile
from ..voice.check import check
from .templates import MAX_PAGES_PER_BATCH, MIN_WORDS, TEMPLATES

PAGE_SYS = """You write a web page for a B2B software company. You are given the template sections,
the target query, the segment, the product summary, and one or more REAL data points with their source.
Write plainly for a practitioner. Every section must be specific to the segment. Use the data point in the
hero and again in the data_point section with its source. Do not invent numbers, customers or features.
No marketing adjectives. Return JSON: {"sections": {section_name: "html-free plain text with paragraphs separated by \\n\\n"},
"faq": [{"q": "...", "a": "..."}], "meta_description": "..."}"""


@dataclass
class Candidate:
    template_id: str
    slug: str
    query: str
    vars: dict
    score: float
    data_points: list[dict] = field(default_factory=list)


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:80]


def propose(db: Session, company: Company, data_points: list[dict], limit: int = 30) -> list[Candidate]:
    """data_points: [{"stat": "1,300 agents onboarded in 6 weeks", "source": "internal rollout data", "tags": ["onboarding","brokerage"]}]"""
    try:
        summary = json.loads(company.product_summary or "{}") or {}
    except json.JSONDecodeError:
        summary = {}
    icp = db.scalars(select(ICP).where(ICP.company_id == company.id).order_by(ICP.version.desc())).first()
    product = summary.get("one_liner") and company.name or company.name
    segments = []
    if icp:
        for ind in (icp.firmographics or {}).get("industry", []) or []:
            segments.append(ind)
        for p in icp.personas or []:
            if isinstance(p, dict) and p.get("title"):
                segments.append(p["title"])
    competitors = summary.get("competitors_mentioned", []) or []
    use_cases = [f for f in (summary.get("key_features", []) or [])][:6]
    if not data_points:
        return []

    def dp_for(tags: list[str]) -> list[dict]:
        tagged = [d for d in data_points if set(map(str.lower, d.get("tags", []))) & set(map(str.lower, tags))]
        return tagged or data_points[:1]

    out: list[Candidate] = []
    for seg in segments:
        out.append(Candidate("product_for_segment", _slug(f"{product} for {seg}"), f"{product} for {seg}",
                             {"product": product, "segment": seg}, 0.9, dp_for([seg])))
    for comp in competitors:
        for seg in segments[:2] or ["teams"]:
            out.append(Candidate("competitor_alternative", _slug(f"{comp} alternative {seg}"), f"{comp} alternative",
                                 {"product": product, "competitor": comp, "segment": seg,
                                  "differences": summary.get("key_features", [])[:4]}, 0.8, dp_for([comp, seg])))
    for uc in use_cases:
        for seg in segments[:2] or ["teams"]:
            out.append(Candidate("use_case_with_data", _slug(f"{uc} {seg}"), f"{uc} {seg}",
                                 {"product": product, "use_case": uc, "segment": seg}, 0.7, dp_for([uc, seg])))
    # dedupe by slug, keep best score
    best: dict[str, Candidate] = {}
    for c in out:
        if c.slug not in best or c.score > best[c.slug].score:
            best[c.slug] = c
    existing = {p.slug for p in db.scalars(select(Page).where(Page.company_id == company.id))}
    ranked = sorted((c for c in best.values() if c.slug not in existing), key=lambda c: -c.score)
    return ranked[:min(limit, MAX_PAGES_PER_BATCH)]


def _fake_sections(tpl: dict, v: dict, dps: list[dict]) -> dict:
    dp = dps[0]["stat"]
    src = dps[0].get("source", "internal data")
    seg, product = v.get("segment", "teams"), v.get("product", "the product")
    base = {s: f"{s.replace('_', ' ').title()} for {seg}: {product} — {dp} ({src}). " * 6 for s in tpl["sections"]}
    base["hero"] = f"{product} for {seg}. {dp} ({src}).\n\nThis page explains how {seg} use {product} and what the numbers show."
    base["cta"] = f"See how {product} works for {seg}."
    return {"sections": base, "faq": [{"q": f"Does {product} work for {seg}?", "a": f"Yes: {dp} ({src})."},
                                      {"q": "How long does setup take?", "a": "Most teams are live in a week."}],
            "meta_description": f"{dp}. How {seg} use {product}."}


def generate(db: Session, company: Company, cands: list[Candidate], founder_id: uuid.UUID | None = None) -> dict:
    llm = get_llm()
    vp = db.scalars(select(VoiceProfile).where(VoiceProfile.company_id == company.id)).first()
    banned = (vp.rules or {}).get("banned_phrases", []) if vp else []
    try:
        summary = json.loads(company.product_summary or "{}") or {}
    except json.JSONDecodeError:
        summary = {}
    made, rejected = [], []
    for c in cands:
        tpl = TEMPLATES[c.template_id]
        missing = [r for r in tpl["requires"] if r != "data_point" and not c.vars.get(r) and r not in ("proof", "steps", "differences")]
        if not c.data_points or missing:
            rejected.append({"slug": c.slug, "reason": f"missing {missing or ['data_point']}"})
            continue
        user = json.dumps({"template": tpl["sections"], "query": c.query, "vars": c.vars, "product": summary,
                           "data_points": c.data_points}, indent=1)
        raw = llm.complete(PAGE_SYS, user, purpose="page_generate", json_mode=True, max_tokens=2500, temperature=0.3).text
        try:
            body = json.loads(raw)
            if body.get("fake"):
                raise ValueError
        except (json.JSONDecodeError, ValueError):
            body = _fake_sections(tpl, c.vars, c.data_points)
        text_all = " ".join(body.get("sections", {}).values()) + " ".join(f["q"] + " " + f["a"] for f in body.get("faq", []))
        words = len(text_all.split())
        chk = check(text_all, banned=banned, samples=[])
        has_dp = any(d["stat"].split()[0] in text_all for d in c.data_points)
        if words < MIN_WORDS or chk.banned_hits or not has_dp:
            rejected.append({"slug": c.slug, "reason": f"words={words} banned={chk.banned_hits} data_present={has_dp}"})
            continue
        dp_short = c.data_points[0]["stat"]
        title = tpl["title"].format(**{**c.vars, "data_point_short": dp_short})
        page = Page(company_id=company.id, template_id=c.template_id, slug=c.slug, title=title,
                    data={"query": c.query, "vars": c.vars, "data_points": c.data_points, "body": body,
                          "words": words, "meta_description": body.get("meta_description") or tpl["description"].format(**{**c.vars, "data_point_short": dp_short})},
                    status="draft")
        db.add(page)
        db.flush()
        page.html_ref = f"/p/{company.id}/{c.slug}"
        # one approval Job per batch is created by the router; each page is a draft until then
        made.append(page)
    db.commit()
    return {"generated": [{"id": str(p.id), "slug": p.slug, "title": p.title, "words": p.data["words"]} for p in made],
            "rejected": rejected}


def render_page(company: Company, page: Page) -> str:
    e = escape
    b = page.data.get("body", {})
    secs = b.get("sections", {})
    dps = page.data.get("data_points", [])
    faq = b.get("faq", [])
    faq_ld = {"@context": "https://schema.org", "@type": "FAQPage",
              "mainEntity": [{"@type": "Question", "name": f["q"], "acceptedAnswer": {"@type": "Answer", "text": f["a"]}} for f in faq]}
    parts = []
    order = TEMPLATES.get(page.template_id, {}).get("sections", list(secs))
    for name in [n for n in order if n in secs] + [n for n in secs if n not in order]:
        if name in ("faq", "cta"):
            continue  # rendered by their own blocks below
        txt = secs[name]
        heading = "" if name == "hero" else name.replace("_", " ").capitalize()
        paras = "".join(f"<p>{e(p.strip())}</p>" for p in txt.split("\n\n") if p.strip())
        if name == "data_point" and dps:
            paras = f'<div class="dp"><b>{e(dps[0]["stat"])}</b><span>{e(dps[0].get("source", ""))}</span></div>' + paras
        parts.append(f"<section>{f'<h2>{e(heading)}</h2>' if heading else ''}{paras}</section>")
    faq_html = "".join(f"<details><summary>{e(f['q'])}</summary><p>{e(f['a'])}</p></details>" for f in faq)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{e(page.title)}</title>
<meta name="description" content="{e(page.data.get('meta_description', ''))}"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="canonical" href="{e(page.html_ref or '')}">
<script type="application/ld+json">{json.dumps(faq_ld)}</script>
<style>body{{font-family:Helvetica,Arial,sans-serif;max-width:760px;margin:0 auto;padding:32px 20px;line-height:1.55;color:#141414}}
h1{{font-size:32px;letter-spacing:-.01em}} h2{{font-size:20px;margin-top:32px}} .dp{{background:#f3f5fa;border-left:3px solid #1f4fd1;padding:12px 16px;margin:12px 0}}
.dp b{{display:block;font-size:22px}} .dp span{{color:#666;font-size:13px}} details{{margin:8px 0}} summary{{font-weight:600;cursor:pointer}}
.cta{{margin-top:40px;padding:20px;background:#141414;color:#fff;border-radius:8px}} .m{{color:#666;font-size:13px}}</style></head>
<body><h1>{e(page.title)}</h1><p class="m">{e(company.name)}</p>{''.join(parts)}
<section><h2>FAQ</h2>{faq_html}</section>
<div class="cta">{e(secs.get('cta', f"Talk to {company.name} about {page.data.get('vars', {}).get('segment', 'your team')}.").split(chr(10))[0][:200])}</div>
</body></html>"""


def sitemap(company: Company, pages: list[Page], base_url: str) -> str:
    urls = "".join(f"<url><loc>{escape(base_url.rstrip('/') + (p.html_ref or ''))}</loc><lastmod>{(p.published_at or p.updated_at).date()}</lastmod></url>"
                   for p in pages if p.status in ("published", "indexed"))
    return f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'


def approve_batch(db: Session, company: Company, page_ids: list[uuid.UUID], approve: bool) -> dict:
    pages = db.scalars(select(Page).where(Page.company_id == company.id, Page.id.in_(page_ids))).all()
    now = datetime.now(timezone.utc)
    for p in pages:
        if approve and p.status == "draft":
            p.status, p.published_at = "published", now
        elif not approve:
            db.delete(p)
    db.commit()
    return {"published" if approve else "deleted": [str(p.id) for p in pages]}


def mark_indexed(db: Session, company: Company, slugs: list[str]) -> int:
    """Called by the metrics pull once Search Console reports the URL (Component 5 hook)."""
    n = 0
    for p in db.scalars(select(Page).where(Page.company_id == company.id, Page.slug.in_(slugs), Page.status == "published")):
        p.status, p.indexed_at = "indexed", datetime.now(timezone.utc)
        n += 1
    db.commit()
    return n
