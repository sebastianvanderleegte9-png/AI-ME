"""The public marketing site, served at / (Component 14b). One page, no build step.
Brand tokens (name, font, palette) come from settings so they change without a deploy of code.
The font is fetched from api.fonts.coollabs.io, a privacy-friendly Google Fonts mirror.

Layout follows the structural pattern of a premium dark-mode SaaS template (floating pill nav,
hero with an elevated product-preview card, a bento feature grid with a terminal mock, a pricing
card row, a watermark footer) — reskinned entirely in Aime's own navy palette and copy. Two things
are deliberately NOT copied from that reference: fabricated social proof (star-rated testimonials
from invented people, "N developers already use this") and made-up business metrics (a specific
revenue number, an uptime SLA) — Aime doesn't have real customers yet, so the hero's preview card
is explicitly labeled illustrative, and the "what people think" slot uses the product's real,
already-shipped rules instead of invented quotes."""
from html import escape as e
from urllib.parse import quote

from ..interfaces.billing_oauth import PLANS
from ..settings import settings
from .icons import icon

# Navy palette: deep navy ground, electric-blue accent, warm off-white type.
BRAND_CSS = """
:root{--font:%(font)s,-apple-system,"Segoe UI",sans-serif;--bg:#070d1a;--bg2:#0c1527;--card:#101b31;--line:#1c2a45;
--ink:#f4f6fb;--mute:#93a0ba;--acc:#3b82f6;--acc2:#8fb4ff;--navy:#1e3a8a;--ok:#34d399;--warn:#fbbf24}
""" % {"font": '"%s"' % settings.site_font}


def font_link() -> str:
    fam = quote(settings.site_font) + ":wght@" + settings.site_font_weights
    return (f'<link rel="preconnect" href="{settings.font_css_base.split("/css2")[0]}">'
            f'<link rel="stylesheet" href="{settings.font_css_base}?family={fam}&display=swap">')


