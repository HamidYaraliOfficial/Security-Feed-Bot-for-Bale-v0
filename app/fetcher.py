# -*- coding: utf-8 -*-
"""Download + parse feeds, find images, format messages."""
import calendar
import hashlib
import re
import time
import warnings
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import feedparser
import requests
from bs4 import BeautifulSoup

from .sources import CATEGORIES, CATEGORY_EMOJI

warnings.filterwarnings("ignore", category=UserWarning, module="bs4")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36 SecurityFeedBot/1.0")
TEHRAN = timezone(timedelta(hours=3, minutes=30))
_BAD_IMG = re.compile(r"(pixel|tracker|feedburner\.com/~|doubleclick|gravatar|emoji|/ads?/|\.svg(\?|$)|spacer|1x1)", re.I)


# ----------------------------------------------------------------- HTTP helpers
def new_session(proxy=""):
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.5",
        "Accept-Language": "en-US,en;q=0.8",
    })
    if proxy:
        s.proxies = {"http": proxy, "https": proxy}
    return s


def fetch_feed(session, url, cache=None, timeout=(8, 25)):
    """Returns bytes, or None when the server says 'not modified'."""
    headers = {}
    if cache is not None and url in cache:
        etag, last_mod = cache[url]
        if etag:
            headers["If-None-Match"] = etag
        if last_mod:
            headers["If-Modified-Since"] = last_mod
    r = session.get(url, headers=headers, timeout=timeout)
    if r.status_code == 304:
        return None
    r.raise_for_status()
    if cache is not None:
        cache[url] = (r.headers.get("ETag"), r.headers.get("Last-Modified"))
    return r.content[:5_000_000]


def describe_error(e):
    if isinstance(e, requests.HTTPError):
        return f"HTTP {e.response.status_code}" if e.response is not None else "HTTP error"
    if isinstance(e, requests.Timeout):
        return "timeout"
    if isinstance(e, requests.ConnectionError):
        return "اتصال برقرار نشد"
    if isinstance(e, ValueError):
        return str(e)
    return type(e).__name__


# ----------------------------------------------------------------- parsing
def clean_text(html):
    if not html:
        return ""
    text = BeautifulSoup(str(html), "html.parser").get_text(" ")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s*(The post|The article)\b.{0,200}?\bappeared first on\b.*$", "", text, flags=re.I)
    text = re.sub(r"\s*\[?(…|\.\.\.)\]?\s*(Read more|Continue reading)?\W*$", "", text, flags=re.I)
    return text.strip()


def norm_link(url):
    url = (url or "").strip()
    if not url:
        return ""
    p = urlparse(url)
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
         if not k.lower().startswith("utm_") and k.lower() not in ("fbclid", "gclid")]
    return urlunparse(p._replace(query=urlencode(q), fragment=""))


def _entry_ts(e):
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        v = e.get(key)
        if v:
            try:
                return min(calendar.timegm(v), int(time.time()))
            except (TypeError, ValueError, OverflowError):
                pass
    return int(time.time())


def _is_img_url(u):
    return bool(u) and not _BAD_IMG.search(u)


def extract_image(e, base_link):
    for m in e.get("media_content", []) or []:
        u = m.get("url", "")
        if _is_img_url(u) and (str(m.get("type", "")).startswith("image") or m.get("medium") == "image"
                               or re.search(r"\.(jpe?g|png|webp|gif)(\?|$)", u, re.I)):
            return u
    for m in e.get("media_thumbnail", []) or []:
        if _is_img_url(m.get("url", "")):
            return m["url"]
    for l in e.get("links", []) or []:
        if l.get("rel") == "enclosure" and str(l.get("type", "")).startswith("image") and _is_img_url(l.get("href", "")):
            return l["href"]
    html_parts = [e.get("summary", "")] + [c.get("value", "") for c in (e.get("content") or [])]
    for html in html_parts:
        if not html or "<img" not in html.lower():
            continue
        for img in BeautifulSoup(html, "html.parser").find_all("img"):
            src = img.get("src") or img.get("data-src") or ""
            try:
                if int(img.get("width", 100)) <= 2 or int(img.get("height", 100)) <= 2:
                    continue
            except ValueError:
                pass
            src = urljoin(base_link, src.strip())
            if src.startswith("http") and _is_img_url(src):
                return src
    return ""


