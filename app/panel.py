# -*- coding: utf-8 -*-
"""Local control panel (runs on 127.0.0.1 only). Persian / RTL, opens in your browser."""
import json
import re
import secrets
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import config, fetcher
from .bale import BaleClient, BaleError, explain
from .sources import CATEGORIES, SOURCES

PANEL_TOKEN = secrets.token_urlsafe(24)       # protects the API against other websites (CSRF)
WEB_DIR = Path(__file__).resolve().parent / "web"
ALLOWED_HOSTS = {"127.0.0.1", "localhost", "[::1]"}


def public_config(cfg):
    out = dict(cfg)
    out["token_masked"] = config.mask_token(cfg["bale_token"])
    out["has_token"] = bool(cfg["bale_token"])
    out["bale_token"] = ""
    out["custom_feeds_text"] = "\n".join(f"{f['name']} | {f['url']}" for f in cfg["custom_feeds"])
    out["include_keywords_text"] = "\n".join(cfg["include_keywords"])
    out["exclude_keywords_text"] = "\n".join(cfg["exclude_keywords"])
    return out


def make_handler(engine):
    class Handler(BaseHTTPRequestHandler):
        server_version = "SecBot"

        def log_message(self, *a):
            pass

        # -------- helpers
        def _send(self, code, body, ctype="application/json; charset=utf-8"):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy",
                             "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'")
            self.end_headers()
            self.wfile.write(body)

        def _host_ok(self):
            return self.headers.get("Host", "").rsplit(":", 1)[0] in ALLOWED_HOSTS

        def _json_body(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n > 1_000_000:
                return {}
            try:
                return json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return {}

        def _auth(self):
            return secrets.compare_digest(self.headers.get("X-Panel-Token", ""), PANEL_TOKEN)

        # -------- routes
        def do_GET(self):
            if not self._host_ok():
                return self._send(403, {"ok": False})
            if self.path in ("/", "/index.html"):
                html = (WEB_DIR / "index.html").read_text(encoding="utf-8").replace("__PANEL_TOKEN__", PANEL_TOKEN)
                return self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
            if not self._auth():
                return self._send(403, {"ok": False, "error": "forbidden"})
            if self.path == "/api/config":
                return self._send(200, {
                    "config": public_config(config.load()),
                    "sources": SOURCES, "categories": CATEGORIES,
                })
            if self.path == "/api/status":
                return self._send(200, {"status": engine.snapshot(), "logs": list(engine.logs)[-120:]})
            self._send(404, {"ok": False})

        def do_POST(self):
            if not self._host_ok() or not self._auth():
                return self._send(403, {"ok": False, "error": "forbidden"})
            body = self._json_body()
            route = self.path
            try:
                if route == "/api/save":
                    return self._send(200, self._save(body))
                if route == "/api/test_bale":
                    return self._send(200, self._test_bale(body))
                if route == "/api/test_sources":
                    return self._send(200, self._test_sources(body))
                if route == "/api/detect_chat":
                    return self._send(200, self._detect_chat(body))
                if route == "/api/start":
                    cfg = config.load()
                    if not cfg["bale_token"] or not cfg["channel_id"]:
                        return self._send(200, {"ok": False, "error": "ابتدا توکن و آیدی کانال را وارد و ذخیره کنید."})
                    engine.start()
                    return self._send(200, {"ok": True})
                if route == "/api/stop":
                    engine.stop()
                    return self._send(200, {"ok": True})
                if route == "/api/run_now":
                    if engine.running:
                        engine.run_now()
                        return self._send(200, {"ok": True})
                    return self._send(200, {"ok": False, "error": "ربات در حال اجرا نیست؛ ابتدا «شروع» را بزنید."})
                if route == "/api/clear_db":
                    engine.store.clear_queue() if body.get("only_queue") else engine.store.clear_all()
                    return self._send(200, {"ok": True})
            except Exception as e:      # keep the panel alive
                return self._send(200, {"ok": False, "error": f"{type(e).__name__}: {e}"})
            self._send(404, {"ok": False})

        # -------- actions
        def _merged(self, body):
            old = config.load()
            new = dict(old)
            for k in config.DEFAULTS:
                if k in body:
                    new[k] = body[k]
            tok = str(body.get("bale_token") or "").strip()
            if not tok or tok == config.mask_token(old["bale_token"]):
                new["bale_token"] = old["bale_token"]
            if "custom_feeds_text" in body:
                new["custom_feeds"] = body["custom_feeds_text"]
            if "include_keywords_text" in body:
                new["include_keywords"] = body["include_keywords_text"]
            if "exclude_keywords_text" in body:
                new["exclude_keywords"] = body["exclude_keywords_text"]
            return config.sanitize(new)

        def _save(self, body):
            cfg = config.save(self._merged(body))
            return {"ok": True, "config": public_config(cfg)}

        def _test_bale(self, body):
            cfg = self._merged(body)
            steps = []
            if not cfg["bale_token"]:
                return {"ok": False, "steps": [{"ok": False, "text": "توکن وارد نشده است."}]}
            client = BaleClient(cfg["bale_token"], cfg["bale_api_base"], cfg["bale_proxy"], timeout=(10, 25))
            try:
                me = client.get_me() or {}
                steps.append({"ok": True, "text": f"توکن معتبر است. نام کاربری ربات: @{me.get('username', '?')}"})
            except BaleError as e:
                steps.append({"ok": False, "text": explain(e)})
                return {"ok": False, "steps": steps}
            if not cfg["channel_id"]:
                steps.append({"ok": False, "text": "آیدی کانال وارد نشده است."})
                return {"ok": False, "steps": steps}
            try:
                client.send_message(cfg["channel_id"], "✅ اتصال ربات رصد امنیتی برقرار شد (پیام آزمایشی).")
                steps.append({"ok": True, "text": f"پیام آزمایشی در {cfg['channel_id']} ارسال شد؛ کانال را ببینید."})
            except BaleError as e:
                steps.append({"ok": False, "text": explain(e)})
                return {"ok": False, "steps": steps}
            return {"ok": True, "steps": steps}

        def _test_sources(self, body):
            cfg = self._merged(body)
            sources = config.active_sources(cfg)

            def work(src):
                try:
                    content = fetcher.fetch_feed(fetcher.new_session(cfg["fetch_proxy"]), src["url"])
                    items = fetcher.parse_feed(content, src)
                    return {"id": src["id"], "ok": True, "count": len(items),
                            "with_image": sum(1 for i in items if i["image_url"])}
                except Exception as e:
                    return {"id": src["id"], "ok": False, "error": fetcher.describe_error(e)}

            with ThreadPoolExecutor(max_workers=8) as pool:
                return {"ok": True, "results": list(pool.map(work, sources))}

        def _detect_chat(self, body):
            cfg = self._merged(body)
            client = BaleClient(cfg["bale_token"], cfg["bale_api_base"], cfg["bale_proxy"], timeout=(10, 25))
            try:
                updates = client.get_updates() or []
            except BaleError as e:
                return {"ok": False, "error": explain(e)}
            found = {}
            for u in updates:
                for key in ("channel_post", "edited_channel_post", "message", "my_chat_member"):
                    chat = (u.get(key) or {}).get("chat")
                    if chat and chat.get("id") is not None:
                        found[chat["id"]] = {"id": chat["id"], "type": chat.get("type", ""),
                                             "title": chat.get("title") or chat.get("username") or ""}
            return {"ok": True, "chats": list(found.values())}

    return Handler


def serve(engine, port):
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(engine))
    server.daemon_threads = True
    return server