CSS = """
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 var(--font);-webkit-font-smoothing:antialiased}
a{color:inherit;text-decoration:none}
.wrap{max-width:1160px;margin:0 auto;padding:0 22px}

/* ---------- floating pill nav ---------- */
.navpad{position:sticky;top:14px;z-index:20;padding:0 16px}
nav{max-width:1160px;margin:0 auto;background:rgba(12,21,39,.78);backdrop-filter:blur(16px);
  border:1px solid var(--line);border-radius:18px;box-shadow:0 12px 32px -16px rgba(0,0,0,.6)}
nav .inner{display:flex;align-items:center;justify-content:space-between;height:62px;padding:0 18px}
.logo{display:flex;align-items:center;gap:9px;font-weight:800;font-size:18px;letter-spacing:-.02em}
.logo i{width:26px;height:26px;border-radius:8px;background:linear-gradient(160deg,var(--acc),var(--navy));display:inline-block;position:relative}
.logo i:after{content:"";position:absolute;left:8px;top:8px;width:10px;height:10px;border-radius:3px;background:var(--ink);opacity:.9}
nav .links{display:flex;gap:24px;color:var(--mute);font-size:14.5px;font-weight:500}nav .links a:hover{color:var(--ink)}
@media(max-width:820px){nav .links{display:none}}
.btn{display:inline-flex;align-items:center;gap:7px;background:var(--ink);color:#0a1220;padding:11px 18px;border-radius:999px;font-weight:700;border:0;font:inherit;font-size:14.5px;cursor:pointer;transition:transform .12s,opacity .12s}
.btn:hover{opacity:.88}.btn.ghost{background:transparent;border:1px solid var(--line);color:var(--ink);font-weight:600}
.btn.ghost:hover{background:rgba(255,255,255,.05)}
.btn.big{padding:15px 24px;font-size:16px}.btn svg{flex:none}

/* ---------- hero ---------- */
.hero{padding:74px 0 60px;position:relative;overflow:hidden}
.hero:before{content:"";position:absolute;right:-15%;top:-10%;width:55%;height:110%;background:radial-gradient(closest-side,rgba(59,130,246,.18),transparent);pointer-events:none}
.hero .wrap{position:relative;display:grid;grid-template-columns:1.1fr .9fr;gap:52px;align-items:center}
@media(max-width:940px){.hero .wrap{grid-template-columns:1fr}.hero{padding:52px 0}}
.eyebrow{display:inline-flex;align-items:center;gap:8px;font-size:13px;font-weight:700;color:var(--acc2);
  background:rgba(59,130,246,.12);border:1px solid rgba(59,130,246,.28);border-radius:999px;padding:6px 14px 6px 8px;margin-bottom:24px}
.eyebrow b{background:var(--acc);color:#fff;border-radius:999px;padding:2px 9px;font-size:11px;font-weight:800;letter-spacing:.02em}
h1{font-size:clamp(38px,5.4vw,62px);line-height:1.02;letter-spacing:-.035em;margin:0 0 18px;font-weight:800}
h1 em{font-style:normal;color:var(--acc2)}
.sub{font-size:clamp(16px,1.7vw,18.5px);color:var(--mute);max-width:540px;margin:0 0 28px}
.cta{display:flex;gap:12px;flex-wrap:wrap}.fine{color:var(--mute);font-size:13px;margin-top:16px}
.proof{display:flex;gap:26px;margin-top:36px;flex-wrap:wrap}.proof div b{display:block;font-size:24px;letter-spacing:-.02em}.proof div span{color:var(--mute);font-size:12.5px}

/* ---------- hero preview card (product screen, not a revenue claim) ---------- */
.preview{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:22px 24px;
  box-shadow:0 1px 2px rgba(0,0,0,.3),0 30px 70px -24px rgba(0,0,0,.75)}
.preview .ptop{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:2px}
.preview .plabel{font-size:12px;color:var(--mute);font-weight:600}
.preview .chip{width:32px;height:32px;border-radius:9px;background:rgba(59,130,246,.14);color:var(--acc2);display:flex;align-items:center;justify-content:center}
.preview .pnum{font-size:38px;font-weight:800;letter-spacing:-.02em;margin-top:6px}
.preview .pdelta{display:inline-flex;align-items:center;gap:4px;font-size:12px;font-weight:700;color:var(--ok);
  background:rgba(52,211,153,.13);border-radius:999px;padding:3px 9px;margin-top:8px}
.preview .barlabel{font-size:11px;color:var(--mute);text-transform:uppercase;letter-spacing:.06em;font-weight:700;margin:20px 0 10px}
.preview .bars{display:flex;align-items:flex-end;gap:8px;height:84px}
.preview .bars b{flex:1;border-radius:4px 4px 0 0;background:rgba(59,130,246,.28)}
.preview .bars b.on{background:var(--acc)}
.preview .barx{display:flex;gap:8px;margin-top:6px}.preview .barx span{flex:1;text-align:center;font-size:10.5px;color:var(--mute)}
.preview .pfoot{display:flex;margin-top:18px;padding-top:16px;border-top:1px solid var(--line)}
.preview .pfoot div{flex:1}.preview .pfoot b{display:block;font-size:16px;font-weight:800}.preview .pfoot span{font-size:11.5px;color:var(--mute)}
.preview .caption{font-size:11px;color:var(--mute);opacity:.65;margin-top:14px;text-align:center}

section{padding:88px 0;border-top:1px solid var(--line)}
h2{font-size:clamp(27px,3.6vw,40px);letter-spacing:-.03em;margin:0 0 10px;line-height:1.08;font-weight:800}
.lead{color:var(--mute);font-size:17.5px;max-width:620px;margin:0 0 40px}
.grid{display:grid;gap:16px}.g3{grid-template-columns:repeat(3,1fr)}.g2{grid-template-columns:repeat(2,1fr)}
@media(max-width:820px){.g3,.g2{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:26px;
  box-shadow:0 1px 2px rgba(0,0,0,.25),0 16px 34px -22px rgba(0,0,0,.7);transition:border-color .15s,transform .15s}
.card:hover{border-color:#28395c}
.card h3{margin:0 0 6px;font-size:18px;font-weight:700}.card p{margin:0;color:var(--mute);font-size:15px}
.num{font-size:13px;color:var(--acc2);font-weight:700;margin-bottom:12px;letter-spacing:.02em}
.formula .card{display:flex;gap:16px;align-items:flex-start}.formula .k{flex:0 0 46px;height:46px;border-radius:12px;background:rgba(59,130,246,.14);color:var(--acc2);display:grid;place-items:center;font-weight:800}

/* ---------- bento feature block ---------- */
.bento{display:grid;grid-template-columns:1.35fr .95fr;gap:16px}
@media(max-width:900px){.bento{grid-template-columns:1fr}}
.bcard{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:32px;
  box-shadow:0 1px 2px rgba(0,0,0,.25),0 20px 44px -26px rgba(0,0,0,.75)}
.bcard .ic{width:44px;height:44px;border-radius:12px;background:rgba(52,211,153,.14);color:var(--ok);display:flex;align-items:center;justify-content:center;margin-bottom:18px}
.bcard h3{font-size:24px;margin:0 0 10px;letter-spacing:-.02em}
.bcard p{color:var(--mute);font-size:15.5px;max-width:440px;margin:0 0 22px}
.chiprow{display:flex;flex-wrap:wrap;gap:10px}
.chiprow span{display:flex;align-items:center;gap:7px;background:var(--bg2);border:1px solid var(--line);border-radius:10px;padding:10px 14px;font-size:13.5px;font-weight:600;color:var(--ink)}
.term{background:#050a15;border:1px solid var(--line);border-radius:12px;padding:18px 16px;font:12.5px/1.7 ui-monospace,SFMono-Regular,Menlo,monospace;color:#8fb4ff;min-height:140px}
.term .ok{color:var(--ok)}.term .mute{color:#4b5b7c}.term .cur{display:inline-block;width:7px;height:13px;background:var(--acc2);vertical-align:-2px;animation:blink 1s step-end infinite}
@keyframes blink{50%{opacity:0}}
.badge{display:inline-flex;align-items:center;gap:6px;font-size:11px;font-weight:700;border-radius:999px;padding:4px 10px;margin-top:14px}
.badge.on{background:rgba(52,211,153,.14);color:var(--ok)}
.pairrow{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px}
@media(max-width:820px){.pairrow{grid-template-columns:1fr}}
.pairrow .card{display:flex;justify-content:space-between;align-items:flex-start;gap:14px}

/* ---------- principles (replaces fabricated testimonials) ---------- */
.principles{background:var(--bg2)}
.pquote{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:26px}
.pquote svg{color:var(--acc2);opacity:.5;margin-bottom:10px}
.pquote p{font-size:16px;line-height:1.5;margin:0 0 14px}
.pquote .who{display:flex;align-items:center;gap:9px;font-size:12.5px;color:var(--mute);font-weight:600}
.pquote .who i{width:8px;height:8px;border-radius:50%;background:var(--ok);display:inline-block}

/* ---------- pricing ---------- */
.plans{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}@media(max-width:820px){.plans{grid-template-columns:1fr}}
.plan{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:28px;display:flex;flex-direction:column}
.plan.pick{border-color:var(--acc);box-shadow:0 0 0 1px var(--acc),0 24px 60px rgba(59,130,246,.15)}
.plan .tag{align-self:flex-start;font-size:11px;font-weight:800;letter-spacing:.03em;color:var(--acc2);background:rgba(59,130,246,.14);border-radius:999px;padding:4px 10px;margin-bottom:14px}
.plan .p{font-size:38px;font-weight:800;letter-spacing:-.03em}.plan .p small{font-size:14px;color:var(--mute);font-weight:400}
.plan .pdesc{color:var(--mute);font-size:13.5px;margin-top:6px}
.plan ul{padding:0;list-style:none;margin:20px 0 24px;flex:1}
.plan li{display:flex;align-items:center;gap:9px;padding:7px 0;color:var(--ink);font-size:14.5px}
.plan li i{flex:none;width:18px;height:18px;border-radius:50%;background:rgba(52,211,153,.15);color:var(--ok);display:flex;align-items:center;justify-content:center}
.plan .btn{width:100%;justify-content:center;background:var(--acc);color:#fff}
.plan.pick .btn{background:var(--ink);color:#0a1220}

.faq details{border-bottom:1px solid var(--line);padding:16px 0}.faq summary{cursor:pointer;font-weight:600;font-size:17px}.faq p{color:var(--mute);margin:10px 0 0}
.final{text-align:center;padding:100px 0;background:linear-gradient(180deg,var(--bg),var(--bg2))}.final .lead{margin:10px auto 30px}

/* ---------- footer ---------- */
footer{border-top:1px solid var(--line);padding-top:56px;overflow:hidden}
.fgrid{display:grid;grid-template-columns:1.3fr repeat(3,.8fr);gap:32px}
@media(max-width:760px){.fgrid{grid-template-columns:1fr 1fr}}
.fgrid h4{font-size:12.5px;text-transform:uppercase;letter-spacing:.06em;color:var(--mute);margin:0 0 14px;font-weight:700}
.fgrid a{display:block;color:var(--mute);font-size:14px;padding:5px 0}.fgrid a:hover{color:var(--ink)}
.fcol p{color:var(--mute);font-size:14px;max-width:260px;margin:0 0 4px}
.fbottom{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;
  border-top:1px solid var(--line);margin-top:44px;padding:22px 0;color:var(--mute);font-size:13px}
.fwatermark{font-size:min(19vw,190px);font-weight:800;letter-spacing:-.04em;line-height:.75;
  color:var(--ink);opacity:.05;margin:20px -4px -6px;white-space:nowrap;user-select:none}
"""

