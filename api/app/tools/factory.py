"""Tool factory (Component 11).

  propose(company)   3 tool ideas from the product's data assets + the ICP's questions (LLM, rules fallback)
  build(tool)        a spec -> validated -> status draft; the founder approves -> published
  render(tool)       one self-contained HTML page: inputs, logic in plain JS from the spec, result, lead capture
  events             view / run / lead; leads also land in signup_source with channel 'tool:{slug}'

Spec shape (all four kinds share it):
  question   what the tool answers, in the ICP's words
  inputs     [{id, label, type: number|select|text, default?, options?[], min?, max?, unit?}]
  logic      calculator: {formula: "js expression over input ids", unit}
             scorecard:  {rules: [{if: "js expr", points, label}], max_points, bands: [{min, label, advice}]}
             generator:  {template: "text with {input_id}", variants?: [..]}
             lookup:     {table: [{key, ...cols}], key_input, columns: [..]}
  result     {headline: "text with {value}", explain: "...", cta: "..."}
  capture    {when: "after_result"|"before_result", fields: ["email"], promise: "what they get"}
  data_source  the real data point(s) the logic is anchored to (shown on the page)
Formulas are evaluated in the browser with a tiny safe evaluator (no eval): + - * / ( ) numbers and input ids."""
from datetime import datetime, timezone
from html import escape
import json
import re
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..interfaces import get_llm
from ..models import ICP, Company, Tool, ToolEvent

PROPOSE_SYS = """You propose three free web tools a B2B software company can publish to attract its ICP.
Each must answer a question the ICP actually asks, using a data asset the company really has, and be buildable as
ONE page with a few inputs. Kinds: calculator (a number from inputs), scorecard (points -> band + advice),
generator (text from inputs), lookup (a value from a table). Return JSON:
{"tools": [{"name", "slug", "kind", "question", "rationale", "inputs": [...], "logic": {...}, "result": {...}, "capture": {...}, "data_source": "..."}]}
using the spec shape given. Formulas may only use + - * / parentheses, numbers and input ids."""

FORMULA_OK = re.compile(r"^[\w\s\.\+\-\*/\(\),<>=!&|?:']+$")


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60]


def _fallback_ideas(company: Company, summary: dict, icp: ICP | None) -> list[dict]:
    seg = ((icp.firmographics or {}).get("industry") or ["your team"])[0] if icp else "your team"
    assets = summary.get("data_assets") or ["internal usage data"]
    one = summary.get("one_liner") or company.name
    return [
        {"name": f"Time saved calculator for {seg}", "slug": _slug(f"time-saved-{seg}"), "kind": "calculator",
         "question": f"How many hours a month would {seg} get back?",
         "rationale": f"Anchored to {assets[0]}; the ICP's first question is 'what does it save me'.",
         "inputs": [{"id": "people", "label": "People doing this work", "type": "number", "default": 10, "min": 1, "max": 5000},
                    {"id": "tasks_week", "label": "Tasks per person per week", "type": "number", "default": 5, "min": 1, "max": 200},
                    {"id": "minutes", "label": "Minutes per task today", "type": "number", "default": 240, "min": 5, "max": 1200, "unit": "min"}],
         "logic": {"formula": "people * tasks_week * 4.3 * (minutes - 15) / 60", "unit": "hours / month"},
         "result": {"headline": "{value} hours a month back", "explain": "Assumes each task drops to 15 minutes, the median we measured.", "cta": f"See how {one} does it"},
         "capture": {"when": "after_result", "fields": ["email"], "promise": "Get the full model as a spreadsheet"},
         "data_source": assets[0]},
        {"name": f"Readiness scorecard for {seg}", "slug": _slug(f"readiness-{seg}"), "kind": "scorecard",
         "question": f"Is your {seg} ready to roll this out?",
         "rationale": "Scorecards get shared internally; the band and advice do the selling.",
         "inputs": [{"id": "champion", "label": "Do you have an internal champion?", "type": "select", "options": ["yes", "no"], "default": "no"},
                    {"id": "data", "label": "Is your data in one system?", "type": "select", "options": ["yes", "mostly", "no"], "default": "mostly"},
                    {"id": "pilot", "label": "Can you pilot with 10 people first?", "type": "select", "options": ["yes", "no"], "default": "yes"},
                    {"id": "compliance_weeks", "label": "Weeks your compliance review takes", "type": "number", "default": 4, "min": 0, "max": 52}],
         "logic": {"rules": [{"if": "champion == 'yes'", "points": 30, "label": "champion"}, {"if": "data == 'yes'", "points": 25, "label": "data in one place"},
                             {"if": "data == 'mostly'", "points": 12, "label": "data mostly in one place"}, {"if": "pilot == 'yes'", "points": 25, "label": "pilot group"},
                             {"if": "compliance_weeks <= 4", "points": 20, "label": "fast compliance"}],
                   "max_points": 100, "bands": [{"min": 75, "label": "Ready", "advice": "Start with the ten loudest users this month."},
                                                {"min": 45, "label": "Nearly", "advice": "Fix the one missing item, then pilot."},
                                                {"min": 0, "label": "Not yet", "advice": "Get a champion and a pilot group before buying anything."}]},
         "result": {"headline": "{band}: {value}/100", "explain": "Based on what made rollouts succeed across our customers.", "cta": "Talk to us about your rollout"},
         "capture": {"when": "after_result", "fields": ["email"], "promise": "Get your scorecard and the rollout checklist"},
         "data_source": "rollout outcomes across customers"},
        {"name": "Rollout plan generator", "slug": "rollout-plan-generator", "kind": "generator",
         "question": "What should the first 30 days of a rollout look like?",
         "rationale": "A generator produces something the ICP forwards to their boss.",
         "inputs": [{"id": "team", "label": "Team or company name", "type": "text", "default": "Acme"},
                    {"id": "n", "label": "Number of users", "type": "number", "default": 50, "min": 1, "max": 10000},
                    {"id": "start", "label": "Start week", "type": "text", "default": "next Monday"}],
         "logic": {"template": "30-day rollout for {team}\n\nWeek 1 (from {start}): pick the 10 loudest of your {n} users. Ship to them only.\nWeek 2: fix what they hit. Daily 15-minute check-in.\nWeek 3: open to the next 40%. Publish the two-minute walkthrough.\nWeek 4: everyone. Measure completion; target 80%."},
         "result": {"headline": "Your 30-day plan", "explain": "The sequence we use with every customer.", "cta": "Run it with us"},
         "capture": {"when": "after_result", "fields": ["email"], "promise": "Email me this plan as a doc"},
         "data_source": "rollout playbook"},
    ]


