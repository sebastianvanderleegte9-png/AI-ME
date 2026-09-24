"""The client-facing metrics dashboard (Component 16): /dashboard/{token}, same setup-session-token
auth as /account. Server-rendered SVG + HTML, no chart library, in the site's navy brand palette.

Color follows the dataviz skill: a single-series trend uses one hue (the brand accent, already
checked for contrast against --bg elsewhere on the site); the signup-source bars use a fixed,
validated 4-hue categorical order (see metrics/dashboard.py SOURCE_COLORS) that is never reordered
and never grown past four slots — a 5th source folds into "other" in --mute.

Layout is a fixed icon+label sidebar next to a wide content grid (not a single narrow column),
cards carry real elevation and a hover lift, the trend line draws itself in and numbers count up
on load — small, self-contained touches (no chart library, one inline <script>) so the page reads
as a finished product rather than a server-rendered form."""
from html import escape as e

from ..settings import settings
from .icons import icon as _icon
from .site import BRAND_CSS, font_link

CSS = """
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 var(--font)}
.shell{display:flex;min-height:100vh}

/* ---------- sidebar ---------- */
.sidebar{width:224px;flex:none;background:var(--bg2);border-right:1px solid var(--line);padding:22px 14px;
  position:sticky;top:0;height:100vh;display:flex;flex-direction:column;gap:2px}
.sidebar .logo{display:flex;align-items:center;gap:10px;font-weight:800;font-size:18px;letter-spacing:-.02em;
  padding:4px 10px 22px}
.sidebar .logo i{width:24px;height:24px;border-radius:7px;background:linear-gradient(160deg,var(--acc),var(--navy));
  display:inline-block;position:relative;flex:none}
.sidebar .logo i:after{content:"";position:absolute;left:7px;top:7px;width:10px;height:10px;border-radius:3px;background:var(--ink);opacity:.9}
.sidebar .logo .env{margin-left:auto;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;
  color:var(--mute);background:var(--card);border:1px solid var(--line);border-radius:5px;padding:2px 6px}
.navgroup{margin-bottom:14px}
.navlabel{font-size:10.5px;text-transform:uppercase;letter-spacing:.07em;color:var(--mute);opacity:.7;
  font-weight:700;padding:6px 12px 4px}
.navitem{display:flex;align-items:center;gap:11px;padding:9px 12px;border-radius:8px;color:var(--mute);
  font-size:13.5px;font-weight:600;text-decoration:none;border-left:2px solid transparent;transition:background .12s,color .12s}
.navitem svg{width:17px;height:17px;flex:none;opacity:.85}
.navitem:hover{background:rgba(255,255,255,.04);color:var(--ink)}
.navitem.on{color:var(--ink);background:rgba(59,130,246,.14);border-left-color:var(--acc)}
.sidebar .spacer{flex:1}
.sidebar .foot{padding:10px 12px;font-size:11.5px;color:var(--mute);opacity:.7}
@media(max-width:860px){.sidebar{display:none}}

/* ---------- main ---------- */
.main{flex:1;min-width:0}
.crumbbar{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:16px 32px;
  border-bottom:1px solid var(--line);background:rgba(12,21,39,.5)}
.crumb{font-size:13.5px;color:var(--mute);font-weight:600;display:flex;align-items:center;gap:6px}
.crumb b{color:var(--ink);font-weight:700}
.searchbox{display:flex;align-items:center;gap:8px;background:var(--card);border:1px solid var(--line);
  border-radius:9px;padding:8px 14px;color:var(--mute);font-size:13px;min-width:220px}
.searchbox svg{opacity:.7;flex:none}
.crumbbar .icons{display:flex;align-items:center;gap:10px}
.iconbtn{width:34px;height:34px;border-radius:9px;background:var(--card);border:1px solid var(--line);
  display:flex;align-items:center;justify-content:center;color:var(--mute)}
.content{padding:26px 36px 64px}
.topbar{display:flex;align-items:baseline;justify-content:space-between;gap:16px;margin-bottom:26px;flex-wrap:wrap}
h1{font-size:23px;margin:0 0 3px;letter-spacing:-.02em}
p.sub{color:var(--mute);margin:0;font-size:13.5px}
.range{display:flex;gap:2px;background:var(--card);border:1px solid var(--line);border-radius:9px;padding:3px}
.range span{font-size:12.5px;font-weight:600;padding:6px 12px;border-radius:6px;color:var(--mute)}
.range span.on{background:var(--acc);color:#fff}

h2{font-size:12.5px;text-transform:uppercase;letter-spacing:.06em;color:var(--mute);margin:0;font-weight:700}
.card-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px 22px;
  box-shadow:0 1px 2px rgba(0,0,0,.25),0 12px 28px -18px rgba(0,0,0,.65);
  transition:transform .15s ease,box-shadow .15s ease,border-color .15s ease}
.card:hover{border-color:#28395c;box-shadow:0 1px 2px rgba(0,0,0,.3),0 18px 34px -16px rgba(0,0,0,.75)}
.section{margin-bottom:20px}

.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}
@media(max-width:1080px){.kpis{grid-template-columns:1fr 1fr}}
.tile{background:var(--card);border:1px solid var(--line);border-radius:13px;padding:16px 18px;
  box-shadow:0 1px 2px rgba(0,0,0,.25),0 10px 22px -18px rgba(0,0,0,.6);
  transition:transform .15s ease,box-shadow .15s ease,border-color .15s ease}
.tile:hover{transform:translateY(-2px);border-color:#28395c;box-shadow:0 6px 20px -8px rgba(0,0,0,.55)}
.tile .top{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:12px}
.tile .chip{width:32px;height:32px;border-radius:9px;display:flex;align-items:center;justify-content:center;flex:none}
.tile .chip svg{width:16px;height:16px}
.tile .label{font-size:12.5px;color:var(--mute);font-weight:500}
.tile .value{font-size:25px;font-weight:700;letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.tile .delta{font-size:11.5px;margin-top:8px;display:inline-flex;align-items:center;gap:4px;padding:3px 8px;border-radius:999px;font-weight:600}
.delta.up{color:var(--ok);background:rgba(52,211,153,.13)}
.delta.down{color:#f87171;background:rgba(248,113,113,.13)}
.delta.flat{color:var(--mute);background:rgba(147,160,186,.1)}

.meter{height:9px;border-radius:5px;background:rgba(59,130,246,.16);margin-top:12px;overflow:hidden}
.meter b{display:block;height:100%;border-radius:5px;background:linear-gradient(90deg,var(--navy),var(--acc));
  width:0;transition:width 1s cubic-bezier(.22,1,.36,1)}

.legend{display:flex;gap:18px;flex-wrap:wrap;font-size:12.5px;color:var(--mute);margin-top:14px}
.legend i{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:6px;vertical-align:middle}
.bar-row{display:grid;grid-template-columns:100px 1fr 34px;gap:12px;align-items:center;margin:10px 0;font-size:13.5px}
.bar-row .track{height:20px;border-radius:5px;background:var(--bg2);position:relative;overflow:hidden}
.bar-row .fill{position:absolute;left:0;top:0;bottom:0;width:0;border-radius:5px 0 0 5px;transition:width .8s cubic-bezier(.22,1,.36,1)}
.bar-row .n{color:var(--mute);font-size:12.5px;text-align:right;font-variant-numeric:tabular-nums}
.empty{color:var(--mute);font-size:13.5px;padding:26px 0;text-align:center}
.stat-row{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:14px}
.grid2{display:grid;grid-template-columns:1.6fr 1fr;gap:16px;align-items:start}
@media(max-width:980px){.grid2{grid-template-columns:1fr}}

svg .trend-path{stroke-dasharray:2000;stroke-dashoffset:2000;animation:draw 1.1s cubic-bezier(.22,1,.36,1) forwards}
svg .trend-area{opacity:0;animation:fadein .8s ease .5s forwards}
svg .trend-dot{opacity:0;animation:fadein .3s ease forwards}
@keyframes draw{to{stroke-dashoffset:0}}
@keyframes fadein{to{opacity:1}}
"""

