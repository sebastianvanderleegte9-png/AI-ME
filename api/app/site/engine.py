"""Site and onboarding engine (Component 10).

  snapshot(url)         fetch the landing page; find and walk the signup flow (headless when available)
  audit(company)        40 checks -> scored, stored on the plan row as `site_audit`
  rewrite(company)      for each failed check with a copy fix: generate the change as a Job(type=site_change)
                        (hero, subhead, CTA, section order, signup fields, activation email) for approval
  variant(company)      assemble the approved changes into a hosted landing page at /v/{company}/{slug}
                        the founder can A/B it with a redirect, or export the HTML/copy to their CMS
  measure               signup -> activation before/after, from signup_source + activation events"""
from dataclasses import asdict
from datetime import datetime, timezone
from html import escape
import json
import re
import uuid

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..interfaces import get_llm
from ..models import ICP, Company, Founder, Job, Plan, VoiceProfile
from ..voice.check import check as voice_check
from .checks import CHECKS, Snapshot, run, score

UA = "MarketingEngineerBot/0.1 (+site-audit)"
SIGNUP_WORDS = ("sign up", "signup", "get started", "start free", "try free", "create account", "start", "try")


def snapshot(url: str, icp_terms: list[str], html_override: str | None = None, walkthrough: dict | None = None) -> Snapshot:
    if not url.startswith("http"):
        url = "https://" + url
    s = Snapshot(url=url, icp_terms=[t.lower() for t in icp_terms])
    html = html_override
    if html is None:
        try:
            t0 = datetime.now()
            r = httpx.get(url, headers={"User-Agent": UA}, timeout=15, follow_redirects=True)
            s.load_ms = int((datetime.now() - t0).total_seconds() * 1000)
            html = r.text if r.status_code == 200 else ""
        except Exception:  # noqa: BLE001
            html = ""
    s.html = html or ""
    if not s.html:
        return s
    soup = BeautifulSoup(s.html, "lxml")
    s.title = (soup.title.string or "").strip() if soup.title else ""
    for t in soup(["script", "style", "noscript"]):
        pass
    s.scripts = len(soup.find_all("script"))
    s.images = len(soup.find_all("img"))
    s.has_demo_or_video = bool(soup.find_all(["video", "iframe"])) or any(
        "demo" in (i.get("alt") or "").lower() or "screenshot" in (i.get("src") or "").lower() for i in soup.find_all("img"))
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    s.text = " ".join(soup.get_text(" ").split())
    s.word_count = len(s.text.split())
    s.headings = [h.get_text(" ", strip=True) for h in soup.find_all(["h1", "h2", "h3"])][:30]
    s.links = [(a.get_text(" ", strip=True) + " " + (a.get("href") or "")).strip() for a in soup.find_all("a")][:200]
    for f in soup.find_all("form"):
        fields = [{"name": i.get("name") or "", "type": i.get("type") or i.name, "required": i.has_attr("required")}
                  for i in f.find_all(["input", "select", "textarea"]) if (i.get("type") or "") not in ("hidden", "submit")]
        s.forms.append({"action": f.get("action") or "", "fields": fields,
                        "has_source_field": any("source" in (x["name"] or "").lower() or "hear" in (x["name"] or "").lower() for x in fields)
                        or "data-me-signup" in str(f)})
    s.proof_points = re.findall(r"\b\d[\d,]*\+?\s*(?:agents|users|customers|teams|companies|loans|%)\b", s.text)[:10]
    # signup discovery: a link whose text or href says signup
    for l in s.links:
        if any(w in l.lower() for w in SIGNUP_WORDS):
            s.signup_url = l.split()[-1] if l.split() else None
            break
    # walkthrough results are supplied (headless run lives in the worker; tests and fakes pass a dict)
    if walkthrough:
        for k, v in walkthrough.items():
            if hasattr(s, k):
                setattr(s, k, v)
    elif s.forms and s.signup_url:
        f0 = s.forms[0]
        s.signup_steps, s.signup_fields = 1, len(f0["fields"])
        s.requires_card = any("card" in (x["name"] or "").lower() for x in f0["fields"])
        s.requires_call = False
    return s