def parse_feed(content, src):
    d = feedparser.parse(content)
    if not d.entries:
        if d.bozo:
            raise ValueError("فید معتبر نیست (RSS/Atom نیست یا صفحه خطا برگشته)")
        return []
    items = []
    for e in d.entries[:40]:
        link = norm_link(e.get("link"))
        title = clean_text(e.get("title"))
        if not (link or title):
            continue
        summary_html = e.get("summary") or ((e.get("content") or [{}])[0].get("value", ""))
        summary = clean_text(summary_html)
        if summary.lower() == title.lower():
            summary = ""
        basis = link or e.get("id") or title
        items.append({
            "uid": hashlib.sha1(basis.encode("utf-8", "ignore")).hexdigest()[:20],
            "source": src["name"],
            "category": src.get("category", "custom"),
            "title": title or link,
            "link": link,
            "summary": summary,
            "image_url": extract_image(e, link),
            "published_ts": _entry_ts(e),
        })
    return items


def passes_filters(item, include, exclude):
    hay = f"{item['title']} {item['summary']}".lower()
    if exclude and any(k in hay for k in exclude):
        return False
    if include and not any(k in hay for k in include):
        return False
    return True


# ----------------------------------------------------------------- images
def find_og_image(session, page_url):
    if not page_url:
        return ""
    try:
        r = session.get(page_url, timeout=(6, 12), stream=True)
        try:
            if r.status_code != 200:
                return ""
            buf = b""
            for part in r.iter_content(16384):
                buf += part
                if len(buf) > 250_000 or b"</head>" in buf.lower():
                    break
            enc = r.encoding or "utf-8"
        finally:
            r.close()
    except requests.RequestException:
        return ""
    soup = BeautifulSoup(buf.decode(enc, "ignore"), "html.parser")
    for attrs in ({"property": "og:image"}, {"name": "twitter:image"}, {"property": "og:image:url"}):
        m = soup.find("meta", attrs=attrs)
        if m and m.get("content"):
            u = urljoin(page_url, m["content"].strip())
            if u.startswith("http") and _is_img_url(u):
                return u
    return ""


def download_image(session, url, max_bytes=8_000_000):
    """Returns (bytes, filename) or None. The image lives only in memory."""
    try:
        r = session.get(url, timeout=(8, 25), stream=True, headers={"Accept": "image/*"})
        try:
            if r.status_code != 200:
                return None
            ctype = r.headers.get("Content-Type", "").split(";")[0].strip().lower()
            ext = {"image/jpeg": "jpg", "image/jpg": "jpg", "image/png": "png",
                   "image/gif": "gif", "image/webp": "webp"}.get(ctype)
            if not ext:
                return None
            data = bytearray()
            for part in r.iter_content(65536):
                data.extend(part)
                if len(data) > max_bytes:
                    return None
        finally:
            r.close()
    except requests.RequestException:
        return None
    if len(data) < 2000:          # tracking pixel / broken image
        return None
    return bytes(data), f"image.{ext}"


# ----------------------------------------------------------------- formatting
def gregorian_to_jalali(gy, gm, gd):
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    if gy > 1600:
        jy, gy = 979, gy - 1600
    else:
        jy, gy = 0, gy - 621
    gy2 = gy + 1 if gm > 2 else gy
    days = (365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400 - 80 + gd + g_d_m[gm - 1])
    jy += 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm, jd = 1 + days // 31, 1 + days % 31
    else:
        jm, jd = 7 + (days - 186) // 30, 1 + (days - 186) % 30
    return jy, jm, jd


def fmt_time(ts):
    dt = datetime.fromtimestamp(ts, TEHRAN)
    jy, jm, jd = gregorian_to_jalali(dt.year, dt.month, dt.day)
    utc = dt.astimezone(timezone.utc)
    return f"{jy:04d}/{jm:02d}/{jd:02d} {dt:%H:%M} (تهران) | {utc:%Y-%m-%d %H:%M} UTC"


def _cut(text, n):
    if n <= 0:
        return ""
    if len(text) <= n:
        return text
    cut = text[: n - 1]
    if " " in cut[int(n * 0.6):]:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip(" .,;:-") + "…"


def format_message(item, limit, summary_chars):
    emoji = CATEGORY_EMOJI.get(item["category"], "📌")
    head = f"{emoji} {_cut(item['title'], 250)}"
    tail_lines = [
        f"📰 منبع: {item['source']}",
        f"🏷 دسته: {CATEGORIES.get(item['category'], 'منبع سفارشی')}",
        f"🕒 {fmt_time(item['published_ts'])}",
    ]
    if item.get("link"):
        tail_lines.append(f"🔗 {item['link']}")
    tail = "\n".join(tail_lines)
    budget = limit - len(head) - len(tail) - 4
    summary = _cut(item.get("summary", ""), min(summary_chars, budget))
    parts = [head] + ([summary] if summary else []) + [tail]
    text = "\n\n".join(parts)
    return text if len(text) <= limit else text[: limit - 1] + "…"
