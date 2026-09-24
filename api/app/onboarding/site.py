"""The public marketing site, served at / (Component 14b). One page, no build step, dark.
Every button leads to /start. The copy is the tweet, rewritten for the buyer."""
from ..interfaces.billing_oauth import PLANS

CSS = """
:root{--bg:#07070c;--bg2:#0e0e1a;--ink:#f3f2ff;--mute:#9a99b3;--line:#232338;--acc:#6c63ff;--acc2:#a59bff;--ok:#34d399;--card:#11111f}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 Inter,-apple-system,Segoe UI,sans-serif;-webkit-font-smoothing:antialiased}
a{color:inherit;text-decoration:none}
.wrap{max-width:1120px;margin:0 auto;padding:0 20px}
nav{position:sticky;top:0;z-index:5;backdrop-filter:blur(14px);background:rgba(7,7,12,.7);border-bottom:1px solid var(--line)}
nav .wrap{display:flex;align-items:center;justify-content:space-between;height:64px}
.logo{display:flex;align-items:center;gap:10px;font-weight:700;font-size:18px;letter-spacing:-.01em}
.logo i{width:26px;height:26px;border-radius:7px;background:linear-gradient(135deg,var(--acc),#3b3399);display:inline-block}
nav .links{display:flex;gap:26px;color:var(--mute);font-size:15px}nav .links a:hover{color:var(--ink)}
@media(max-width:760px){nav .links{display:none}}
.btn{display:inline-block;background:var(--acc);color:#fff;padding:12px 20px;border-radius:9px;font-weight:600;border:0;font:inherit;cursor:pointer}
.btn:hover{background:#7d75ff}.btn.ghost{background:transparent;border:1px solid var(--line);color:var(--ink)}.btn.big{padding:16px 28px;font-size:17px}
.hero{padding:110px 0 70px;text-align:center;position:relative;overflow:hidden}
.hero:before{content:"";position:absolute;inset:auto 0 0 0;height:520px;background:radial-gradient(60% 70% at 50% 100%,rgba(108,99,255,.35),transparent 70%);pointer-events:none}
.hero .wrap{position:relative}
.eyebrow{display:inline-block;font-size:13px;color:var(--acc2);border:1px solid rgba(108,99,255,.4);border-radius:999px;padding:5px 12px;margin-bottom:22px}
h1{font-size:clamp(40px,7vw,76px);line-height:1.02;letter-spacing:-.035em;margin:0 0 18px;font-weight:700}
h1 em{font-style:normal;color:var(--acc2)}
.sub{font-size:clamp(17px,2.2vw,22px);color:var(--mute);max-width:680px;margin:0 auto 34px}
.hero .cta{display:flex;gap:12px;justify-content:center;flex-wrap:wrap}.hero .fine{color:var(--mute);font-size:13px;margin-top:16px}
.phone{margin:70px auto 0;width:min(380px,92%);background:var(--bg2);border:1px solid var(--line);border-radius:28px;padding:22px 16px;text-align:left;box-shadow:0 30px 80px rgba(0,0,0,.5)}
.phone .t{font-size:12px;color:var(--mute);text-align:center;margin-bottom:12px}
.msg{max-width:86%;padding:10px 13px;border-radius:16px;margin:8px 0;font-size:14px;line-height:1.4;white-space:pre-wrap}
.msg.in{background:#1e1e30;border-bottom-left-radius:4px}.msg.out{background:var(--acc);margin-left:auto;border-bottom-right-radius:4px}
section{padding:90px 0;border-top:1px solid var(--line)}
h2{font-size:clamp(28px,4vw,42px);letter-spacing:-.03em;margin:0 0 10px;line-height:1.1}
.lead{color:var(--mute);font-size:18px;max-width:640px;margin:0 0 40px}
.grid{display:grid;gap:16px}.g3{grid-template-columns:repeat(3,1fr)}.g2{grid-template-columns:repeat(2,1fr)}
@media(max-width:820px){.g3,.g2{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:24px}
.card h3{margin:0 0 6px;font-size:18px}.card p{margin:0;color:var(--mute);font-size:15px}
.num{font-size:13px;color:var(--acc2);font-weight:600;margin-bottom:12px}
.formula .card{display:flex;gap:16px;align-items:flex-start}.formula .k{flex:0 0 46px;height:46px;border-radius:10px;background:rgba(108,99,255,.15);color:var(--acc2);display:grid;place-items:center;font-weight:700}
.rules{background:var(--bg2)}.rule{display:flex;gap:14px;padding:18px 0;border-bottom:1px solid var(--line)}.rule b{display:block}.rule span{color:var(--mute);font-size:15px}
.rule i{flex:0 0 22px;height:22px;border-radius:50%;background:rgba(52,211,153,.15);color:var(--ok);display:grid;place-items:center;font-style:normal;font-size:13px;margin-top:3px}
.plans{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}@media(max-width:820px){.plans{grid-template-columns:1fr}}
.plan{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:28px}.plan.pick{border-color:var(--acc);box-shadow:0 0 0 1px var(--acc),0 20px 60px rgba(108,99,255,.15)}
.plan .p{font-size:40px;font-weight:700;letter-spacing:-.03em}.plan .p small{font-size:15px;color:var(--mute);font-weight:400}
.plan ul{padding:0;list-style:none;margin:18px 0 22px}.plan li{padding:6px 0;color:var(--mute);font-size:15px}.plan li:before{content:"✓ ";color:var(--ok)}
.faq details{border-bottom:1px solid var(--line);padding:16px 0}.faq summary{cursor:pointer;font-weight:600;font-size:17px}.faq p{color:var(--mute);margin:10px 0 0}
.final{text-align:center;padding:110px 0}
footer{border-top:1px solid var(--line);padding:30px 0;color:var(--mute);font-size:13px;display:flex;justify-content:space-between;flex-wrap:wrap;gap:10px}
"""