_FEATURES = {
    "founder": ["One founder, LinkedIn + X", "Weekly memo → drafts in your voice", "Morning brief, approve by text", "Attention map + daily replies", "Friday number"],
    "team": ["Up to three founders", "Everything in Founder", "Launch kits and pages", "Outreach and joint posts", "Site fixes and small tools"],
    "growth": ["Everything in Team", "Human review of every weekly plan", "Quarterly growth review", "Priority support", "Custom integrations"],
}
_PLAN_DESC = {"founder": "One founder finding their first channel.", "team": "A small team running the whole loop.", "growth": "Scaling growth with a human in the loop."}


def _plan_card(k: str, v: dict) -> str:
    pick = k == "team"
    tag = '<div class="tag">Most balanced</div>' if pick else ""
    items = "".join(f'<li><i>{icon("check", 11)}</i>{e(x)}</li>' for x in _FEATURES[k])
    return f"""<div class="plan {'pick' if pick else ''}">{tag}<div class="num">{e(v['name'])}</div>
<div class="p">${v['monthly_usd']:,}<small> /month</small></div><div class="pdesc">{e(_PLAN_DESC[k])}</div>
<ul>{items}</ul><a class="btn" href="/start">Start with the free diagnostic</a></div>"""


def page() -> str:
    n = e(settings.site_name)
    plans = "".join(_plan_card(k, v) for k, v in PLANS.items())

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{n} — your marketing engineer, over text</title>
<meta name="description" content="{n} is a marketing engineer that runs on one voice memo a week. Drafts in your voice, you approve by text, it posts, replies, does outreach and reports one number every Friday.">
{font_link()}<style>{BRAND_CSS}{CSS}</style></head><body>

