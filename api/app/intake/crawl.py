"""Fetch a company's public site and docs and reduce them to clean text the LLM can read.
Public pages only; respects a small page budget so intake stays under a minute."""
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

UA = "MarketingEngineerBot/0.1 (+intake; contact: founder)"
MAX_PAGES = 12
MAX_CHARS_PER_PAGE = 6000


@dataclass
class CrawlResult:
    root: str
    pages: list[dict] = field(default_factory=list)   # {url, title, text}
    errors: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n\n".join(f"# {p['title']}\n{p['text']}" for p in self.pages)


def _clean(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "nav", "footer", "svg", "noscript"]):
        t.decompose()
    title = (soup.title.string or "").strip() if soup.title else ""
    text = " ".join(soup.get_text(" ").split())
    return title, text[:MAX_CHARS_PER_PAGE]


def crawl(root_url: str, extra_urls: list[str] | None = None, max_pages: int = MAX_PAGES) -> CrawlResult:
    if not root_url.startswith("http"):
        root_url = "https://" + root_url
    res = CrawlResult(root=root_url)
    host = urlparse(root_url).netloc
    queue = [root_url] + list(extra_urls or [])
    seen: set[str] = set()
    with httpx.Client(headers={"User-Agent": UA}, timeout=10, follow_redirects=True) as c:
        while queue and len(res.pages) < max_pages:
            url = queue.pop(0)
            if url in seen:
                continue
            seen.add(url)
            try:
                r = c.get(url)
                if r.status_code != 200 or "text/html" not in r.headers.get("content-type", ""):
                    continue
                title, text = _clean(r.text)
                if len(text) < 200:
                    continue
                res.pages.append({"url": url, "title": title or url, "text": text})
                # follow same-host links from the root page and obvious product/docs pages
                soup = BeautifulSoup(r.text, "lxml")
                for a in soup.find_all("a", href=True):
                    u = urljoin(url, a["href"]).split("#")[0]
                    if urlparse(u).netloc == host and u not in seen and any(
                        k in u.lower() for k in ("product", "feature", "pricing", "docs", "about", "customers", "solutions", "how", "use-case")):
                        queue.append(u)
            except Exception as e:  # noqa: BLE001
                res.errors.append(f"{url}: {e}")
    return res