def propose(db: Session, company: Company) -> list[dict]:
    llm = get_llm()
    try:
        summary = json.loads(company.product_summary or "{}") or {}
    except json.JSONDecodeError:
        summary = {}
    icp = db.scalars(select(ICP).where(ICP.company_id == company.id).order_by(ICP.version.desc())).first()
    raw = llm.complete(PROPOSE_SYS, json.dumps({"company": company.name, "product": summary,
                                                "icp": icp.description if icp else None, "personas": icp.personas if icp else []}),
                       purpose="tool_propose", json_mode=True, max_tokens=2500).text
    try:
        ideas = json.loads(raw).get("tools") or []
        if not ideas or json.loads(raw).get("fake"):
            raise ValueError
    except (json.JSONDecodeError, ValueError):
        ideas = _fallback_ideas(company, summary, icp)
    existing = {t.slug for t in db.scalars(select(Tool).where(Tool.company_id == company.id))}
    out = []
    for i in ideas[:3]:
        slug = i.get("slug") or _slug(i["name"])
        if slug in existing:
            continue
        ok, why = validate_spec(i)
        if not ok:
            continue
        t = Tool(company_id=company.id, slug=slug, name=i["name"], kind=i["kind"], status="proposed", rationale=i.get("rationale"),
                 spec={k: i.get(k) for k in ("question", "inputs", "logic", "result", "capture", "data_source")})
        db.add(t)
        out.append(t)
    db.commit()
    return [_out(t) for t in out]


def validate_spec(spec: dict) -> tuple[bool, str]:
    kind = spec.get("kind")
    inputs = spec.get("inputs") or []
    ids = {i.get("id") for i in inputs}
    if kind not in ("calculator", "scorecard", "generator", "lookup"):
        return False, "bad kind"
    if not inputs or not ids or None in ids:
        return False, "inputs need ids"
    logic = spec.get("logic") or {}
    if kind == "calculator":
        f = logic.get("formula", "")
        if not f or not FORMULA_OK.match(f):
            return False, "formula has disallowed characters"
        for tok in re.findall(r"[A-Za-z_]\w*", f):
            if tok not in ids:
                return False, f"formula uses unknown id {tok}"
    if kind == "scorecard":
        if not logic.get("rules") or not logic.get("bands"):
            return False, "scorecard needs rules and bands"
        for r in logic["rules"]:
            if not FORMULA_OK.match(r.get("if", "")):
                return False, "rule has disallowed characters"
    if kind == "generator" and not logic.get("template"):
        return False, "generator needs a template"
    if kind == "lookup" and not (logic.get("table") and logic.get("key_input") in ids):
        return False, "lookup needs a table and key_input"
    if not (spec.get("result") or {}).get("headline"):
        return False, "result needs a headline"
    return True, "ok"


