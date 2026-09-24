"""HTML for the public setup wizard (Component 14). Plain server-rendered pages, one CSS block,
no framework: the wizard has to load on a phone in a coffee shop and be done in ten minutes."""
from html import escape as e

from ..interfaces.billing_oauth import PLANS

CSS = """
:root{--ink:#14140f;--mute:#6b6a60;--line:#e6e4dc;--bg:#f7f6f1;--card:#fff;--acc:#1d4ed8;--ok:#15803d;--warn:#b45309}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 -apple-system,Inter,Segoe UI,sans-serif}
.wrap{max-width:640px;margin:0 auto;padding:32px 16px 64px}
.brand{font-weight:700;letter-spacing:-.01em;margin-bottom:24px;display:flex;justify-content:space-between;align-items:center}
.brand small{color:var(--mute);font-weight:400}
.steps{display:flex;gap:6px;margin:0 0 20px}.steps i{flex:1;height:4px;border-radius:2px;background:var(--line)}.steps i.on{background:var(--acc)}.steps i.done{background:var(--ok)}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:24px}
h1{font-size:24px;margin:0 0 6px;letter-spacing:-.02em}h2{font-size:17px;margin:20px 0 8px}p.sub{color:var(--mute);margin:0 0 20px}
label{display:block;font-size:13px;font-weight:600;margin:14px 0 4px}
input,textarea,select{width:100%;padding:10px 12px;border:1px solid var(--line);border-radius:8px;font:inherit;background:#fff}
textarea{min-height:72px}
.row{display:grid;grid-template-columns:1fr 1fr;gap:12px}@media(max-width:520px){.row{grid-template-columns:1fr}}
button,.btn{display:inline-block;margin-top:20px;background:var(--acc);color:#fff;border:0;border-radius:8px;padding:12px 18px;font:inherit;font-weight:600;cursor:pointer;text-decoration:none}
.btn.ghost{background:#fff;color:var(--ink);border:1px solid var(--line)}
.cust{border:1px dashed var(--line);border-radius:8px;padding:12px;margin-top:12px}
.tag{display:inline-block;font-size:12px;padding:2px 8px;border-radius:999px;background:#eef2ff;color:var(--acc);margin-left:8px}
.tag.ok{background:#ecfdf5;color:var(--ok)}
.score{display:flex;align-items:baseline;gap:10px}.score b{font-size:48px;letter-spacing:-.03em}.score span{color:var(--mute)}
.bars{margin:16px 0}.bar{display:grid;grid-template-columns:110px 1fr 36px;gap:10px;align-items:center;margin:6px 0;font-size:14px}
.bar i{height:8px;border-radius:4px;background:var(--line);display:block;position:relative}.bar i b{position:absolute;left:0;top:0;bottom:0;border-radius:4px;background:var(--acc)}
.plans{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:16px}@media(max-width:520px){.plans{grid-template-columns:1fr}}
.plan{border:1px solid var(--line);border-radius:10px;padding:16px}.plan b{font-size:22px;display:block}.plan small{color:var(--mute)}
.plan.pick{border-color:var(--acc);box-shadow:0 0 0 2px #dbe4ff}
.opt{display:flex;gap:12px;align-items:flex-start;padding:12px;border:1px solid var(--line);border-radius:8px;margin-top:10px}.opt input{width:auto;margin-top:4px}
.opt div b{display:block}.opt div small{color:var(--mute)}
ul.list{padding-left:18px;margin:6px 0}.note{font-size:13px;color:var(--mute);margin-top:16px}
.done{text-align:center;padding:24px 0}.done .big{font-size:56px}
code{background:#f1f0ea;padding:2px 6px;border-radius:4px}
"""


def shell(title: str, body: str, step: int | None = None) -> str:
    bar = ""
    if step:
        bar = '<div class="steps">' + "".join(f'<i class="{"done" if i < step else "on" if i == step else ""}"></i>' for i in range(1, 9)) + "</div>"
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)} · Marketing Engineer</title><style>{CSS}</style></head><body><div class="wrap">
<div class="brand">Marketing Engineer <small>{('step ' + str(step) + ' of 8') if step else ''}</small></div>{bar}
<div class="card">{body}</div></div></body></html>"""


def landing(error: str | None = None) -> str:
    return shell("Start", f"""