<div class="navpad"><nav><div class="inner"><a class="logo" href="/"><i></i>{n}</a>
<div class="links"><a href="#how">How it works</a><a href="#formula">What it does</a><a href="#principles">Principles</a><a href="#pricing">Pricing</a><a href="#faq">FAQ</a></div>
<div style="display:flex;gap:8px"><a class="btn ghost" href="/start">Sign in</a><a class="btn" href="/start">Free scorecard {icon('arrow-right', 15)}</a></div>
</div></nav></div>

<header class="hero"><div class="wrap">
<div>
<div class="eyebrow"><b>New</b>Outlook outreach &amp; meeting scheduling</div>
<h1>{n} is your <em>marketing engineer.</em></h1>
<p class="sub">Growth on LinkedIn and X, replies where your buyers already are, outbound to real prospects, launches, pages and site fixes — one system, run from a weekly voice memo and a text thread. Not a scheduler. The whole job.</p>
<div class="cta"><a class="btn big" href="/start">Get your free growth scorecard {icon('arrow-right', 16)}</a><a class="btn ghost big" href="#how">{icon('doc', 16)} How it works</a></div>
<div class="fine">Ten-minute setup · no card until you've seen the scorecard · nothing posts without your yes</div>
<div class="proof"><div><b>10 min</b><span>a week from you</span></div><div><b>9</b><span>growth channels, scored</span></div><div><b>0</b><span>posts, emails or meetings booked without your yes</span></div></div>
</div>

