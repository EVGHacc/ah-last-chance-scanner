"""Strict public Personio XML inventory with live first-party application verification."""
from html import unescape
from html.parser import HTMLParser
import re
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree


class PersonioError(ValueError):
    pass


class _JobPage(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_h1 = False
        self.h1 = []
        self.apply_links = []
        self.text = []
        self.in_body_text = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "h1":
            self.in_h1 = True
        if tag in ("p", "li"):
            self.in_body_text = True
        if tag == "a" and a.get("href"):
            self.apply_links.append(a["href"])

    def handle_endtag(self, tag):
        if tag == "h1":
            self.in_h1 = False
        if tag in ("p", "li"):
            self.in_body_text = False

    def handle_data(self, data):
        if self.in_h1:
            self.h1.append(data)
        if self.in_body_text:
            self.text.append(data)


def _plain(value):
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", value or "")).split())


def parse_inventory(xml_text, board_url, detail_fetcher):
    """Reject unknown XML, uncorroborated zero, duplicate IDs and missing live apply."""
    if "<!DOCTYPE" in xml_text.upper() or "<!ENTITY" in xml_text.upper():
        raise PersonioError("unsafe XML declaration")
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as exc:
        raise PersonioError("invalid XML") from exc
    if root.tag != "workzag-jobs":
        raise PersonioError("unexpected Personio XML root")
    positions = list(root)
    if not positions or any(p.tag != "position" for p in positions):
        raise PersonioError("empty or invalid public position feed; zero not corroborated")
    board = board_url.rstrip("/")
    host = urlparse(board).netloc
    if not host.endswith(".jobs.personio.com") and not host.endswith(".jobs.personio.de"):
        raise PersonioError("untrusted Personio board")
    seen = set()
    jobs = []
    for p in positions:
        job_id = (p.findtext("id") or "").strip()
        title = (p.findtext("name") or "").strip()
        if not job_id.isdigit() or not title or job_id in seen:
            raise PersonioError("invalid or duplicate job identity")
        seen.add(job_id)
        url = f"{board}/job/{job_id}"
        page = _JobPage()
        page.feed(detail_fetcher(url))
        page_title = " ".join(" ".join(page.h1).split())
        if not page_title or page_title.casefold() != title.casefold():
            raise PersonioError("live job title missing or mismatched")
        valid_apply = []
        for href in page.apply_links:
            link = urljoin(url, href)
            parsed = urlparse(link)
            if parsed.scheme == "https" and parsed.netloc == host and parsed.path.rstrip("/") == f"/job/{job_id}/apply":
                valid_apply.append(link)
        if not valid_apply:
            raise PersonioError("live first-party apply route missing")
        blocks = p.findall("./jobDescriptions/jobDescription/value")
        description = " ".join(filter(None, (_plain(x.text) for x in blocks)))
        if not description:
            description = " ".join(" ".join(page.text).split())
        if len(description) < 30:
            raise PersonioError("job description unavailable")
        jobs.append({
            "job_id": job_id,
            "title": title,
            "short_summary": description[:1200],
            "location": (p.findtext("office") or "").strip(),
            "department": (p.findtext("department") or "").strip(),
            "job_url": url,
            "apply_url": valid_apply[0],
            "published_at": (p.findtext("createdAt") or "").strip() or None,
        })
    return jobs