<h1>Your marketing engineer, over text.</h1>
<p class="sub">Ten minutes of setup. A free growth diagnostic before you pay anything. Then one voice memo a week, and it drafts, you approve, it posts.</p>
<form method="post" action="/start">
<label>Work email</label><input name="email" type="email" required placeholder="you@company.com">
{f'<p style="color:#b91c1c">{e(error)}</p>' if error else ''}
<button>Start the free diagnostic →</button></form>
<p class="note">No card until you have seen your scorecard. Nothing is ever posted without your yes.</p>""")


def step1(s, error=None) -> str:
    d = s.data or {}
    return shell("Your company", f"""
<h1>Your company</h1><p class="sub">This is what the engineer reads first.</p>
<form method="post" action="/setup/{e(s.token)}/1">
<div class="row"><div><label>Company name</label><input name="company_name" required value="{e(d.get('company_name',''))}"></div>
<div><label>Website</label><input name="website" required placeholder="https://" value="{e(d.get('website',''))}"></div></div>
<label>What you do, in one sentence</label><input name="one_line" required value="{e(d.get('one_line',''))}" placeholder="e.g. AI phone agents for real-estate brokerages">
<label>Your name (the founder whose voice we post in)</label><input name="founder_name" required value="{e(d.get('founder_name',''))}">
<label>If your site blocks robots, paste your homepage text here (optional)</label><textarea name="site_text">{e(d.get('site_text',''))}</textarea>
{f'<p style="color:#b91c1c">{e(error)}</p>' if error else ''}
<button>Continue →</button></form>""", 1)


def step2(s, error=None) -> str:
    cs = (s.data or {}).get("customers") or [{}, {}, {}]
    while len(cs) < 3:
        cs.append({})
    blocks = "".join(f"""<div class="cust"><b>Customer {i+1}</b>
<div class="row"><div><label>Company</label><input name="c{i}_company" value="{e(c.get('company',''))}" {'required' if i == 0 else ''}></div>
<div><label>Their website</label><input name="c{i}_domain" value="{e(c.get('domain','') or '')}"></div></div>
<div class="row"><div><label>Person who bought</label><input name="c{i}_person" value="{e(c.get('person',''))}"></div>
<div><label>Their role</label><input name="c{i}_role" value="{e(c.get('role',''))}"></div></div>
<label>Why they bought (one line)</label><input name="c{i}_why" value="{e(c.get('why_they_bought',''))}"></div>""" for i, c in enumerate(cs[:3]))
    return shell("Best customers", f"""
<h1>Your three best customers</h1><p class="sub">The engineer builds your ideal customer profile from people who already pay you. One is enough to start.</p>
<form method="post" action="/setup/{e(s.token)}/2">{blocks}
{f'<p style="color:#b91c1c">{e(error)}</p>' if error else ''}
<button>Continue →</button></form>""", 2)


def step3(s) -> str:
    conn = set((s.data or {}).get("connected", []))
    def row(p, label):
        ok = p in conn
        return (f'<div class="opt"><div style="flex:1"><b>{label} {"<span class=tag ok>connected</span>" if ok else ""}</b>'
                f'<small>{"We post in your name, only after you approve each one." if not ok else "You can disconnect any time from your account page."}</small></div>'
                f'<a class="btn {"ghost" if ok else ""}" style="margin:0" href="/setup/{e(s.token)}/oauth/{p}">{"Reconnect" if ok else "Connect"}</a></div>')
    return shell("Connect", f"""
<h1>Connect your accounts</h1><p class="sub">Founder accounts, not company pages: that is where the attention is.</p>
{row('linkedin', 'LinkedIn')}{row('x', 'X')}
<form method="post" action="/setup/{e(s.token)}/3"><button class="{'' if conn else 'btn ghost'}">{'Continue →' if conn else 'Skip for now →'}</button></form>
<p class="note">Tokens are encrypted at rest. The engineer only ever gets the permission to post and read replies.</p>""", 3)


def step4(s, sent: bool = False, code_hint: str | None = None, error=None) -> str:
    d = s.data or {}
    if sent:
        return shell("Phone", f"""