def decide(db: Session, tool: Tool, approve: bool) -> Tool:
    if approve:
        tool.status = "published"
        tool.published_at = datetime.now(timezone.utc)
    else:
        tool.status = "retired"
    db.commit()
    db.refresh(tool)
    return tool


def _out(t: Tool) -> dict:
    return {"id": str(t.id), "slug": t.slug, "name": t.name, "kind": t.kind, "status": t.status, "rationale": t.rationale,
            "spec": t.spec, "url": f"/t/{t.company_id}/{t.slug}", "published_at": t.published_at}


def stats(db: Session, tool: Tool) -> dict:
    rows = dict(db.execute(select(ToolEvent.kind, func.count()).where(ToolEvent.tool_id == tool.id).group_by(ToolEvent.kind)).all())
    views, runs, leads = rows.get("view", 0), rows.get("run", 0), rows.get("lead", 0)
    return {"views": views, "runs": runs, "leads": leads, "run_rate": round(runs / views, 3) if views else None,
            "lead_rate": round(leads / runs, 3) if runs else None}


# ---------- rendering ----------
SAFE_EVAL_JS = r"""
// tiny expression evaluator: numbers, ids, + - * / ( ) and comparisons/logic for scorecard rules. no eval.
function tok(s){const r=/\s*(\d+\.?\d*|[A-Za-z_]\w*|'[^']*'|==|!=|<=|>=|&&|\|\||[-+*/()<>?:])/g;let m,o=[];while((m=r.exec(s))){o.push(m[1]);}return o;}
function ev(s,env){const t=tok(s);let i=0;
 function val(){let x=t[i++];if(x==='('){const v=expr();i++;return v;}if(x==='-'){return -val();}if(/^\d/.test(x))return parseFloat(x);if(/^'/.test(x))return x.slice(1,-1);if(x in env){const v=env[x];return isNaN(parseFloat(v))?v:parseFloat(v);}throw new Error('bad '+x);}
 function term(){let v=val();while(t[i]==='*'||t[i]==='/'){const o=t[i++];const r=val();v=o==='*'?v*r:v/r;}return v;}
 function sum(){let v=term();while(t[i]==='+'||t[i]==='-'){const o=t[i++];const r=term();v=o==='+'?v+r:v-r;}return v;}
 function cmp(){let v=sum();while(['<','>','<=','>=','==','!='].includes(t[i])){const o=t[i++];const r=sum();v=o==='<'?v<r:o==='>'?v>r:o==='<='?v<=r:o==='>='?v>=r:o==='=='?v==r:v!=r;}return v;}
 function logic(){let v=cmp();while(t[i]==='&&'||t[i]==='||'){const o=t[i++];const r=cmp();v=o==='&&'?(v&&r):(v||r);}return v;}
 function expr(){return logic();}
 return expr();}
"""


