"""Fail-closed, first-party Breezy public JSON inventory and live apply proof."""
from html import unescape
from html.parser import HTMLParser
import re
from urllib.parse import urljoin, urlparse


class BreezyError(ValueError):
    pass


class _Detail(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_title = False
        self.in_heading = False
        self.in_text = False
        self.titles = []
        self.headings = []
        self.paragraphs = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "title":
            self.in_title = True
        if tag in ("h1", "h2"):
            self.in_heading = True
        if tag in ("p", "li"):
            self.in_text = True
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag in ("h1", "h2"):
            self.in_heading = False
        if tag in ("p", "li"):
            self.in_text = False

    def handle_data(self, data):
        if self.in_title:
            self.titles.append(data)
        if self.in_heading:
            self.headings.append(data)
        if self.in_text:
            self.paragraphs.append(data)


def _clean(value):
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", value or "")).split())


def _board_host(board_url):
    parsed = urlparse(board_url)
    host = parsed.hostname or ""
    if parsed.scheme != "https" or parsed.port is not None or not re.fullmatch(r"[a-z0-9-]+\.breezy\.hr", host):
        raise BreezyError("untrusted Breezy board")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment or parsed.username:
        raise BreezyError("Breezy board must be a pinned HTTPS root")
    return host


def _identity(url, host):
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc != host or parsed.port is not None or parsed.query or parsed.fragment:
        raise BreezyError("job URL is not on pinned first-party board")
    match = re.fullmatch(r"/p/([0-9a-f]{12,32})(?:-[a-z0-9-]+)?/?", parsed.path)
    if not match:
        raise BreezyError("invalid Breezy job URL")
    return match.group(1)


def parse_inventory(payload, board_url, detail_fetcher):
    """Require complete nonzero JSON list, unique IDs, live details and apply routes."""
    host = _board_host(board_url)
    if not isinstance(payload, list) or not payload:
        raise BreezyError("invalid or uncorroborated zero Breezy inventory")
    seen = set()
    jobs = []
    for raw in payload:
        if not isinstance(raw, dict):
            raise BreezyError("malformed Breezy position")
        ident = raw.get("_id")
        title = raw.get("name")
        url = raw.get("url")
        if not isinstance(ident, str) or not re.fullmatch(r"[0-9a-f]{12,32}", ident):
            raise BreezyError("invalid Breezy position ID")
        if not isinstance(title, str) or not title.strip() or not isinstance(url, str):
            raise BreezyError("missing title or first-party job URL")
        if _identity(url, host) != ident or ident in seen:
            raise BreezyError("cross-board or duplicate Breezy position")
        seen.add(ident)
        parsed = _Detail()
        parsed.feed(detail_fetcher(url))
        visible = _clean(" ".join(parsed.titles + parsed.headings))
        if title.casefold() not in visible.casefold():
            raise BreezyError("live detail title missing or mismatched")
        summary = _clean(" ".join(parsed.paragraphs))
        if len(summary) < 30:
            raise BreezyError("live first-party job description missing")
        expected = url.rstrip("/") + "/apply"
        apply_links = [urljoin(url, href) for href in parsed.links]
        if expected not in apply_links:
            raise BreezyError("live first-party application link missing")
        loc = raw.get("location")
        location = _clean(loc.get("name")) if isinstance(loc, dict) else ""
        jobs.append({
            "job_id": ident,
            "title": title.strip(),
            "short_summary": summary[:1200],
            "location": location,
            "department": _clean(raw.get("department")) if isinstance(raw.get("department"), str) else "",
            "job_url": url,
            "apply_url": expected,
            "published_at": raw.get("published_date") if isinstance(raw.get("published_date"), str) else None,
        })
    return jobs