<h1>Check your phone</h1><p class="sub">We texted a 6-digit code to <b>{e(d.get('phone',''))}</b>. Reply to that text with the code, then come back here.</p>
{f'<p class="note">Local/test mode: the code is <code>{e(code_hint)}</code>. POST it to <code>/public/sms/inbound</code> as the founder to simulate the reply.</p>' if code_hint else ''}
<form method="post" action="/setup/{e(s.token)}/4/check"><button>I replied →</button></form>
<form method="post" action="/setup/{e(s.token)}/4"><input type="hidden" name="phone" value="{e(d.get('phone',''))}"><button class="btn ghost">Resend the code</button></form>
{f'<p style="color:#b91c1c">{e(error)}</p>' if error else ''}""", 4)
    return shell("Phone", f"""
<h1>Your phone number</h1><p class="sub">Everything after this happens over text: the morning brief, the drafts to approve, the Friday number.</p>
<form method="post" action="/setup/{e(s.token)}/4">
<label>Mobile number (with country code)</label><input name="phone" required placeholder="+13055551234" value="{e(d.get('phone',''))}">
{f'<p style="color:#b91c1c">{e(error)}</p>' if error else ''}
<button>Text me a code →</button></form>""", 4)


def step5(s) -> str:
    d = s.data or {}
    mode = d.get("schedule_mode", "managed")
    hour = int(d.get("brief_hour", 8))
    hours = "".join(f'<option value="{h}" {"selected" if h == hour else ""}>{h}:00</option>' for h in range(5, 13))
    return shell("Preferences", f"""
<h1>How hands-on do you want to be?</h1><p class="sub">Either way, nothing posts without your yes. This is only about <i>when</i>.</p>
<form method="post" action="/setup/{e(s.token)}/5">
<label class="opt"><input type="radio" name="schedule_mode" value="managed" {"checked" if mode == "managed" else ""}><div><b>We manage the schedule</b><small>You approve the words; the engineer picks the slot from your audience's active hours and posts it. The recommended way.</small></div></label>
<label class="opt"><input type="radio" name="schedule_mode" value="approve_times" {"checked" if mode == "approve_times" else ""}><div><b>I approve the time too</b><small>Every draft comes with its slot; reply with a different time to move it.</small></div></label>
<div class="row"><div><label>Morning brief at</label><select name="brief_hour">{hours}</select></div>
<div><label>Time zone</label><select name="tz">{"".join(f'<option {"selected" if d.get("tz", "America/New_York") == z else ""}>{z}</option>' for z in ("America/New_York","America/Chicago","America/Denver","America/Los_Angeles","Europe/London","Europe/Amsterdam","Europe/Berlin","Asia/Singapore","Australia/Sydney"))}</select></div></div>
<button>Run my free diagnostic →</button></form>""", 5)


def step6_wait(s) -> str:
    return shell("Diagnostic", f"""
<h1>Reading your company…</h1><p class="sub">Site, customers, and both founder feeds. About a minute.</p>
<meta http-equiv="refresh" content="4;url=/setup/{e(s.token)}/6">
<p class="note">This page refreshes itself.</p>""", 6)


def step6(s, summary: dict) -> str:
    ch = summary.get("channels") or {}
    labels = {"content": "Content", "seo": "SEO", "social": "Social", "email": "Email", "launches": "Launches", "community": "Community", "partnerships": "Partners", "ads": "Ads", "product_led": "Product-led"}
    bars = "".join(f'<div class="bar"><span>{labels.get(k, k)}</span><i><b style="width:{int(float(v)*10)}%"></b></i><span>{v}</span></div>' for k, v in sorted(ch.items(), key=lambda kv: -float(kv[1] or 0)))
    plan = "".join(f"<li>{e(str(x))}</li>" for x in (summary.get("first_two_weeks") or []))
    return shell("Diagnostic", f"""