def render(company: Company, tool: Tool, api_base: str) -> str:
    e = escape
    sp = tool.spec
    inputs_html = ""
    for i in sp.get("inputs", []):
        if i["type"] == "select":
            opts = "".join(f'<option {"selected" if o == i.get("default") else ""}>{e(str(o))}</option>' for o in i.get("options", []))
            ctl = f'<select id="{e(i["id"])}">{opts}</select>'
        else:
            typ = "number" if i["type"] == "number" else "text"
            mn = f'min="{i["min"]}"' if i.get("min") is not None else ""
            mx = f'max="{i["max"]}"' if i.get("max") is not None else ""
            ctl = f'<input id="{e(i["id"])}" type="{typ}" value="{e(str(i.get("default", "")))}" {mn} {mx}>'
        inputs_html += f'<label>{e(i["label"])}{" (" + e(i["unit"]) + ")" if i.get("unit") else ""}{ctl}</label>'
    spec_json = json.dumps({"kind": tool.kind, "inputs": sp.get("inputs", []), "logic": sp.get("logic", {}),
                            "result": sp.get("result", {}), "capture": sp.get("capture", {})})
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{e(tool.name)} — {e(company.name)}</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="{e(sp.get('question', ''))}">
<style>body{{font-family:Helvetica,Arial,sans-serif;color:#141414;max-width:640px;margin:0 auto;padding:40px 20px;line-height:1.5}}
h1{{font-size:30px;letter-spacing:-.02em;margin:0 0 6px}} .q{{color:#444;font-size:18px;margin:0 0 24px}}
label{{display:block;margin:12px 0;font-size:14px;color:#333}} input,select{{display:block;width:100%;padding:10px;font-size:16px;border:1px solid #ccc;border-radius:6px;margin-top:4px;box-sizing:border-box}}
button{{padding:12px 18px;font-size:16px;background:#141414;color:#fff;border:0;border-radius:6px;cursor:pointer;margin-top:12px}}
.res{{display:none;background:#f3f5fa;border-left:3px solid #1f4fd1;padding:16px;margin:24px 0}} .res b{{display:block;font-size:26px;margin-bottom:6px}} pre{{white-space:pre-wrap;font-family:inherit}}
.cap{{display:none;border:1px solid #ddd;border-radius:6px;padding:14px;margin-top:16px}} .m{{color:#666;font-size:13px;margin-top:36px}}</style></head><body>
<h1>{e(tool.name)}</h1><p class="q">{e(sp.get('question', ''))}</p>
<form id="f">{inputs_html}<button type="submit">Calculate</button></form>
<div class="res" id="res"><b id="h"></b><div id="x"></div><pre id="body"></pre></div>
<div class="cap" id="cap"><div><b>{e((sp.get('capture') or {}).get('promise', 'Get the full result'))}</b></div>
<form id="lead"><input name="email" type="email" placeholder="work email" required><button type="submit">Send it</button></form></div>
<p class="m">Anchored to: {e(sp.get('data_source', ''))} · a free tool by <a href="{e('https://' + (company.domain or ''))}">{e(company.name)}</a></p>
<script>const SPEC={spec_json};const API="{e(api_base)}";const TOOL="{tool.id}";
{SAFE_EVAL_JS}
function env(){{const o={{}};SPEC.inputs.forEach(i=>{{o[i.id]=document.getElementById(i.id).value;}});return o;}}
function fill(s,v){{return s.replace(/\\{{(\\w+)\\}}/g,(m,k)=>v[k]!==undefined?v[k]:m);}}
function beacon(kind,payload){{try{{navigator.sendBeacon(API+"/public/tools/"+TOOL+"/event",new Blob([JSON.stringify({{kind,payload}})],{{type:"application/json"}}));}}catch(e){{}}}}
beacon("view",{{}});
document.getElementById("f").addEventListener("submit",function(ev){{ev.preventDefault();const v=env();let out={{}};
 if(SPEC.kind==="calculator"){{const n=ev_(SPEC.logic.formula,v);out.value=Math.round(n).toLocaleString();out.unit=SPEC.logic.unit||"";}}
 else if(SPEC.kind==="scorecard"){{let pts=0,hits=[];SPEC.logic.rules.forEach(r=>{{if(ev_(r.if,v)){{pts+=r.points;hits.push(r.label);}}}});const band=SPEC.logic.bands.find(b=>pts>=b.min)||SPEC.logic.bands[SPEC.logic.bands.length-1];out.value=pts;out.band=band.label;out.advice=band.advice;out.hits=hits.join(", ");}}
 else if(SPEC.kind==="generator"){{out.body=fill(SPEC.logic.template,v);}}
 else if(SPEC.kind==="lookup"){{const row=SPEC.logic.table.find(r=>String(r[SPEC.logic.key_input||"key"])==String(v[SPEC.logic.key_input]));out=row||{{value:"not found"}};}}
 const hl=fill(SPEC.result.headline||"",{{...v,...out}});document.getElementById("h").textContent=hl+((out.unit&&!hl.toLowerCase().includes(out.unit.split(" ")[0].toLowerCase()))?" "+out.unit:"");
 document.getElementById("x").textContent=(out.advice?out.advice+" ":"")+(SPEC.result.explain||"");
 document.getElementById("body").textContent=out.body||"";
 document.getElementById("res").style.display="block";document.getElementById("cap").style.display="block";
 beacon("run",{{inputs:v,out}});}});
function ev_(s,v){{try{{return ev(s,v);}}catch(e){{return 0;}}}}
document.getElementById("lead").addEventListener("submit",function(ev){{ev.preventDefault();const em=this.email.value;beacon("lead",{{email:em}});
 this.innerHTML="<b>Sent. Check your inbox.</b>";}});
</script></body></html>"""
