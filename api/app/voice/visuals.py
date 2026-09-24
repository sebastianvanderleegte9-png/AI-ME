"""Visual engine: templated, code-rendered cards in the founder's own brand colors.
Rule: a visual exists only when it carries information the text cannot (a number,
a before/after, steps, a quote). No stock illustrations, no gradients-by-default.

Templates render to HTML; a worker turns them into PNG with headless Chromium.
The founder's brand (colors, font, logo) comes from voice_profile.rules.visual,
captured at intake from their site; defaults are deliberately plain."""
from html import escape
import os
import subprocess
import tempfile

DEFAULT_BRAND = {"bg": "#ffffff", "fg": "#141414", "accent": "#1f4fd1", "muted": "#6b6b6b",
                 "font": "Helvetica, Arial, sans-serif", "logo_url": None}

SIZES = {"linkedin": (1200, 1200), "x": (1600, 900)}


def _base(brand: dict, w: int, h: int, body: str, footer: str = "") -> str:
    b = {**DEFAULT_BRAND, **(brand or {})}
    logo = f'<img src="{escape(b["logo_url"])}" style="height:36px">' if b.get("logo_url") else ""
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
 html,body{{margin:0;width:{w}px;height:{h}px;background:{b['bg']};color:{b['fg']};font-family:{b['font']};}}
 .wrap{{box-sizing:border-box;width:{w}px;height:{h}px;padding:{int(h*0.09)}px;display:flex;flex-direction:column;justify-content:space-between}}
 .big{{font-size:{int(h*0.22)}px;font-weight:700;line-height:1;letter-spacing:-0.02em;color:{b['accent']}}}
 .h{{font-size:{int(h*0.06)}px;font-weight:600;line-height:1.2}}
 .p{{font-size:{int(h*0.042)}px;line-height:1.35;color:{b['muted']}}}
 .row{{display:flex;gap:{int(w*0.05)}px}} .col{{flex:1}}
 .bar{{height:{int(h*0.02)}px;background:#eee;border-radius:99px;margin-top:{int(h*0.02)}px}} .fill{{height:100%;background:{b['accent']};border-radius:99px}}
 .step{{display:flex;gap:{int(w*0.03)}px;align-items:baseline;margin:{int(h*0.025)}px 0;font-size:{int(h*0.05)}px;line-height:1.25}}
 .n{{color:{b['accent']};font-weight:700;min-width:{int(w*0.06)}px}}
 .q{{font-size:{int(h*0.07)}px;line-height:1.25;font-weight:500}} .q:before{{content:'\\201C';color:{b['accent']}}}
 .foot{{display:flex;justify-content:space-between;align-items:center;font-size:{int(h*0.035)}px;color:{b['muted']}}}
</style></head><body><div class="wrap">{body}<div class="foot"><span>{escape(footer)}</span>{logo}</div></div></body></html>"""


def number_card(brand, platform, *, number: str, label: str, context: str, footer: str = "") -> str:
    w, h = SIZES[platform]
    return _base(brand, w, h, f'<div><div class="big">{escape(number)}</div><div class="h">{escape(label)}</div></div><div class="p">{escape(context)}</div>', footer)


def before_after(brand, platform, *, before_label: str, before: str, after_label: str, after: str, what_changed: str, footer: str = "") -> str:
    w, h = SIZES[platform]
    body = f'''<div class="row"><div class="col"><div class="p">{escape(before_label)}</div><div class="h">{escape(before)}</div></div>
    <div class="col"><div class="p">{escape(after_label)}</div><div class="h" style="color:inherit">{escape(after)}</div></div></div>
    <div class="p"><b>What changed:</b> {escape(what_changed)}</div>'''
    return _base(brand, w, h, body, footer)


def steps(brand, platform, *, title: str, items: list[str], footer: str = "") -> str:
    w, h = SIZES[platform]
    rows = "".join(f'<div class="step"><span class="n">{i+1}</span><span>{escape(t)}</span></div>' for i, t in enumerate(items[:6]))
    return _base(brand, w, h, f'<div><div class="h">{escape(title)}</div>{rows}</div><div></div>', footer)


def quote_card(brand, platform, *, quote: str, attribution: str, footer: str = "") -> str:
    w, h = SIZES[platform]
    return _base(brand, w, h, f'<div class="q">{escape(quote)}</div><div class="p">— {escape(attribution)}</div>', footer)


TEMPLATES = {"number_card": number_card, "before_after": before_after, "steps": steps, "quote_card": quote_card}


def render_png(html: str, platform: str) -> bytes:
    w, h = SIZES[platform]
    with tempfile.TemporaryDirectory() as d:
        src, out, js = os.path.join(d, "c.html"), os.path.join(d, "c.png"), os.path.join(d, "r.js")
        open(src, "w").write(html)
        open(js, "w").write(f"""const {{ chromium }} = require('playwright');
(async () => {{ const b = await chromium.launch({{ executablePath: process.env.CHROMIUM_PATH || undefined, args:['--no-sandbox'] }});
 const p = await b.newPage({{ viewport: {{ width: {w}, height: {h} }} }}); await p.goto('file://{src}');
 await p.screenshot({{ path: '{out}' }}); await b.close(); }})();""")
        subprocess.run(["node", js], check=True, cwd=os.environ.get("PLAYWRIGHT_CWD", os.getcwd()), timeout=60)
        return open(out, "rb").read()


def visual_for_job(job_input: dict, job_output: dict, brand: dict, platform: str, footer: str) -> str | None:
    """Decide whether a post earns a visual and build its HTML. Returns None when the
    text carries everything (most posts)."""
    from .formats import FORMATS
    fmt = job_input.get("format")
    tpl = FORMATS.get(fmt, {}).get("visual")
    claim = job_input.get("claim", {})
    if not tpl:
        return None
    if tpl == "number_card" and claim.get("number"):
        return number_card(brand, platform, number=str(claim["number"]), label=claim.get("text", "")[:60],
                           context=claim.get("evidence", "")[:140], footer=footer)
    if tpl == "quote_card" and claim.get("type") == "quote":
        return quote_card(brand, platform, quote=claim.get("text", "")[:200], attribution=claim.get("customer") or "from a customer", footer=footer)
    if tpl == "steps":
        lines = [l.lstrip("0123456789.-) ").strip() for l in job_output.get("text", "").split("\n") if l.strip() and l.strip()[0].isdigit()]
        if len(lines) >= 3:
            return steps(brand, platform, title=claim.get("text", "")[:70], items=lines, footer=footer)
    if tpl == "before_after" and claim.get("number"):
        return before_after(brand, platform, before_label="Before", before="—", after_label="After",
                            after=str(claim["number"]), what_changed=claim.get("text", "")[:100], footer=footer)
    return None