<h1>Your growth scorecard</h1><p class="sub">{e(summary.get('headline') or '')}</p>
<div class="score"><b>{summary.get('overall')}</b><span>/ 10 today</span></div>
<div class="bars">{bars}</div>
<h2>First two weeks</h2><ul class="list">{plan}</ul>
<a class="btn" href="/setup/{e(s.token)}/7">Start the engine →</a>
<p class="note">Everything above was free. The engine, the weekly memo, the posting and outreach start once you subscribe.</p>""", 6)


def step7(s, error=None) -> str:
    pick = (s.data or {}).get("plan", "founder")
    desc = {"founder": "One founder, LinkedIn + X, weekly memo, morning brief, Friday number.",
            "team": "Up to three founders, plus launch kits, pages and outreach at volume.",
            "growth": "Everything, plus a human check on every week's plan and quarterly review."}
    cards = "".join(f"""<label class="plan {'pick' if k == pick else ''}"><input type="radio" name="plan" value="{k}" {"checked" if k == pick else ""} style="width:auto">
<b>${v['monthly_usd']:,}</b><small>/month · {v['name']}</small><p style="font-size:13px;margin:8px 0 0">{desc[k]}</p></label>""" for k, v in PLANS.items())
    return shell("Subscribe", f"""
<h1>Pick a plan</h1><p class="sub">Cancel any time. If you cancel, posting stops; your data and your scorecards stay.</p>
<form method="post" action="/setup/{e(s.token)}/7"><div class="plans">{cards}</div>
{f'<p style="color:#b91c1c">{e(error)}</p>' if error else ''}
<button>Continue to payment →</button></form>""", 7)


def step7_pending(s) -> str:
    return shell("Confirming", f"""
<h1>Confirming your payment…</h1><p class="sub">Usually a few seconds.</p>
<meta http-equiv="refresh" content="3;url=/setup/{e(s.token)}">""", 7)


def step8(s, first_text: str | None) -> str:
    d = s.data or {}
    return shell("Live", f"""
<div class="done"><div class="big">✓</div><h1>You're live.</h1>
<p class="sub">Check your phone. The first text is on its way to <b>{e(d.get('phone',''))}</b>.</p></div>
{f'<div class="cust" style="white-space:pre-wrap;font-size:14px">{e(first_text)}</div>' if first_text else ''}
<h2>What happens now</h2><ul class="list">
<li>Tomorrow at {d.get('brief_hour', 8)}:00 you get your first morning brief.</li>
<li>Whenever you're ready, send a 10-minute voice memo about the week. Drafts follow within the hour.</li>
<li>Reply <code>yes 1 3</code>, <code>no 2</code>, or type an edit. Nothing posts without your yes.</li>
<li>Friday: one number.</li></ul>
<a class="btn ghost" href="/account/{e(s.token)}">Your account page</a>""", 8)


def account(s, sub, founder, tokens: list, portal: str | None) -> str:
    status = sub.status if sub else "none"
    conn = "".join(f'<li>{t.platform}: <b>@{e(t.handle or "")}</b></li>' for t in tokens) or "<li>none connected</li>"
    return shell("Account", f"""
<h1>Account</h1><p class="sub">{e(s.email)}</p>
<h2>Subscription <span class="tag {'ok' if status in ('active','trialing') else ''}">{e(status)}</span></h2>
<p>{e((sub.plan.title() + ' plan') if sub else 'No plan yet')}{(' · renews ' + sub.current_period_end.date().isoformat()) if sub and sub.current_period_end else ''}</p>
{f'<a class="btn ghost" href="{e(portal)}">Manage billing</a>' if portal else ''}
<h2>Connected</h2><ul class="list">{conn}</ul>
<a class="btn ghost" href="/setup/{e(s.token)}/oauth/linkedin">Reconnect LinkedIn</a> <a class="btn ghost" href="/setup/{e(s.token)}/oauth/x">Reconnect X</a>
<h2>Phone</h2><p>{e(founder.phone or '')} {'<span class="tag ok">verified</span>' if founder.phone_verified_at else ''} · schedule: <b>{e(founder.schedule_mode)}</b></p>
<p class="note">Text <code>pause</code> to stop the briefs, <code>resume</code> to restart, <code>help</code> for everything else.</p>""")
