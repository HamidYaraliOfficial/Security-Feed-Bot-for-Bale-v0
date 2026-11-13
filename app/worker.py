# -*- coding: utf-8 -*-
"""Background engine: fetch feeds -> queue -> send to Bale -> delete from queue."""
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from . import config, fetcher
from .bale import BaleClient, BaleError, explain, is_fatal
from .db import Store

MAX_QUEUE = 500          # safety cap, oldest overflow is dropped
MAX_TRIES = 3            # after 3 failed attempts a post is dropped (so the DB never clogs)
CAPTION_LIMIT = 1000
TEXT_LIMIT = 3900


class Engine:
    def __init__(self):
        self.store = Store(config.DATA_DIR / "bot.db")
        self.logs = deque(maxlen=300)
        self.stop_evt = threading.Event()
        self.wake_evt = threading.Event()
        self.thread = None
        self.cache = {}
        self.status = {"running": False, "state": "متوقف", "last_cycle": None, "next_cycle": None,
                       "last_summary": "", "last_error": ""}

    # ------------------------------------------------------------ utilities
    def log(self, msg, level="info"):
        token = config.load().get("bale_token") or ""
        if token:
            msg = msg.replace(token, "***")
        stamp = datetime.now().strftime("%H:%M:%S")
        self.logs.append({"t": stamp, "level": level, "msg": msg})
        try:
            print(f"[{stamp}] {level.upper():5} {msg}", flush=True)
        except Exception:
            pass

    def snapshot(self):
        st = dict(self.status)
        st.update(self.store.stats())
        st["sent_total"] = int(self.store.get_meta("sent_total", 0) or 0)
        return st

    # ------------------------------------------------------------ lifecycle
    def start(self):
        if self.thread and self.thread.is_alive():
            return False
        self.stop_evt.clear()
        self.wake_evt.clear()
        self.thread = threading.Thread(target=self._loop, name="engine", daemon=True)
        self.thread.start()
        return True

    def stop(self):
        self.stop_evt.set()
        self.wake_evt.set()
        if self.thread:
            self.thread.join(timeout=8)
        self.status.update(running=False, state="متوقف", next_cycle=None)
        self.log("ربات متوقف شد.")

    def run_now(self):
        self.wake_evt.set()

    @property
    def running(self):
        return bool(self.thread and self.thread.is_alive())

    def _loop(self):
        self.status.update(running=True, state="در حال اجرا")
        self.log("ربات شروع به کار کرد.")
        while not self.stop_evt.is_set():
            try:
                self.run_cycle()
            except Exception as e:      # never let the loop die
                self.log(f"خطای غیرمنتظره: {type(e).__name__}: {e}", "error")
            if self.stop_evt.is_set():
                break
            wait = config.load()["interval_minutes"] * 60
            self.status["next_cycle"] = time.time() + wait
            self.wake_evt.clear()
            self.wake_evt.wait(wait)
        self.status.update(running=False, state="متوقف", next_cycle=None)

    # ------------------------------------------------------------ one cycle
    def run_cycle(self):
        cfg = config.load()
        if not cfg["bale_token"] or not cfg["channel_id"]:
            self.status.update(state="تنظیمات ناقص (توکن یا کانال)", last_error="توکن یا آیدی کانال وارد نشده است.")
            self.log("توکن یا آیدی کانال وارد نشده؛ این دوره رد شد.", "warn")
            return
        self.status.update(state="در حال دریافت منابع…")
        added, failed = self.ingest(cfg)
        self.status["state"] = "در حال ارسال…"
        sent = self.dispatch(cfg)
        pruned = self.store.prune(cfg["seen_retention_days"], MAX_QUEUE)
        if pruned:
            self.log(f"{pruned} مورد قدیمی از صف حذف شد (سقف صف {MAX_QUEUE}).", "warn")
        self.status.update(
            state="در حال اجرا (منتظر دوره بعد)", last_cycle=time.time(),
            last_summary=f"{added} مطلب جدید، {sent} ارسال، {failed} منبع ناموفق")
        self.log(f"پایان دوره: {added} مطلب جدید در صف، {sent} ارسال شد، {failed} منبع ناموفق.")

    # ------------------------------------------------------------ fetching
    def ingest(self, cfg):
        sources = config.active_sources(cfg)
        if not sources:
            self.log("هیچ منبعی انتخاب نشده است.", "warn")
            return 0, 0
        first_run = self.store.get_meta("initialized") != "1"
        skip = first_run and cfg["skip_backlog_first_run"]
        cutoff = time.time() - cfg["max_age_hours"] * 3600

        def work(src):
            try:
                content = fetcher.fetch_feed(fetcher.new_session(cfg["fetch_proxy"]), src["url"], self.cache)
                return src, ([] if content is None else fetcher.parse_feed(content, src)), None
            except Exception as e:
                return src, [], fetcher.describe_error(e)

        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(work, sources))

        added, failures = 0, []
        for src, items, err in results:
            if err:
                failures.append(f"{src['name']} ({err})")
                continue
            for it in items:
                if it["published_ts"] < cutoff or self.store.is_known(it["uid"]):
                    continue
                if not fetcher.passes_filters(it, cfg["include_keywords"], cfg["exclude_keywords"]):
                    continue
                if skip:
                    self.store.mark_seen(it["uid"])
                elif self.store.add_pending(it):
                    added += 1
        if first_run:
            self.store.set_meta("initialized", "1")
            if skip:
                self.log("اولین اجرا: مطالب موجود فعلی نادیده گرفته شد؛ فقط مطالب جدید ارسال می‌شود.")
        if failures:
            self.log("منابع ناموفق: " + "، ".join(failures), "warn")
        return added, len(failures)

    # ------------------------------------------------------------ sending
    def dispatch(self, cfg):
        rows = self.store.pending(cfg["max_posts_per_cycle"])
        if not rows:
            return 0
        client = BaleClient(cfg["bale_token"], cfg["bale_api_base"], cfg["bale_proxy"])
        img_session = fetcher.new_session(cfg["fetch_proxy"])
        sent = 0
        for row in rows:
            if self.stop_evt.is_set():
                break
            try:
                self._send_with_retry(client, img_session, cfg, row)
            except BaleError as e:
                if e.network:
                    self.status["last_error"] = explain(e)
                    self.log("ارسال متوقف شد (مشکل اتصال): " + explain(e), "error")
                    break
                if is_fatal(e):
                    self.status["last_error"] = explain(e)
                    self.log("خطای تنظیمات: " + explain(e), "error")
                    break
                tries = self.store.bump(row["id"])
                self.log(f"ارسال «{row['title'][:50]}» ناموفق ({e.description}) تلاش {tries}/{MAX_TRIES}", "warn")
                if tries >= MAX_TRIES:
                    self.store.finish(row["id"], row["uid"])
                    self.log("این مطلب پس از چند تلاش حذف شد.", "warn")
                continue
            # success -> delete full content from DB, keep only the tiny 'seen' marker
            self.store.finish(row["id"], row["uid"])
            total = int(self.store.get_meta("sent_total", 0) or 0) + 1
            self.store.set_meta("sent_total", total)
            self.status["last_error"] = ""
            sent += 1
            self.log(f"ارسال شد: {row['title'][:70]}")
            self.stop_evt.wait(cfg["delay_between_posts_sec"])
        return sent

    def _send_with_retry(self, client, img_session, cfg, row):
        try:
            self._send_item(client, img_session, cfg, row)
        except BaleError as e:
            if e.code == 429:
                wait = max(1, min(int(e.retry_after or 10), 120))
                self.log(f"محدودیت نرخ بله؛ {wait} ثانیه صبر می‌کنم.", "warn")
                self.stop_evt.wait(wait)
                self._send_item(client, img_session, cfg, row)
            else:
                raise

    def _send_item(self, client, img_session, cfg, row):
        chat = cfg["channel_id"]
        if cfg["send_images"]:
            url = row.get("image_url") or fetcher.find_og_image(img_session, row.get("link"))
            img = fetcher.download_image(img_session, url) if url else None
            if img:
                caption = fetcher.format_message(row, CAPTION_LIMIT, cfg["summary_chars"])
                try:
                    client.send_photo(chat, img[0], img[1], caption)
                    return
                except BaleError as e:
                    if e.network or e.code in (401, 403, 429):
                        raise
                    self.log(f"ارسال تصویر نشد ({e.description}); فقط متن ارسال می‌شود.", "warn")
        client.send_message(chat, fetcher.format_message(row, TEXT_LIMIT, cfg["summary_chars"]))
