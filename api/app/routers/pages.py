import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require_api_key
from ..db import get_db
from ..models import Company, Page
from ..pages.factory import Candidate, approve_batch, generate, mark_indexed, propose, render_page, sitemap
from ..pages.templates import TEMPLATES

router = APIRouter(tags=["pages"])
auth = [Depends(require_api_key)]


class DataPoint(BaseModel):
    stat: str = Field(min_length=3)
    source: str = Field(min_length=3)
    tags: list[str] = Field(default_factory=list)


class ProposeIn(BaseModel):
    data_points: list[DataPoint] = Field(min_length=1)
    limit: int = Field(default=30, ge=1, le=50)


class GenerateIn(ProposeIn):
    slugs: list[str] | None = None     # subset of proposed candidates; default all


class BatchIn(BaseModel):
    page_ids: list[uuid.UUID] = Field(min_length=1)
    approve: bool = True


def _company(company_id, db):
    c = db.get(Company, company_id)
    if not c:
        raise HTTPException(404, "company not found")
    return c


@router.get("/page-templates", dependencies=auth)
def templates():
    return {k: {"keyword_rule": v["keyword_rule"], "requires": v["requires"], "sections": v["sections"]} for k, v in TEMPLATES.items()}


@router.post("/companies/{company_id}/pages/propose", dependencies=auth)
def do_propose(company_id: uuid.UUID, body: ProposeIn, db: Session = Depends(get_db)):
    c = _company(company_id, db)
    cands = propose(db, c, [d.model_dump() for d in body.data_points], body.limit)
    return [{"template": x.template_id, "slug": x.slug, "query": x.query, "vars": x.vars, "score": x.score,
             "data_points": x.data_points} for x in cands]


@router.post("/companies/{company_id}/pages/generate", dependencies=auth)
def do_generate(company_id: uuid.UUID, body: GenerateIn, db: Session = Depends(get_db)):
    c = _company(company_id, db)
    cands = propose(db, c, [d.model_dump() for d in body.data_points], body.limit)
    if body.slugs:
        cands = [x for x in cands if x.slug in set(body.slugs)]
    if not cands:
        raise HTTPException(422, "no candidates: the ICP needs segments and at least one data point")
    return generate(db, c, cands)


@router.get("/companies/{company_id}/pages", dependencies=auth)
def list_pages(company_id: uuid.UUID, status: str | None = None, db: Session = Depends(get_db)):
    q = select(Page).where(Page.company_id == company_id)
    if status:
        q = q.where(Page.status == status)
    return [{"id": str(p.id), "slug": p.slug, "title": p.title, "template": p.template_id, "status": p.status,
             "words": p.data.get("words"), "url": p.html_ref, "published_at": p.published_at, "indexed_at": p.indexed_at}
            for p in db.scalars(q.order_by(Page.created_at.desc()))]


@router.post("/companies/{company_id}/pages/batch", dependencies=auth)
def do_batch(company_id: uuid.UUID, body: BatchIn, db: Session = Depends(get_db)):
    """The founder's one tap on a batch: publish (approve=true) or discard."""
    return approve_batch(db, _company(company_id, db), body.page_ids, body.approve)


@router.post("/companies/{company_id}/pages/indexed", dependencies=auth)
def do_indexed(company_id: uuid.UUID, slugs: list[str], db: Session = Depends(get_db)):
    return {"marked": mark_indexed(db, _company(company_id, db), slugs)}


# ---------- public serving ----------
@router.get("/p/{company_id}/sitemap.xml")
def serve_sitemap(company_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    c = _company(company_id, db)
    pages = db.scalars(select(Page).where(Page.company_id == c.id)).all()
    return Response(sitemap(c, pages, str(request.base_url)), media_type="application/xml")


@router.get("/p/{company_id}/{slug}")
def serve_page(company_id: uuid.UUID, slug: str, db: Session = Depends(get_db)):
    c = _company(company_id, db)
    p = db.scalars(select(Page).where(Page.company_id == c.id, Page.slug == slug)).first()
    if not p or p.status == "draft":
        raise HTTPException(404, "page not found")
    return Response(render_page(c, p), media_type="text/html")
