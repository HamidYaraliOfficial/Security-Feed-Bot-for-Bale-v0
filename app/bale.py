# -*- coding: utf-8 -*-
"""Minimal client for the Bale Bot API (https://tapi.bale.ai/bot<TOKEN>/<method>)."""
import re

import requests


class BaleError(Exception):
    def __init__(self, description, code=None, retry_after=None, network=False):
        super().__init__(description)
        self.description = description
        self.code = code
        self.retry_after = retry_after
        self.network = network          # transient problem (connection / 5xx): try again later


_FATAL_RE = re.compile(
    r"chat not found|not found|forbidden|unauthorized|not enough rights|administrator|kicked|not a member|rights",
    re.I,
)


def is_fatal(e):
    """Errors that mean 'configuration is wrong' (bad token / channel / permissions)."""
    if e.network:
        return False
    if e.code in (401, 403, 404):
        return True
    return e.code == 400 and bool(_FATAL_RE.search(e.description or ""))


def explain(e):
    """Human friendly (Persian) explanation of a BaleError."""
    d = (e.description or "").lower()
    if e.network:
        return ("اتصال به سرور بله برقرار نشد. اینترنت را بررسی کنید؛ اگر برنامه خارج از ایران اجرا می‌شود "
                "و بله باز نمی‌شود، در بخش «پیشرفته» پروکسی بله را تنظیم کنید.")
    if e.code == 401:
        return "توکن نامعتبر است. توکن را دقیقاً از @botfather کپی کنید (بدون فاصله اضافه)."
    if e.code == 403 or "rights" in d or "administrator" in d:
        return "ربات اجازهٔ ارسال در این کانال را ندارد. ربات را ادمین کانال کنید و دسترسی «ارسال پیام» بدهید."
    if e.code in (400, 404):
        return ("کانال پیدا نشد. آیدی کانال را بررسی کنید (مثل @mychannel یا عدد) و مطمئن شوید ربات "
                "در کانال ادمین است.")
    if e.code == 429:
        return "بله موقتاً محدودیت نرخ اعمال کرده؛ چند دقیقه بعد دوباره امتحان کنید."
    return f"خطای بله: {e.description} (کد {e.code})"


class BaleClient:
    def __init__(self, token, base="https://tapi.bale.ai", proxy="", timeout=(10, 45)):
        self._url = f"{base.rstrip('/')}/bot{token}/"
        self.session = requests.Session()
        if proxy:
            self.session.proxies = {"http": proxy, "https": proxy}
        self.timeout = timeout

    @staticmethod
    def _chat(chat_id):
        s = str(chat_id)
        return int(s) if re.fullmatch(r"-?\d+", s) else s

    def call(self, method, payload=None, files=None):
        try:
            if files:
                r = self.session.post(self._url + method, data=payload or {}, files=files, timeout=self.timeout)
            else:
                r = self.session.post(self._url + method, json=payload or {}, timeout=self.timeout)
        except requests.RequestException as e:
            # never include str(e): it may contain the URL (and therefore the token)
            raise BaleError("network error: " + type(e).__name__, network=True) from None
        try:
            data = r.json()
        except ValueError:
            raise BaleError(f"invalid response (HTTP {r.status_code})", code=r.status_code,
                            network=r.status_code >= 500) from None
        if r.ok and data.get("ok"):
            return data.get("result")
        code = data.get("error_code") or r.status_code
        params = data.get("parameters") or {}
        raise BaleError(str(data.get("description") or f"HTTP {r.status_code}"), code=code,
                        retry_after=params.get("retry_after"), network=code >= 500)

    def get_me(self):
        return self.call("getMe")

    def send_message(self, chat_id, text):
        return self.call("sendMessage", {"chat_id": self._chat(chat_id), "text": text})

    def send_photo(self, chat_id, data, filename, caption):
        return self.call("sendPhoto", {"chat_id": str(chat_id), "caption": caption},
                         files={"photo": (filename, data)})

    def get_updates(self):
        return self.call("getUpdates", {"limit": 100, "timeout": 0})