def audit(db: Session, company: Company, url: str | None = None, html_override: str | None = None, walkthrough: dict | None = None) -> dict:
    icp = db.scalars(select(ICP).where(ICP.company_id == company.id).order_by(ICP.version.desc())).first()
    terms: list[str] = []
    if icp:
        for p in icp.personas or []:
            if isinstance(p, dict) and p.get("title"):
                terms.append(p["title"])
        for ind in (icp.firmographics or {}).get("industry", []) or []:
            terms.append(ind)
    snap = snapshot(url or (company.domain or ""), terms, html_override, walkthrough)
    results = run(snap)
    sc = score(results)
    report = {**sc, "url": snap.url, "at": datetime.now(timezone.utc).isoformat(), "fetched": bool(snap.html),
              "checks": [{"id": r.check.id, "category": r.check.category, "weight": r.check.weight, "title": r.check.title,
                          "passed": r.passed, "evidence": r.evidence, "fix": r.check.fix} for r in results],
              "snapshot": {"title": snap.title, "h1": snap.headings[0] if snap.headings else None, "word_count": snap.word_count,
                           "signup_url": snap.signup_url, "signup_steps": snap.signup_steps, "signup_fields": snap.signup_fields,
                           "proof_points": snap.proof_points, "forms": len(snap.forms)}}
    # store on the latest plan row (the scorecard's onboarding channel reads it next time)
    plan = db.scalars(select(Plan).where(Plan.company_id == company.id).order_by(Plan.week_start.desc())).first()
    if plan:
        scd = dict(plan.scorecard or {})
        scd["site_audit"] = {k: v for k, v in report.items() if k != "checks"} | {"failed": [c["id"] for c in report["checks"] if not c["passed"]]}
        plan.scorecard = scd
        db.commit()
    return report


REWRITE_SYS = """You rewrite one element of a B2B software landing page or onboarding flow, for a specific ICP,
in the founder's voice (rules and samples below). You are given the current text, the failed check and its fix,
the product summary and the ICP. Return JSON: {"proposal": "<the new text>", "why": "<one line>"}.
Be literal and specific; no category words; use the ICP's own terms; numbers over adjectives."""

COPY_CHECKS = {"c01": ("hero_h1", "the h1"), "c02": ("hero_h1", "the h1"), "c03": ("hero_sub", "the subheadline"),
               "c04": ("hero_sub", "the subheadline"), "c05": ("title_tag", "the title tag"), "c11": ("primary_cta", "the primary CTA label"),
               "c22": ("first_screen", "the first screen a new user sees"), "c23": ("first_screen", "the first screen a new user sees"),
               "c26": ("activation_email", "the activation email (subject + 3 lines)"), "c27": ("activation_email", "the activation email subject"),
               "c30": ("hero_sub", "the subheadline"), "c13": ("signup_form", "the signup form: list the fields to keep"),
               "c14": ("signup_form", "the signup form: list the fields to keep")}


def rewrite(db: Session, company: Company, report: dict, founder: Founder | None = None) -> dict:
    llm = get_llm()
    founder = founder or db.scalars(select(Founder).where(Founder.company_id == company.id)).first()
    vp = db.scalars(select(VoiceProfile).where(VoiceProfile.founder_id == founder.id)).first() if founder else None
    banned = (vp.rules or {}).get("banned_phrases", []) if vp else []
    samples = [s["text"] for s in vp.samples][:8] if vp else []
    icp = db.scalars(select(ICP).where(ICP.company_id == company.id).order_by(ICP.version.desc())).first()
    try:
        summary = json.loads(company.product_summary or "{}") or {}
    except json.JSONDecodeError:
        summary = {}
    snap = report.get("snapshot", {})
    failed = [c for c in report["checks"] if not c["passed"] and c["id"] in COPY_CHECKS]
    done: set[str] = set()
    created = []
    for c in failed:
        element, label = COPY_CHECKS[c["id"]]
        if element in done:
            continue
        done.add(element)
        current = {"hero_h1": snap.get("h1"), "title_tag": snap.get("title")}.get(element) or ""
        system = REWRITE_SYS + f"\nVoice rules: {json.dumps({k: v for k, v in ((vp.rules or {}) if vp else {}).items() if k != 'banned_phrases'})}\nBanned: {', '.join(banned[:30])}\nSamples:\n" + "\n---\n".join(samples)
        user = json.dumps({"element": label, "current": current, "failed_check": c["title"], "fix": c["fix"],
                           "product": summary, "icp": icp.description if icp else None,
                           "personas": [p.get("title") for p in (icp.personas or []) if isinstance(p, dict)] if icp else []})
        raw = llm.complete(system, user, purpose="site_rewrite", json_mode=True, temperature=0.4, max_tokens=400).text
        try:
            body = json.loads(raw)
            if body.get("fake"):
                raise ValueError
        except (json.JSONDecodeError, ValueError):
            body = _fake_rewrite(element, company, icp, summary)
        res = voice_check(body["proposal"], banned=banned, samples=samples)
        if res.banned_hits:
            continue
        job = Job(company_id=company.id, founder_id=founder.id if founder else None, type="site_change", channel="web",
                  format=element, state="pending", voice_match=res.score,
                  input={"element": element, "label": label, "current": current, "check_ids": [x["id"] for x in failed if COPY_CHECKS[x["id"]][0] == element],
                         "fix": c["fix"], "why": body.get("why")},
                  output={"text": body["proposal"]})
        db.add(job)
        created.append(job)
    db.commit()
    return {"created": [{"id": str(j.id), "element": j.format, "proposal": j.output["text"], "why": j.input.get("why")} for j in created],
            "failed_copy_checks": [c["id"] for c in failed]}


