# -*- coding: utf-8 -*-
"""Catalog of built-in sources (RSS / Atom feeds of well-known security & network sites).

You can add your own feeds from the control panel, no need to edit this file.
`default: True` means the source is pre-selected on first run.
"""

CATEGORIES = {
    "news": "اخبار امنیتی",
    "advisory": "هشدارها و آسیب‌پذیری‌های رسمی",
    "research": "گزارش‌های پژوهشی و رصد تهدید",
    "network": "شبکه، اینترنت و ناهنجاری‌های رصدی",
    "custom": "منبع سفارشی",
}

CATEGORY_EMOJI = {
    "news": "📰",
    "advisory": "🚨",
    "research": "🔬",
    "network": "🌐",
    "custom": "📌",
}


def _s(id_, name, url, category, default=False):
    return {"id": id_, "name": name, "url": url, "category": category, "default": default}


SOURCES = [
    # ---------- اخبار امنیتی ----------
    _s("thehackernews", "The Hacker News", "https://feeds.feedburner.com/TheHackersNews", "news", True),
    _s("bleepingcomputer", "BleepingComputer", "https://www.bleepingcomputer.com/feed/", "news", True),
    _s("krebs", "Krebs on Security", "https://krebsonsecurity.com/feed/", "news", True),
    _s("securityweek", "SecurityWeek", "https://feeds.feedburner.com/securityweek", "news", True),
    _s("therecord", "The Record (Recorded Future News)", "https://therecord.media/feed", "news", True),
    _s("darkreading", "Dark Reading", "https://www.darkreading.com/rss.xml", "news"),
    _s("securityaffairs", "Security Affairs", "https://securityaffairs.com/feed", "news"),
    _s("helpnetsecurity", "Help Net Security", "https://www.helpnetsecurity.com/feed/", "news"),
    _s("arstechnica", "Ars Technica - Security", "https://arstechnica.com/security/feed/", "news"),
    _s("cyberscoop", "CyberScoop", "https://cyberscoop.com/feed/", "news"),
    _s("schneier", "Schneier on Security", "https://www.schneier.com/feed/atom/", "news"),
    _s("grahamcluley", "Graham Cluley", "https://grahamcluley.com/feed/", "news"),
    _s("troyhunt", "Troy Hunt", "https://www.troyhunt.com/rss/", "news"),

    # ---------- هشدارها و آسیب‌پذیری‌ها ----------
    _s("cisa", "CISA - Cybersecurity Advisories", "https://www.cisa.gov/cybersecurity-advisories/all.xml", "advisory", True),
    _s("ncsc-uk", "NCSC UK", "https://www.ncsc.gov.uk/api/1/services/v1/all-rss-feed.xml", "advisory"),
    _s("msrc", "Microsoft MSRC - Update Guide", "https://api.msrc.microsoft.com/update-guide/rss", "advisory"),
    _s("zdi", "Zero Day Initiative - Published Advisories", "https://www.zerodayinitiative.com/rss/published/", "advisory"),
    _s("exploitdb", "Exploit-DB", "https://www.exploit-db.com/rss.xml", "advisory"),

    # ---------- گزارش‌های پژوهشی / رصد تهدید ----------
    _s("sans-isc", "SANS Internet Storm Center", "https://isc.sans.edu/rssfeed.xml", "research", True),
    _s("talos", "Cisco Talos", "https://blog.talosintelligence.com/rss/", "research", True),
    _s("unit42", "Palo Alto Unit 42", "https://unit42.paloaltonetworks.com/feed/", "research", True),
    _s("securelist", "Kaspersky Securelist", "https://securelist.com/feed/", "research", True),
    _s("welivesecurity", "ESET WeLiveSecurity", "https://www.welivesecurity.com/en/rss/feed/", "research"),
    _s("ms-security", "Microsoft Security Blog", "https://www.microsoft.com/en-us/security/blog/feed/", "research"),
    _s("project-zero", "Google Project Zero", "https://googleprojectzero.blogspot.com/feeds/posts/default", "research"),
    _s("checkpoint", "Check Point Research", "https://research.checkpoint.com/feed/", "research"),
    _s("sophos", "Sophos News", "https://news.sophos.com/en-us/feed/", "research"),
    _s("malwarebytes", "Malwarebytes Labs", "https://www.malwarebytes.com/blog/feed/index.xml", "research"),
    _s("elastic-labs", "Elastic Security Labs", "https://www.elastic.co/security-labs/rss/feed.xml", "research"),
    _s("citizenlab", "Citizen Lab", "https://citizenlab.ca/feed/", "research"),

    # ---------- شبکه، اینترنت و ناهنجاری‌های رصدی ----------
    _s("cloudflare", "Cloudflare Blog", "https://blog.cloudflare.com/rss/", "network", True),
    _s("apnic", "APNIC Blog", "https://blog.apnic.net/feed/", "network", True),
    _s("ooni", "OONI (سنجش سانسور و اختلال)", "https://ooni.org/post/index.xml", "network", True),
    _s("kentik", "Kentik Blog (تحلیل قطعی‌ها)", "https://www.kentik.com/blog/feed/", "network"),
    _s("isoc", "Internet Society", "https://www.internetsociety.org/feed/", "network"),
    _s("tor", "Tor Project Blog", "https://blog.torproject.org/rss.xml", "network"),
]

SOURCES_BY_ID = {s["id"]: s for s in SOURCES}
