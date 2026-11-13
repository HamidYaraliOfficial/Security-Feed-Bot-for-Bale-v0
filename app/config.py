# -*- coding: utf-8 -*-
"""Config file handling (data/config.json)."""
import hashlib
import json
import os
import re
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlparse

from .sources import SOURCES, SOURCES_BY_ID

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("BALEBOT_DATA") or (BASE_DIR / "data"))
CONFIG_PATH = DATA_DIR / "config.json"
_lock = threading.Lock()

DEFAULTS = {
    "bale_token": "",
    "channel_id": "",
    "bale_api_base": "https://tapi.bale.ai",
    "interval_minutes": 15,
    "max_posts_per_cycle": 10,
    "delay_between_posts_sec": 4,
    "max_age_hours": 24,
    "summary_chars": 350,
    "send_images": True,
    "skip_backlog_first_run": False,
    "selected_sources": [s["id"] for s in SOURCES if s["default"]],
    "custom_feeds": [],
    "include_keywords": [],
    "exclude_keywords": [],
    "fetch_proxy": "",
    "bale_proxy": "",
    "seen_retention_days": 30,
    "auto_start": True,
    "panel_port": 8765,
}


def _clamp(v, lo, hi, default):
    try:
        v = int(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def _as_list(v):
    if isinstance(v, str):
        v = re.split(r"[\n,،;]+", v)
    out = []
    for x in v or []:
        x = str(x).strip()
        if x and x not in out:
            out.append(x)
    return out


def normalize_channel(v):
    """Accepts @id, id, numeric id, or a ble.ir link and returns what the API wants."""
    v = (v or "").strip()
    if not v:
        return ""
    if "/join/" in v:            # invite link of a private channel: not usable as chat_id
        return v
    m = re.search(r"(?:ble\.ir|bale\.ai)/@?([A-Za-z0-9_]{3,})", v)
    if m:
        return "@" + m.group(1)
    if re.fullmatch(r"-?\d+", v):
        return v
    return v if v.startswith("@") else "@" + v


def normalize_proxy(v):
    v = (v or "").strip()
    if not v:
        return ""
    if not re.match(r"^(https?|socks4a?|socks5h?)://", v, re.I):
        v = "http://" + v
    return v


def parse_custom_feeds(v):
    """Accepts a list of dicts or text lines 'name | url' (or just 'url')."""
    items = []
    if isinstance(v, str):
        v = v.splitlines()
    for row in v or []:
        if isinstance(row, dict):
            name, url = str(row.get("name", "")).strip(), str(row.get("url", "")).strip()
        else:
            row = str(row).strip()
            if not row:
                continue
            if "|" in row:
                name, url = [p.strip() for p in row.split("|", 1)]
            else:
                name, url = "", row
        if not re.match(r"^https?://", url, re.I):
            continue
        host = urlparse(url).netloc or url
        items.append({
            "id": "custom-" + hashlib.sha1(url.encode()).hexdigest()[:8],
            "name": name or host,
            "url": url,
            "category": "custom",
        })
    seen, out = set(), []
    for it in items:
        if it["url"] not in seen:
            seen.add(it["url"])
            out.append(it)
    return out


def sanitize(cfg):
    d = dict(DEFAULTS)
    d.update({k: v for k, v in (cfg or {}).items() if k in DEFAULTS})
    out = {}
    out["bale_token"] = str(d["bale_token"] or "").strip()
    out["channel_id"] = normalize_channel(d["channel_id"])
    base = str(d["bale_api_base"] or "").strip().rstrip("/")
    out["bale_api_base"] = base if re.match(r"^https?://", base, re.I) else DEFAULTS["bale_api_base"]
    out["interval_minutes"] = _clamp(d["interval_minutes"], 1, 1440, 15)
    out["max_posts_per_cycle"] = _clamp(d["max_posts_per_cycle"], 1, 50, 10)
    out["delay_between_posts_sec"] = _clamp(d["delay_between_posts_sec"], 1, 120, 4)
    out["max_age_hours"] = _clamp(d["max_age_hours"], 1, 720, 24)
    out["summary_chars"] = _clamp(d["summary_chars"], 0, 800, 350)
    out["send_images"] = bool(d["send_images"])
    out["skip_backlog_first_run"] = bool(d["skip_backlog_first_run"])
    out["selected_sources"] = [i for i in _as_list(d["selected_sources"]) if i in SOURCES_BY_ID]
    out["custom_feeds"] = parse_custom_feeds(d["custom_feeds"])
    out["include_keywords"] = [k.lower() for k in _as_list(d["include_keywords"])]
    out["exclude_keywords"] = [k.lower() for k in _as_list(d["exclude_keywords"])]
    out["fetch_proxy"] = normalize_proxy(d["fetch_proxy"])
    out["bale_proxy"] = normalize_proxy(d["bale_proxy"])
    out["seen_retention_days"] = _clamp(d["seen_retention_days"], 3, 365, 30)
    out["auto_start"] = bool(d["auto_start"])
    out["panel_port"] = _clamp(d["panel_port"], 1024, 65535, 8765)
    return out


def load():
    with _lock:
        raw = {}
        if CONFIG_PATH.exists():
            try:
                raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                raw = {}
        return sanitize(raw)


def save(cfg):
    cfg = sanitize(cfg)
    with _lock:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(DATA_DIR), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            try:
                os.chmod(tmp, 0o600)
            except OSError:
                pass
            os.replace(tmp, CONFIG_PATH)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
    return cfg


def mask_token(token):
    if not token:
        return ""
    return token[:4] + "…" + token[-4:] if len(token) > 12 else "••••••"


def active_sources(cfg):
    chosen = [SOURCES_BY_ID[i] for i in cfg["selected_sources"] if i in SOURCES_BY_ID]
    return chosen + list(cfg["custom_feeds"])
