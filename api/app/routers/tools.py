import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require_api_key
from ..db import get_db
from ..metrics.signup import classify
from ..models import Company, Job, SignupSource, Tool, ToolEvent
from ..tools.factory import _out, decide, propose, render, stats, validate_spec

router = APIRouter(tags=["tools"])
auth = [Depends(require_api_key)]


class DecideIn(BaseModel):
    approve: bool = True


class SpecIn(BaseModel):
    spec: dict


class EventIn(BaseModel):
    kind: str
    payload: dict = {}


def _company(cid, db):
    c = db.get(Company, cid)
    if not c:
        raise HTTPException(404, "company not found")
    return c


@router.post("/companies/{company_id}/tools/propose", dependencies=auth)
def do_propose(company_id: uuid.UUID, db: Session = Depends(get_db)):
    return propose(db, _company(company_id, db))


@router.get("/companies/{company_id}/tools", dependencies=auth)
def list_tools(company_id: uuid.UUID, db: Session = Depends(get_db)):
    return [{**_out(t), "stats": stats(db, t)} for t in db.scalars(select(Tool).where(Tool.company_id == company_id).order_by(Tool.created_at))]


@router.patch("/tools/{tool_id}/spec", dependencies=auth)
def edit_spec(tool_id: uuid.UUID, body: SpecIn, db: Session = Depends(get_db)):
    t = db.get(Tool, tool_id)
    if not t:
        raise HTTPException(404, "tool not found")
    merged = {**t.spec, **body.spec}
    ok, why = validate_spec({"kind": t.kind, **merged})
    if not ok:
        raise HTTPException(422, why)
    t.spec = merged
    if t.status == "proposed":
        t.status = "draft"
    db.commit()
    return _out(t)


@router.post("/tools/{tool_id}/decide", dependencies=auth)
def do_decide(tool_id: uuid.UUID, body: DecideIn, request: Request, db: Session = Depends(get_db)):
    """The founder's tap: publish (and queue distribution posts) or retire."""
    t = db.get(Tool, tool_id)
    if not t:
        raise HTTPException(404, "tool not found")
    t = decide(db, t, body.approve)
    out = _out(t)
    if body.approve:
        # distribution: two posts drafted from the tool, into the founder's feed
        from ..models import Founder, VoiceProfile
        from ..voice.check import check
        from ..voice.engine import draft_one
        from ..voice.formats import FORMATS
        f = db.scalars(select(Founder).where(Founder.company_id == t.company_id)).first()
        vp = db.scalars(select(VoiceProfile).where(VoiceProfile.founder_id == f.id)).first() if f else None
        made = []
        if f and vp:
            url = f"{str(request.base_url).rstrip('/')}/t/{t.company_id}/{t.slug}"
            claim = {"id": f"tool-{t.id}", "type": "product", "text": f"we built a free tool: {t.name}. {t.spec.get('question', '')} {url}",
                     "evidence": t.rationale or "", "number": None}
            for ch, fmt in (("linkedin", "build_log"), ("x", "question")):
                text, meta = draft_one(claim, fmt, ch, vp, f.name)
                res = check(text, banned=(vp.rules or {}).get("banned_phrases", []), samples=[s["text"] for s in vp.samples][:20])
                if res.passed:
                    j = Job(company_id=t.company_id, founder_id=f.id, type="post", channel=ch, format=fmt, state="pending", voice_match=res.score,
                            input={"claim": claim, "shape": FORMATS[fmt]["shape"], "length": meta, "tool_id": str(t.id)}, output={"text": text, "media": []})
                    db.add(j)
                    made.append(j)
            db.commit()
        out["distribution_jobs"] = [str(j.id) for j in made]
    return out


# ---- public ----
@router.get("/t/{company_id}/{slug}")
def serve(company_id: uuid.UUID, slug: str, request: Request, db: Session = Depends(get_db)):
    c = _company(company_id, db)
    t = db.scalars(select(Tool).where(Tool.company_id == c.id, Tool.slug == slug, Tool.status == "published")).first()
    if not t:
        raise HTTPException(404, "tool not found")
    return Response(render(c, t, str(request.base_url).rstrip("/")), media_type="text/html")


@router.post("/public/tools/{tool_id}/event", status_code=201)
def event(tool_id: uuid.UUID, body: EventIn, db: Session = Depends(get_db)):
    t = db.get(Tool, tool_id)
    if not t or body.kind not in ("view", "run", "lead"):
        raise HTTPException(404, "tool not found")
    payload = dict(body.payload)
    if body.kind == "lead":
        email = payload.pop("email", None)
        payload["email_hash"] = str(hash(email)) if email else None
        db.add(SignupSource(company_id=t.company_id, signup_id=email, answer_text=f"tool:{t.slug}",
                            classified_channel=f"tool:{t.slug}", classified_by="tool_event"))
    db.add(ToolEvent(tool_id=t.id, company_id=t.company_id, kind=body.kind, payload=payload))
    db.commit()
    return {"ok": True}