def page() -> str:
    plans = "".join(f"""<div class="plan {'pick' if k == 'team' else ''}"><div class="num">{v['name']}</div>
<div class="p">${v['monthly_usd']:,}<small> /month</small></div>
<ul>{''.join(f'<li>{x}</li>' for x in _FEATURES[k])}</ul>
<a class="btn" href="/start">Start with the free diagnostic</a></div>""" for k, v in PLANS.items())
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Marketing Engineer — the growth hire every startup is trying to make, over text</title>
<meta name="description" content="A marketing engineer that runs on one voice memo a week. Drafts in your voice, you approve by text, it posts, replies, does outreach and reports one number every Friday.">
<style>{CSS}</style></head><body>
<nav><div class="wrap"><a class="logo" href="/"><i></i>Marketing Engineer</a>
<div class="links"><a href="#how">How it works</a><a href="#formula">What it does</a><a href="#rules">Rules</a><a href="#pricing">Pricing</a><a href="#faq">FAQ</a></div>
<div><a class="btn ghost" href="/start" style="margin-right:8px">Sign in</a><a class="btn" href="/start">Get your free scorecard</a></div></div></nav>

<header class="hero"><div class="wrap">
<div class="eyebrow">The role every startup is trying to hire, as software</div>
<h1>Your marketing engineer,<br><em>over text.</em></h1>
<p class="sub">One voice memo a week from you. It turns that into posts in your voice, replies where your buyers actually are, outreach, launches and pages. You approve by text. Every Friday: one number.</p>
<div class="cta"><a class="btn big" href="/start">Get your free growth scorecard →</a><a class="btn ghost big" href="#how">See how it works</a></div>
<div class="fine">Ten minutes of setup. No card until you have seen the scorecard. Nothing is ever posted without your yes.</div>
<div class="phone"><div class="t">Today 8:00 AM</div>
<div class="msg in">Morning, Juraj. 4 things:
1. Post (LinkedIn): "1,300 agents onboarded in six weeks. Here is what broke."
2. Reply to Sarah K. (COO, 40k followers) on brokerage AI
3. Post (X): the four-hours-per-packet line
4. DM: Dan at Compass, warm intro from Tuesday's thread
Reply yes 1 3, no 2, or type an edit.</div>
<div class="msg out">yes 1 3 4</div>
<div class="msg in">Done. 1 goes out at 11:10 (your audience's peak). 3 at 2:40. DM sent. #2 kept for tomorrow.</div>
<div class="msg out">2 → make it shorter, lead with the number</div>
<div class="msg in">Rewritten. "40% of inbound calls never got picked up. Here is the fix that took nine weeks, not two." Post it?</div>
<div class="msg out">yes</div></div>
</div></header>

<section id="how"><div class="wrap"><h2>How it works</h2><p class="lead">You already know what happened this week. Saying it out loud is the whole job.</p>
<div class="grid g3">
<div class="card"><div class="num">01 · Once</div><h3>Ten-minute setup</h3><p>Company, three best customers, connect LinkedIn and X, your phone. You get a free growth scorecard: nine channels scored, the biggest gap named, your first two weeks planned.</p></div>
<div class="card"><div class="num">02 · Weekly</div><h3>One voice memo</h3><p>Ten minutes, whenever. What shipped, what a customer said, what you got wrong, what you believe. It pulls the claims and drafts the week in your voice, not "AI voice".</p></div>
<div class="card"><div class="num">03 · Daily</div><h3>Approve by text</h3><p>A numbered brief every morning. yes 1 3, no 2, or type an edit. It schedules, posts, replies, follows up. Friday it texts you the one number that matters and what changed it.</p></div>
</div></div></section>

<section id="formula"><div class="wrap"><h2>What a marketing engineer does. All of it.</h2><p class="lead">This is the job description that is going around. Each line is a working part of the product, not a slide.</p>
<div class="grid g2 formula">
<div class="card"><div class="k">01</div><div><h3>Judgment on what to build first</h3><p>Scores content, SEO, social, email, launches, community, partners, product-led and ads for <i>your</i> company, sequences the fixes, and re-plans every Monday from last week's numbers.</p></div></div>
<div class="card"><div class="k">02</div><div><h3>Founder voice, not brand voice</h3><p>Learns how you actually write from your own posts. Every draft is checked against it; anything that reads like a bot is rejected before you ever see it.</p></div></div>
<div class="card"><div class="k">03</div><div><h3>Goes where the attention already is</h3><p>Maps the accounts your buyers actually read and reply to, then puts you in those threads daily. Reach follows replies.</p></div></div>
<div class="card"><div class="k">04</div><div><h3>Measures what matters</h3><p>Impressions inside your ICP, not vanity totals. Signups tied to the post that caused them. One number, every Friday.</p></div></div>
<div class="card"><div class="k">05</div><div><h3>Ships pages and launches</h3><p>Comparison, use-case and integration pages built from your real claims. Launch kits with the posts, the DMs and the day-by-day plan.</p></div></div>
<div class="card"><div class="k">06</div><div><h3>Relationships and outreach</h3><p>Warm, sequenced, conditional on silence. Joint posts with founders who share your buyer. Every DM waits for your yes.</p></div></div>
<div class="card"><div class="k">07</div><div><h3>Fixes your site</h3><p>Audits the signup field, the proof, the speed, the message; proposes the change; ships it when you tap.</p></div></div>
<div class="card"><div class="k">08</div><div><h3>Builds small tools</h3><p>Calculators, checkers, graders your buyers will use and share. Proposed by text, built when you say build 2.</p></div></div>
</div></div></section>

<section id="rules" class="rules"><div class="wrap"><h2>The rules it cannot break</h2><p class="lead">Written into the database, not the terms of service.</p>
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
<details><summary>What does the weekly memo need to contain?</summary><p>Whatever happened. What you shipped, a customer's words, a number you measured, a mistake, a belief. Ten minutes is plenty; it extracts the claims and builds the drafts from those.</p></details>
<details><summary>Are LinkedIn and X posts different?</summary><p>Yes. Same claim, different shape: a story on LinkedIn, a single sharp line on X. Both in your voice.</p></details>
<details><summary>Do I have to be on the schedule?</summary><p>No. Pick "we manage the schedule" and it posts at your audience's active hours once you've approved the words. Or approve the time too.</p></details>
<details><summary>What if I don't answer for a week?</summary><p>Nothing goes out. It waits. The brief keeps coming until you text pause.</p></details>
</div></section>

<section class="final"><div class="wrap"><h2>See your growth score in ten minutes.</h2><p class="lead" style="margin:10px auto 30px">Free, before any card. Then decide.</p><a class="btn big" href="/start">Get your free scorecard →</a></div></section>
<footer class="wrap"><span>© Marketing Engineer</span><span><a href="/start">Sign in</a> · <a href="#pricing">Pricing</a> · <a href="mailto:hello@example.com">Contact</a></span></footer>
</body></html>"""


_FEATURES = {
    "founder": ["One founder, LinkedIn + X", "Weekly memo → drafts in your voice", "Morning brief, approve by text", "Attention map + daily replies", "Friday number"],
    "team": ["Up to three founders", "Everything in Founder", "Launch kits and pages", "Outreach and joint posts", "Site fixes and small tools"],
    "growth": ["Everything in Team", "Human review of every weekly plan", "Quarterly growth review", "Priority support", "Custom integrations"],
}