NAV = [("General", [("grid", "Overview", "#overview"), ("trend", "Metrics", "#trend")]),
       ("Growth", [("users", "Signups", "#sources"), ("mail", "Outreach", "#outreach")]),
       ("You", [("user", "Account", None)])]


def _sidebar(token: str) -> str:
    groups = ""
    first = True
    for group, items in NAV:
        rows = "".join(
            f'<a class="navitem{" on" if first and i == 0 else ""}" href="{"/account/" + e(token) if href is None else href}">'
            f'{_icon(ic)}<span>{label}</span></a>'
            for i, (ic, label, href) in enumerate(items))
        groups += f'<div class="navgroup"><div class="navlabel">{e(group)}</div>{rows}</div>'
        first = False
    return f"""<div class="sidebar"><div class="logo"><i></i>{e(settings.site_name)}<span class="env">production</span></div>{groups}<div class="spacer"></div>
<div class="foot">Live data &middot; updates every Friday</div></div>"""


def _shell(body: str, token: str) -> str:
    n = e(settings.site_name)
    crumb = (f'<div class="crumb">{_icon("grid", 14)}<span>{n}</span><span>/</span><b>Overview</b></div>'
             f'<div class="searchbox">{_icon("search", 15)}<span>Search or type a command</span></div>'
             f'<div class="icons"><div class="iconbtn">{_icon("bell", 16)}</div>'
             f'<div class="iconbtn">{_icon("user", 16)}</div></div>')
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dashboard · {n}</title>{font_link()}<style>{BRAND_CSS}{CSS}</style></head><body>
<div class="shell">{_sidebar(token)}<div class="main"><div class="crumbbar">{crumb}</div><div class="content">{body}</div></div></div>
<script>
// small, dependency-free count-up for the KPI/score numbers, and animated meter/bar fills — the
// chart's own draw-in and fade-in are pure CSS (see .trend-path / .trend-area / .trend-dot above).
document.querySelectorAll('[data-count]').forEach(function(el){{
  var target = parseFloat(el.getAttribute('data-count')), suffix = el.getAttribute('data-suffix') || '';
  var start = performance.now(), dur = 700;
  function tick(now){{
    var p = Math.min(1, (now - start) / dur), eased = 1 - Math.pow(1 - p, 3);
    var v = target * eased;
    el.textContent = (Number.isInteger(target) ? Math.round(v).toLocaleString() : v.toFixed(1)) + suffix;
    if (p < 1) requestAnimationFrame(tick);
  }}
  requestAnimationFrame(tick);
}});
requestAnimationFrame(function(){{
  document.querySelectorAll('[data-fill]').forEach(function(el){{ el.style.width = el.getAttribute('data-fill'); }});
}});
</script>
</body></html>"""


def _pct(a, b) -> tuple[str, str]:
    if not b:
        return "—", "flat"
    p = (a - b) / b * 100
    d = "up" if p > 0 else "down" if p < 0 else "flat"
    return f"{'+' if p >= 0 else ''}{p:.0f}% vs last week", d


_DELTA_ARROW = {"up": "&uarr;", "down": "&darr;", "flat": "&middot;"}


def _tile(icon: str, chip_color: str, label: str, value: float | int | str, count: bool = False,
          suffix: str = "", delta_text: str | None = None, direction: str = "flat") -> str:
    v_attr = f' data-count="{value}" data-suffix="{e(suffix)}"' if count else ""
    v_html = "0" + suffix if count else e(str(value))
    d = (f'<div class="delta {direction}">{_DELTA_ARROW[direction]} {e(delta_text)}</div>' if delta_text else "")
    return (f'<div class="tile"><div class="top"><div class="label">{e(label)}</div>'
            f'<div class="chip" style="background:{chip_color}1f;color:{chip_color}">{_icon(icon, 16)}</div></div>'
            f'<div class="value"{v_attr}>{v_html}</div>{d}</div>')


def _trend_svg(trend: list[dict]) -> str:
    if len(trend) < 2:
        return '<div class="empty">Not enough weeks yet — this fills in after your first two Friday reports.</div>'
    W, H, PAD_L, PAD_B, PAD_T = 800, 220, 46, 26, 18
    vals = [t["impressions_icp"] for t in trend]
    vmax = max(vals) or 1
    step = 10 ** (len(str(int(vmax))) - 1) or 1
    ceil = ((int(vmax) // step) + 1) * step
    n = len(trend)
    plot_w = W - PAD_L - 12
    plot_h = H - PAD_T - PAD_B

    def xy(i, v):
        x = PAD_L + (plot_w * i / (n - 1) if n > 1 else 0)
        y = PAD_T + plot_h - (plot_h * v / ceil if ceil else 0)
        return x, y

    pts = [xy(i, t["impressions_icp"]) for i, t in enumerate(trend)]
    path = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(pts))
    area = path + f" L{pts[-1][0]:.1f},{PAD_T + plot_h:.1f} L{pts[0][0]:.1f},{PAD_T + plot_h:.1f} Z"
    grid = "".join(
        f'<line x1="{PAD_L}" y1="{PAD_T + plot_h * (1 - f):.1f}" x2="{W - 12}" y2="{PAD_T + plot_h * (1 - f):.1f}" stroke="var(--line)" stroke-width="1"/>'
        f'<text x="4" y="{PAD_T + plot_h * (1 - f) + 4:.1f}" font-size="11" fill="var(--mute)">{int(ceil * f):,}</text>'
        for f in (0, 0.5, 1))
    dots = "".join(
        f'<circle class="trend-dot" style="animation-delay:{0.5 + i * 0.05:.2f}s" cx="{x:.1f}" cy="{y:.1f}" r="4.5" '
        f'fill="var(--acc)" stroke="var(--bg)" stroke-width="2">'
        f'<title>week of {e(trend[i]["week_start"])}: {trend[i]["impressions_icp"]:,} impressions in ICP</title></circle>'
        for i, (x, y) in enumerate(pts))
    last_x, last_y = pts[-1]
    end_label = f'<text x="{last_x - 4:.1f}" y="{last_y - 14:.1f}" font-size="13" font-weight="700" fill="var(--ink)" text-anchor="end">{trend[-1]["impressions_icp"]:,}</text>'
    return (f'<svg viewBox="0 0 {W} {H}" width="100%" height="{H}" role="img" '
            f'aria-label="Impressions inside your ICP, last {n} weeks, ending at {trend[-1]["impressions_icp"]:,}">'
            f'{grid}<path class="trend-area" d="{area}" fill="var(--acc)" fill-opacity="0.12"/>'
            f'<path class="trend-path" d="{path}" fill="none" stroke="var(--acc)" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"/>'
            f'{dots}{end_label}</svg>')


def _sources_bars(sources: list[dict]) -> str:
    if not sources:
        return '<div class="empty">No signups classified by source yet this week.</div>'
    total = sum(s["count"] for s in sources) or 1
    rows = "".join(
        f'<div class="bar-row"><span>{e(s["name"].title())}</span>'
        f'<span class="track"><span class="fill" data-fill="{max(4, s["count"] / total * 100):.0f}%" '
        f'style="background:{s["color"]}"></span></span><span class="n">{s["count"]}</span></div>' for s in sources)
    legend = "".join(f'<span><i style="background:{s["color"]}"></i>{e(s["name"].title())}</span>' for s in sources)
    return f'{rows}<div class="legend">{legend}</div>'


def dashboard(s, company, data: dict) -> str:
    imp_delta, imp_dir = _pct(data["this"]["impressions_icp"], data["prev"]["impressions_icp"])
    signup_delta, signup_dir = _pct(data["this"]["signups"], data["prev"]["signups"])
    ar = data["approval_rate"]
    gs = data["growth_score"]

    kpis = "".join([
        _tile("trend", "#4f8ef7", "Impressions in ICP this week", data["this"]["impressions_icp"], count=True,
              delta_text=imp_delta, direction=imp_dir),
        _tile("users", "#1fae76", "Signups this week", data["this"]["signups"], count=True,
              delta_text=signup_delta, direction=signup_dir),
        (_tile("check", "#c2870f", "Approval rate", round(ar * 100), count=True, suffix="%",
               delta_text="of drafts approved or edited")
         if ar is not None else
         _tile("check", "#c2870f", "Approval rate", "—", delta_text="no decisions yet this week")),
        _tile("file", "#a855f7", "Pages indexed", int(data["this"]["pages_indexed"]), count=True,
              delta_text=f'{int(data["delta"]["pages_indexed"]):+d} vs last week',
              direction="up" if data["delta"]["pages_indexed"] > 0 else "flat"),
    ])

    score_html = ""
    if gs is not None:
        score_html = f"""<div class="card">