<div class="preview">
<div class="ptop"><div><div class="plabel">Impressions inside your ICP</div><div class="pnum">6,100</div>
<div class="pdelta">{icon('trend', 12)} +24% vs last week</div></div>
<div class="chip">{icon('trend', 17)}</div></div>
<div class="barlabel">This week, by day</div>
<div class="bars"><b style="height:38%"></b><b style="height:56%"></b><b class="on" style="height:100%"></b><b style="height:44%"></b><b style="height:72%"></b><b style="height:30%"></b><b style="height:18%"></b></div>
<div class="barx"><span>Mon</span><span>Tue</span><span>Wed</span><span>Thu</span><span>Fri</span><span>Sat</span><span>Sun</span></div>
<div class="pfoot"><div><b>3</b><span>drafts approved</span></div><div><b>1</b><span>meeting booked</span></div><div><b>86%</b><span>approval rate</span></div></div>
<div class="caption">Illustrative — this is what your own dashboard looks like from week one.</div>
</div>
</div></header>

<section id="how"><div class="wrap"><h2>How it works</h2><p class="lead">You already know what happened this week. Saying it out loud is the whole job.</p>
<div class="grid g3">
<div class="card"><div class="num">01 · ONCE</div><h3>Ten-minute setup</h3><p>Company, three best customers, connect LinkedIn and X, your phone. You get a free growth scorecard: nine channels scored, the biggest gap named, your first two weeks planned.</p></div>
<div class="card"><div class="num">02 · WEEKLY</div><h3>One voice memo</h3><p>Ten minutes, whenever. What shipped, what a customer said, what you got wrong, what you believe. {n} pulls the claims and drafts the week in your voice, not "AI voice".</p></div>
<div class="card"><div class="num">03 · DAILY</div><h3>Approve by text, day mapped for you</h3><p>Every morning: your calendar for the day, then a numbered brief of posts, replies and outreach. yes 1 3, no 2, or edit. Meeting requests text you separately the moment a prospect books — yes puts it on your calendar.</p></div>
</div></div></section>

<section id="formula"><div class="wrap"><h2>What a marketing engineer does. All of it.</h2><p class="lead">Not a content calendar with a chatbot on top. Every card below is a system running in {n}, not a slide.</p>

<div class="bento">
<div class="bcard"><div class="ic">{icon('shield', 22)}</div><h3>Your voice, checked every time</h3>
<p>Every draft is scored against how you actually write before it's ever shown to you. Fails the check, it's rejected before you see it — no editing an "AI voice" back into yours.</p>
<div class="chiprow">
<span>{icon('wand', 14)} Voice check</span><span>{icon('compass', 14)} Attention map</span><span>{icon('gauge', 14)} Judgment engine</span><span>{icon('mail', 14)} Outreach</span>
</div></div>
<div class="bcard">
<div class="term">&gt; voice_memo.transcribe()<br>&nbsp;&nbsp;<span class="mute">4 claims extracted</span><br>&gt; drafts.generate(claims, platform=[linkedin, x])<br>&nbsp;&nbsp;<span class="mute">8 formats drafted</span><br>&gt; voice.check(drafts)<br>&nbsp;&nbsp;<span class="ok">✓ 7 passed · 1 rejected</span><br>&gt; feed.queue(approved=false)<br>&nbsp;&nbsp;<span class="mute">waiting for your yes</span><span class="cur"></span></div>
<div class="badge on">{icon('check', 12)} Nothing sends without your yes</div>
</div>
</div>

