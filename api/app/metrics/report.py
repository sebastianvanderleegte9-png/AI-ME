"""Weekly rollup and the Friday report.

  rollup(week)  -> {impressions_icp, impressions, followers_icp_delta, pages_indexed, signups,
                    approval_rate, edit_rate, top_posts[]}  from metric + job rows
  outcome row   -> targets (from the plan) vs actuals vs delta: the training set
  report        -> HTML email body + JSON, and a share card (PNG) the founder can post"""
from datetime import date, timedelta
from html import escape

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Company, Job, Metric, Outcome, Plan, SignupSource


def week_bounds(d: date | None = None) -> tuple[date, date]:
    d = d or date.today()
    start = d - timedelta(days=d.weekday())            # Monday
    return start, start + timedelta(days=6)


def _sum(db, company_id, name, start, end, source_prefix=None) -> float:
    q = select(func.coalesce(func.sum(Metric.value), 0)).where(Metric.company_id == company_id, Metric.name == name,
                                                              Metric.date >= start, Metric.date <= end)
    if source_prefix:
        q = q.where(Metric.source.like(f"{source_prefix}%"))
    return float(db.scalar(q) or 0)


def _latest(db, company_id, name, on_or_before) -> float | None:
    v = db.scalar(select(Metric.value).where(Metric.company_id == company_id, Metric.name == name, Metric.date <= on_or_before)
                  .order_by(Metric.date.desc()).limit(1))
    return None if v is None else float(v)


def rollup(db: Session, company: Company, week_of: date | None = None) -> dict:
    start, end = week_bounds(week_of)
    prev_start, prev_end = start - timedelta(days=7), start - timedelta(days=1)
    cid = company.id

    def block(s, e):
        return {"impressions_icp": round(_sum(db, cid, "impressions_icp", s, e)),
                "impressions": round(_sum(db, cid, "impressions", s, e)),
                "search_impressions": round(_sum(db, cid, "search_impressions", s, e)),
                "signups": round(_sum(db, cid, "signups", s, e)),
                "pages_indexed": _latest(db, cid, "pages_indexed", e) or 0,
                "followers": (_latest(db, cid, "followers_linkedin", e) or 0) + (_latest(db, cid, "followers_x", e) or 0)}

    this, prev = block(start, end), block(prev_start, prev_end)
    delta = {k: this[k] - prev[k] for k in this}

    # approval / edit rates for jobs decided this week
    jobs = db.scalars(select(Job).where(Job.company_id == cid, Job.type.in_(["post", "reply"]),
                                        Job.updated_at >= start, Job.state.in_(["approved", "edited", "rejected", "executed"]))).all()
    decided = len(jobs)
    ok = sum(1 for j in jobs if j.state != "rejected")
    edited = sum(1 for j in jobs if j.state == "edited" or (j.state == "executed" and j.approval_diff))
    approval_rate = round(ok / decided, 3) if decided else None
    edit_rate = round(edited / ok, 3) if ok else None

    # top posts by impressions_icp this week
    rows = db.execute(select(Metric.job_id, func.sum(Metric.value)).where(
        Metric.company_id == cid, Metric.name == "impressions_icp", Metric.date >= start, Metric.date <= end,
        Metric.job_id.is_not(None)).group_by(Metric.job_id).order_by(func.sum(Metric.value).desc()).limit(3)).all()
    top = []
    for jid, v in rows:
        j = db.get(Job, jid)
        if j:
            top.append({"job_id": str(jid), "channel": j.channel, "format": j.format,
                        "text": (j.output or {}).get("text", "")[:160], "impressions_icp": round(float(v))})

    # signup sources this week
    src = dict(db.execute(select(SignupSource.classified_channel, func.count()).where(
        SignupSource.company_id == cid, SignupSource.created_at >= start).group_by(SignupSource.classified_channel)).all())

    return {"week_start": str(start), "week_end": str(end), "this": this, "prev": prev, "delta": delta,
            "approval_rate": approval_rate, "edit_rate": edit_rate, "decided": decided, "top_posts": top,
            "signup_sources": {k or "unknown": v for k, v in src.items()}}


def write_outcome(db: Session, company: Company, week_of: date | None = None) -> Outcome:
    start, _ = week_bounds(week_of)
    r = rollup(db, company, start)
    plan = db.scalars(select(Plan).where(Plan.company_id == company.id, Plan.week_start <= start)
                      .order_by(Plan.week_start.desc())).first()
    if not plan:
        raise ValueError("no plan for this company; generate a scorecard first")
    targets = plan.targets or {}
    actuals = {"impressions_icp": r["this"]["impressions_icp"], "signups": r["this"]["signups"],
               "pages_indexed": r["this"]["pages_indexed"], "followers": r["this"]["followers"],
               "approval_rate": r["approval_rate"], "edit_rate": r["edit_rate"]}
    delta = {"impressions_icp_vs_target": actuals["impressions_icp"] - targets.get("impressions_icp_weekly", 0),
             "impressions_icp_wow": r["delta"]["impressions_icp"],
             "approval_gate": (r["approval_rate"] or 0) >= targets.get("approval_rate_min", 0.7)}
    o = db.scalars(select(Outcome).where(Outcome.company_id == company.id, Outcome.week_start == start)).first()
    if not o:
        o = Outcome(company_id=company.id, plan_id=plan.id, week_start=start)
        db.add(o)
    o.plan_id, o.targets, o.actuals, o.delta = plan.id, targets, actuals, delta
    o.approval_rate, o.edit_rate = r["approval_rate"], r["edit_rate"]
    db.commit()
    db.refresh(o)
    return o