<div class="card-head"><h2>Growth score</h2>{_icon("gauge", 18)}</div>
<div class="value" style="font-size:38px" data-count="{gs}">0<span style="font-size:15px;color:var(--mute);font-weight:400"> / 10</span></div>
<div class="meter"><b data-fill="{min(100, gs / 10 * 100):.0f}%"></b></div></div>"""

    body = f"""<div id="overview" class="topbar"><div><h1>{e(company.name)}</h1>
<p class="sub">Week of {e(data["week_start"])} &ndash; {e(data["week_end"])}</p></div>
<div class="range"><span>7d</span><span class="on">This week</span><span>90d</span></div></div>

<div class="section kpis">{kpis}</div>

<div class="section grid2">
<div id="trend" class="card"><div class="card-head"><h2>Impressions inside your ICP</h2>{_icon("trend", 16)}</div>{_trend_svg(data["trend"])}</div>
{score_html}
</div>

<div class="section grid2">
<div id="sources" class="card"><div class="card-head"><h2>Where signups came from this week</h2>{_icon("users", 16)}</div>{_sources_bars(data["sources"])}</div>
<div id="outreach" class="card"><div class="card-head"><h2>Outreach &amp; meetings &middot; last 30 days</h2>{_icon("mail", 16)}</div>
<div class="stat-row">{_tile("mail", "#4f8ef7", "Emails sent", data["emails_sent_30d"], count=True)}{_tile("cal", "#1fae76", "Meetings confirmed", data["meetings_confirmed_30d"], count=True)}</div></div>
</div>"""
    return _shell(body, s.token)