<div class="pairrow">
<div class="card"><div><h3>Judgment, replanned weekly</h3><p>Scores content, SEO, social, email, launches, community, partners, product-led and ads for <i>your</i> company, then re-sequences every Monday from last week's real numbers.</p></div></div>
<div class="card"><div><h3>Meetings, from your own calendar</h3><p>A prospect replies interested, {n} proposes real times from your Outlook, they book, and it only lands on your calendar once you text yes.</p></div></div>
</div>
</div></section>

<section id="principles" class="principles"><div class="wrap"><h2>What we won't compromise on</h2><p class="lead">Written into the database, not the terms of service — the same five rules that run in production today.</p>
<div class="grid g3">
<div class="pquote">{icon('shield', 22)}<p>A bare "yes" never approves a batch by guess. Every executed post records exactly which reply approved it.</p><div class="who"><i></i>Rule 1 — nothing posts without your yes</div></div>
<div class="pquote">{icon('wand', 22)}<p>Drafts that fail the voice check are never shown to you, let alone posted. Your voice or nothing.</p><div class="who"><i></i>Rule 2 — your voice or nothing</div></div>
<div class="pquote">{icon('users', 22)}<p>No paid ads, no press releases, no company-page filler. Only what actually works for a founder at this stage.</p><div class="who"><i></i>Rule 3 — founder accounts, founder attention</div></div>
</div></div></section>

<section id="pricing"><div class="wrap"><h2>Pricing</h2><p class="lead">A fraction of the hire, and it starts this week. The diagnostic is free either way.</p>
<div class="plans">{plans}</div></div></section>

<section id="faq" class="faq"><div class="wrap"><h2>Questions</h2>
<details><summary>Does it post as me?</summary><p>Yes, from your own LinkedIn and X accounts, after you approve each post by text. You can disconnect from the account page at any time.</p></details>
<details><summary>What does the weekly memo need to contain?</summary><p>Whatever happened. What you shipped, a customer's words, a number you measured, a mistake, a belief. Ten minutes is plenty; {n} extracts the claims and builds the drafts from those.</p></details>
<details><summary>Are LinkedIn and X posts different?</summary><p>Yes. Same claim, different shape: a story on LinkedIn, a single sharp line on X. Both in your voice.</p></details>
<details><summary>Do I have to be on the schedule?</summary><p>No. Pick "we manage the schedule" and it posts at your audience's active hours once you've approved the words. Or approve the time too.</p></details>
<details><summary>What if I don't answer for a week?</summary><p>Nothing goes out. It waits. The brief keeps coming until you text pause.</p></details>
<details><summary>Does it book meetings on my calendar automatically?</summary><p>No — it proposes times from your real Outlook calendar, the prospect picks one, and it only creates the calendar event after you text yes. A no gets fresh times sent automatically, no extra work from you.</p></details>
</div></section>

<section class="final"><div class="wrap"><h2>See your growth score in ten minutes.</h2><p class="lead">Free, before any card. Then decide.</p><a class="btn big" href="/start">Get your free scorecard {icon('arrow-right', 16)}</a></div></section>

<footer class="wrap">
<div class="fgrid">
<div class="fcol"><a class="logo" href="/" style="margin-bottom:12px"><i></i>{n}</a><p>The marketing engineer for founders who'd rather text ten minutes a week than run a content calendar.</p></div>
<div><h4>Product</h4><a href="#how">How it works</a><a href="#formula">What it does</a><a href="#principles">Principles</a><a href="#pricing">Pricing</a></div>
<div><h4>Get started</h4><a href="/start">Free scorecard</a><a href="#faq">Questions</a><a href="mailto:hello@example.com">Contact</a></div>
<div><h4>Account</h4><a href="/start">Sign in</a></div>
</div>
<div class="fwatermark">{n}</div>
<div class="fbottom"><span>© {n}</span><span>Nothing posts, sends or books without your yes.</span></div>
</footer>
</body></html>"""