def _fake_rewrite(element: str, company: Company, icp, summary: dict) -> dict:
    seg = ((icp.firmographics or {}).get("industry") or ["your team"])[0] if icp else "your team"
    persona = next((p.get("title") for p in (icp.personas or []) if isinstance(p, dict)), "operators") if icp else "operators"
    one = summary.get("one_liner") or f"{company.name}"
    return {
        "hero_h1": {"proposal": f"{one} for {seg}", "why": "says what it does for whom, no category words"},
        "hero_sub": {"proposal": f"Built for {persona}s at {seg}. First result in your first session; no sales call to start.", "why": "ICP terms and time-to-value"},
        "title_tag": {"proposal": f"{company.name} — {one} for {seg}"[:60], "why": "under 60 chars, states the job"},
        "primary_cta": {"proposal": "Start with your own data", "why": "an action, not 'learn more'"},
        "first_screen": {"proposal": "Paste one listing address to see the packet draft. (Or use the sample.)", "why": "one action, sample data offered, under 120 words"},
        "activation_email": {"proposal": "Subject: Your first packet is one paste away\n\nPaste one address. You'll have a draft in under a minute.\nReply to this email if it isn't right; a person reads these.", "why": "subject is the action"},
        "signup_form": {"proposal": "Keep: work email, password. Remove: company size, phone, role. Add: 'how did you hear about us?' (one line).", "why": "four fields or fewer, attribution added"},
    }[element]


def variant_html(company: Company, approved: list[Job], report: dict, signup_widget_url: str) -> str:
    """A hosted landing page built from the approved changes. Minimal by design: hero, proof,
    how it works, one CTA. The founder can point a redirect at it or copy the sections."""
    e = escape
    by = {j.format: j.output["text"] for j in approved}
    snap = report.get("snapshot", {})
    h1 = by.get("hero_h1") or snap.get("h1") or company.name
    sub = by.get("hero_sub") or ""
    cta = by.get("primary_cta") or "Get started"
    title = by.get("title_tag") or snap.get("title") or h1
    proof = "".join(f"<li>{e(p)}</li>" for p in snap.get("proof_points", [])[:4])
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{e(title)}</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="{e(sub[:155])}">
<style>body{{font-family:Helvetica,Arial,sans-serif;color:#141414;max-width:720px;margin:0 auto;padding:48px 20px;line-height:1.5}}
h1{{font-size:38px;letter-spacing:-.02em;margin:0 0 12px}} .sub{{font-size:19px;color:#444;margin:0 0 24px}}
form{{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 32px}} input{{padding:12px;font-size:16px;border:1px solid #ccc;border-radius:6px;flex:1;min-width:220px}}
button{{padding:12px 18px;font-size:16px;background:#141414;color:#fff;border:0;border-radius:6px;cursor:pointer}}
ul{{padding-left:18px}} .m{{color:#666;font-size:13px;margin-top:40px}}</style></head><body>
<h1>{e(h1)}</h1><p class="sub">{e(sub)}</p>
<form data-me-signup method="post" action="#"><input name="email" type="email" placeholder="work email" required><button>{e(cta)}</button></form>
{f'<h2>Proof</h2><ul>{proof}</ul>' if proof else ''}
<p class="m">{e(company.name)} · variant generated by the onboarding engine · <a href="{e(report.get('url', ''))}">current site</a></p>
<script src="{e(signup_widget_url)}"></script></body></html>"""
