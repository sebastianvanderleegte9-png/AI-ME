"""The public marketing site, served at / (Component 14b). One page, no build step.
Brand tokens (name, font, palette) come from settings so they change without a deploy of code.
The font is fetched from api.fonts.coollabs.io, a privacy-friendly Google Fonts mirror."""
from html import escape as e
from urllib.parse import quote

from ..interfaces.billing_oauth import PLANS
from ..settings import settings

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
.wrap{max-width:1140px;margin:0 auto;padding:0 22px}
nav{position:sticky;top:0;z-index:5;backdrop-filter:blur(14px);background:rgba(7,13,26,.72);border-bottom:1px solid var(--line)}
nav .wrap{display:flex;align-items:center;justify-content:space-between;height:66px}
.logo{display:flex;align-items:center;gap:10px;font-weight:800;font-size:22px;letter-spacing:-.02em}
.logo i{width:28px;height:28px;border-radius:8px;background:linear-gradient(160deg,var(--acc),var(--navy));display:inline-block;position:relative}
.logo i:after{content:"";position:absolute;left:8px;top:8px;width:12px;height:12px;border-radius:3px;background:var(--ink);opacity:.9}
nav .links{display:flex;gap:26px;color:var(--mute);font-size:15px;font-weight:500}nav .links a:hover{color:var(--ink)}
@media(max-width:820px){nav .links{display:none}}
.btn{display:inline-block;background:var(--acc);color:#fff;padding:12px 20px;border-radius:10px;font-weight:600;border:0;font:inherit;font-weight:600;cursor:pointer}
.btn:hover{background:#4f8ff8}.btn.ghost{background:transparent;border:1px solid var(--line);color:var(--ink)}.btn.big{padding:16px 26px;font-size:17px}
.hero{padding:96px 0 80px;position:relative;overflow:hidden}
.hero:before{content:"";position:absolute;right:-20%;top:-10%;width:60%;height:120%;background:radial-gradient(closest-side,rgba(59,130,246,.22),transparent);pointer-events:none}
.hero .wrap{position:relative;display:grid;grid-template-columns:1.15fr .85fr;gap:48px;align-items:center}
@media(max-width:900px){.hero .wrap{grid-template-columns:1fr}.hero{padding:64px 0}}
.eyebrow{display:inline-flex;align-items:center;gap:8px;font-size:13px;font-weight:600;color:var(--acc2);margin-bottom:22px}
.eyebrow:before{content:"";width:22px;height:2px;background:var(--acc)}
h1{font-size:clamp(42px,6.2vw,72px);line-height:1;letter-spacing:-.035em;margin:0 0 20px;font-weight:800}
h1 em{font-style:normal;color:var(--acc2)}
.sub{font-size:clamp(17px,2vw,20px);color:var(--mute);max-width:560px;margin:0 0 30px}
.cta{display:flex;gap:12px;flex-wrap:wrap}.fine{color:var(--mute);font-size:13px;margin-top:16px}
.proof{display:flex;gap:28px;margin-top:38px;flex-wrap:wrap}.proof div b{display:block;font-size:26px;letter-spacing:-.02em}.proof div span{color:var(--mute);font-size:13px}
.phone{width:min(360px,100%);margin:0 auto;background:var(--bg2);border:1px solid var(--line);border-radius:30px;padding:22px 16px;box-shadow:0 40px 90px rgba(0,0,0,.55),inset 0 1px 0 rgba(255,255,255,.04)}
.phone .t{font-size:12px;color:var(--mute);text-align:center;margin-bottom:12px}
.msg{max-width:88%;padding:10px 13px;border-radius:16px;margin:8px 0;font-size:14px;line-height:1.4;white-space:pre-wrap}
.msg.in{background:#182742;border-bottom-left-radius:4px}.msg.out{background:var(--acc);margin-left:auto;border-bottom-right-radius:4px}
section{padding:96px 0;border-top:1px solid var(--line)}
h2{font-size:clamp(28px,4vw,44px);letter-spacing:-.03em;margin:0 0 10px;line-height:1.08;font-weight:800}
.lead{color:var(--mute);font-size:18px;max-width:640px;margin:0 0 40px}
.grid{display:grid;gap:16px}.g3{grid-template-columns:repeat(3,1fr)}.g2{grid-template-columns:repeat(2,1fr)}
@media(max-width:820px){.g3,.g2{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:26px}
.card h3{margin:0 0 6px;font-size:18px;font-weight:700}.card p{margin:0;color:var(--mute);font-size:15px}
.num{font-size:13px;color:var(--acc2);font-weight:700;margin-bottom:12px;letter-spacing:.02em}
.formula .card{display:flex;gap:16px;align-items:flex-start}.formula .k{flex:0 0 46px;height:46px;border-radius:12px;background:rgba(59,130,246,.14);color:var(--acc2);display:grid;place-items:center;font-weight:800}
.rules{background:var(--bg2)}.rule{display:flex;gap:14px;padding:18px 0;border-bottom:1px solid var(--line)}.rule b{display:block}.rule span{color:var(--mute);font-size:15px}
.rule i{flex:0 0 22px;height:22px;border-radius:50%;background:rgba(52,211,153,.15);color:var(--ok);display:grid;place-items:center;font-style:normal;font-size:13px;margin-top:3px}
.plans{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}@media(max-width:820px){.plans{grid-template-columns:1fr}}
.plan{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:28px}.plan.pick{border-color:var(--acc);box-shadow:0 0 0 1px var(--acc),0 24px 60px rgba(59,130,246,.15)}
.plan .p{font-size:40px;font-weight:800;letter-spacing:-.03em}.plan .p small{font-size:15px;color:var(--mute);font-weight:400}
.plan ul{padding:0;list-style:none;margin:18px 0 22px}.plan li{padding:6px 0;color:var(--mute);font-size:15px}.plan li:before{content:"✓ ";color:var(--ok)}
.faq details{border-bottom:1px solid var(--line);padding:16px 0}.faq summary{cursor:pointer;font-weight:600;font-size:17px}.faq p{color:var(--mute);margin:10px 0 0}
.final{text-align:center;padding:110px 0;background:linear-gradient(180deg,var(--bg),var(--bg2))}.final .lead{margin:10px auto 30px}
footer{border-top:1px solid var(--line);padding:30px 0;color:var(--mute);font-size:13px;display:flex;justify-content:space-between;flex-wrap:wrap;gap:10px}
"""

_FEATURES = {
    "founder": ["One founder, LinkedIn + X", "Weekly memo → drafts in your voice", "Morning brief, approve by text", "Attention map + daily replies", "Friday number"],
    "team": ["Up to three founders", "Everything in Founder", "Launch kits and pages", "Outreach and joint posts", "Site fixes and small tools"],
    "growth": ["Everything in Team", "Human review of every weekly plan", "Quarterly growth review", "Priority support", "Custom integrations"],
}


def page() -> str:
    n = e(settings.site_name)
    plans = "".join(f"""<div class="plan {'pick' if k == 'team' else ''}"><div class="num">{v['name']}</div>
<div class="p">${v['monthly_usd']:,}<small> /month</small></div>
<ul>{''.join(f'<li>{x}</li>' for x in _FEATURES[k])}</ul>
<a class="btn" href="/start">Start with the free diagnostic</a></div>""" for k, v in PLANS.items())
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{n} — your marketing engineer, over text</title>
<meta name="description" content="{n} is a marketing engineer that runs on one voice memo a week. Drafts in your voice, you approve by text, it posts, replies, does outreach and reports one number every Friday.">
{font_link()}<style>{BRAND_CSS}{CSS}</style></head><body>
<nav><div class="wrap"><a class="logo" href="/"><i></i>{n}</a>
<div class="links"><a href="#how">How it works</a><a href="#formula">What it does</a><a href="#rules">Rules</a><a href="#pricing">Pricing</a><a href="#faq">FAQ</a></div>
<div><a class="btn ghost" href="/start" style="margin-right:8px">Sign in</a><a class="btn" href="/start">Free scorecard</a></div></div></nav>

<header class="hero"><div class="wrap">
<div>
<div class="eyebrow">The full growth hire, not a content tool</div>
<h1>{n} is your <em>marketing engineer.</em></h1>
<p class="sub">Growth on LinkedIn and X, replies where your buyers already are, outbound to real prospects, launches, pages and site fixes — one system, run from a weekly voice memo and a text thread. Not a scheduler. The whole job.</p>
<div class="cta"><a class="btn big" href="/start">Get your free growth scorecard →</a><a class="btn ghost big" href="#how">How it works</a></div>
<div class="fine">Ten-minute setup · no card until you've seen the scorecard · nothing posts without your yes</div>
<div class="proof"><div><b>10 min</b><span>a week from you</span></div><div><b>9</b><span>growth channels, scored</span></div><div><b>0</b><span>posts, emails or meetings booked without your yes</span></div></div>
</div>
<div class="phone"><div class="t">Today 8:00 AM</div>
<div class="msg in">Morning, Noah. 4 things:
1. Post (LinkedIn): "1,300 users onboarded in six weeks. Here is what broke."
2. Reply to Sarah K. (COO, 40k followers) on AI ops
3. Post (X): the four-hours-per-week line
4. Outreach: Dan at Northwind — warm intro from Tuesday's thread
Reply yes 1 3, no 2, or type an edit.</div>
<div class="msg out">yes 1 3 4</div>
<div class="msg in">Done. 1 goes out at 11:10 (your audience's peak). 3 at 2:40. Outreach sent to Dan. #2 kept for tomorrow.</div>
<div class="msg in">Dan replied: "interested, can we talk this week?" Proposing 3 times from your calendar now — I'll text you when he picks one.</div>
<div class="msg in">Dan picked Thu 2:00pm for "Quick chat — Aime". yes to confirm / no for other times.</div>
<div class="msg out">yes</div>
<div class="msg in">Confirmed. On your calendar and his.</div></div>
</div></header>

<section id="how"><div class="wrap"><h2>How it works</h2><p class="lead">You already know what happened this week. Saying it out loud is the whole job.</p>
<div class="grid g3">
<div class="card"><div class="num">01 · ONCE</div><h3>Ten-minute setup</h3><p>Company, three best customers, connect LinkedIn and X, your phone. You get a free growth scorecard: nine channels scored, the biggest gap named, your first two weeks planned.</p></div>
<div class="card"><div class="num">02 · WEEKLY</div><h3>One voice memo</h3><p>Ten minutes, whenever. What shipped, what a customer said, what you got wrong, what you believe. {n} pulls the claims and drafts the week in your voice, not "AI voice".</p></div>
<div class="card"><div class="num">03 · DAILY</div><h3>Approve by text, day mapped for you</h3><p>Every morning: your calendar for the day, then a numbered brief of posts, replies and outreach. yes 1 3, no 2, or edit. Meeting requests text you separately the moment a prospect books — yes puts it on your calendar.</p></div>
</div></div></section>

<section id="formula"><div class="wrap"><h2>What a marketing engineer does. All of it.</h2><p class="lead">Not a content calendar with a chatbot on top. Every line below is a system running in {n}, not a slide.</p>
<div class="grid g2 formula">
<div class="card"><div class="k">01</div><div><h3>Judgment on what to build first</h3><p>Scores content, SEO, social, email, launches, community, partners, product-led and ads for <i>your</i> company, sequences the fixes, and re-plans every Monday from last week's numbers.</p></div></div>
<div class="card"><div class="k">02</div><div><h3>Founder voice, not brand voice</h3><p>Learns how you actually write from your own posts. Every draft is checked against it; anything that reads like a bot is rejected before you ever see it.</p></div></div>
<div class="card"><div class="k">03</div><div><h3>Goes where the attention already is</h3><p>Maps the accounts your buyers actually read and reply to, then puts you in those threads daily. Reach follows replies.</p></div></div>
<div class="card"><div class="k">04</div><div><h3>Measures what matters</h3><p>Impressions inside your ICP, not vanity totals. Signups tied to the post that caused them. One number, every Friday.</p></div></div>
<div class="card"><div class="k">05</div><div><h3>Ships pages and launches</h3><p>Comparison, use-case and integration pages built from your real claims. Launch kits with the posts, the DMs and the day-by-day plan.</p></div></div>
<div class="card"><div class="k">06</div><div><h3>Outreach, meetings, client acquisition</h3><p>Personalized emails from your own Outlook to real prospects. The moment one replies interested, it proposes times from your actual calendar, the prospect books, and it only goes on the calendar once you text yes.</p></div></div>
<div class="card"><div class="k">07</div><div><h3>Fixes your site</h3><p>Audits the signup field, the proof, the speed, the message; proposes the change; ships it when you tap.</p></div></div>
<div class="card"><div class="k">08</div><div><h3>Builds small tools</h3><p>Calculators, checkers, graders your buyers will use and share. Proposed by text, built when you say build 2.</p></div></div>
</div></div></section>

<section id="rules" class="rules"><div class="wrap"><h2>The rules {n} cannot break</h2><p class="lead">Written into the database, not the terms of service.</p>
<div class="rule"><i>✓</i><div><b>Nothing posts without your yes.</b><span>A bare "yes" never approves a batch by guess. Every executed post records exactly which reply approved it.</span></div></div>
<div class="rule"><i>✓</i><div><b>Your voice or nothing.</b><span>Drafts that fail the voice check are never shown to you, let alone posted.</span></div></div>
<div class="rule"><i>✓</i><div><b>Founder accounts, founder attention.</b><span>No paid ads, no press releases, no company-page filler. Only the things that work for early-stage companies.</span></div></div>
<div class="rule"><i>✓</i><div><b>Your data stays yours.</b><span>Cancel and posting stops; your scorecards, voice profile and history stay. Tokens are encrypted at rest and revocable in one tap.</span></div></div>
<div class="rule"><i>✓</i><div><b>It learns only from what it can prove.</b><span>The planner changes its defaults only after a controlled test says the new plan grew ICP attention more than the old one.</span></div></div>
</div></section>

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

<section class="final"><div class="wrap"><h2>See your growth score in ten minutes.</h2><p class="lead">Free, before any card. Then decide.</p><a class="btn big" href="/start">Get your free scorecard →</a></div></section>
<footer class="wrap"><span>© {n}</span><span><a href="/start">Sign in</a> · <a href="#pricing">Pricing</a> · <a href="mailto:hello@example.com">Contact</a></span></footer>
</body></html>"""