def _pct(a, b):
    if not b:
        return "—"
    p = (a - b) / b * 100
    return f"{'+' if p >= 0 else ''}{p:.0f}%"


def report_html(company: Company, r: dict, plan: Plan | None) -> str:
    e = escape
    t, p, d = r["this"], r["prev"], r["delta"]
    target = (plan.targets or {}).get("impressions_icp_weekly_12w") if plan else None
    top = "".join(f"<li><b>{v['impressions_icp']:,}</b> in ICP · {e(v['channel'])} · {e(v['format'])}<br><span class='m'>{e(v['text'])}</span></li>"
                  for v in r["top_posts"]) or "<li class='m'>No posts measured yet this week.</li>"
    src = ", ".join(f"{e(k)} {v}" for k, v in r["signup_sources"].items()) or "none recorded"
    nxt = ""
    if plan and plan.sequence:
        nxt = "".join(f"<li>{e(s['fix'])}</li>" for s in plan.sequence[:2])
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
 body{{font-family:Helvetica,Arial,sans-serif;color:#141414;max-width:600px;margin:0 auto;padding:24px;line-height:1.45}}
 .n{{font-size:44px;font-weight:700;letter-spacing:-.02em;margin:0}} .m{{color:#666}} .row{{display:flex;gap:16px;margin:16px 0}}
 .k{{flex:1;background:#f3f5fa;padding:10px 12px;border-radius:6px}} .k b{{display:block;font-size:20px}}
 h2{{font-size:14px;text-transform:uppercase;letter-spacing:.05em;color:#666;margin:24px 0 8px}} li{{margin-bottom:8px}}
</style></head><body>
<p class="m">{e(company.name)} · week of {r['week_start']}</p>
<p class="n">{t['impressions_icp']:,}</p>
<p><b>impressions inside your ICP this week</b> · {_pct(t['impressions_icp'], p['impressions_icp'])} vs last week{f" · target by week 12: {target:,}" if target else ""}</p>
<div class="row">
 <div class="k"><b>{t['impressions']:,}</b><span class="m">all impressions ({_pct(t['impressions'], p['impressions'])})</span></div>
 <div class="k"><b>{t['signups']:,}</b><span class="m">signups ({_pct(t['signups'], p['signups'])})</span></div>
 <div class="k"><b>{int(t['pages_indexed'])}</b><span class="m">pages indexed ({int(d['pages_indexed']):+d})</span></div>
</div>
<h2>Top posts</h2><ol>{top}</ol>
<h2>Your part</h2><p>You decided {r['decided']} drafts · approval {f"{r['approval_rate']:.0%}" if r['approval_rate'] is not None else '—'} · edited {f"{r['edit_rate']:.0%}" if r['edit_rate'] is not None else '—'}. Signups said they came from: {src}.</p>
<h2>Next week</h2><ul>{nxt or '<li class="m">Plan pending.</li>'}</ul>
<p class="m">impressions inside ICP = impressions × share of engaged accounts that match your attention map (method icp_v1; a 20% prior is used when fewer than 5 engaged accounts are visible).</p>
</body></html>"""


def share_card_html(company: Company, r: dict, brand: dict | None) -> str:
    """1200x630 card the founder can post: one number, one delta, no product pitch."""
    from ..voice.visuals import DEFAULT_BRAND
    b = {**DEFAULT_BRAND, **(brand or {})}
    t, p = r["this"], r["prev"]
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
 html,body{{margin:0;width:1200px;height:630px;background:{b['bg']};color:{b['fg']};font-family:{b['font']}}}
 .w{{box-sizing:border-box;width:1200px;height:630px;padding:64px;display:flex;flex-direction:column;justify-content:space-between}}
 .n{{font-size:150px;font-weight:700;line-height:1;letter-spacing:-.03em;color:{b['accent']}}}
 .l{{font-size:40px;font-weight:600;margin-top:12px}} .d{{font-size:28px;color:{b['muted']};margin-top:8px}}
 .f{{font-size:24px;color:{b['muted']}}}
</style></head><body><div class="w">
<div><div class="n">{t['impressions_icp']:,}</div><div class="l">impressions inside our ICP this week</div>
<div class="d">{_pct(t['impressions_icp'], p['impressions_icp'])} vs last week · {t['signups']} signups</div></div>
<div class="f">{escape(company.name)} · week of {r['week_start']}</div></div></body></html>"""
