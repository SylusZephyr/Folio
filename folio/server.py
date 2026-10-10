"""Local web server behind the Folio window. Listens on 127.0.0.1 only; files never leave this computer."""

from __future__ import annotations

import json
import mimetypes
import os
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from . import __version__
from .core import MergeError, Part, merge, page_count, parse_ranges

PORT = 8765
WEB = Path(__file__).parent / "web"
WORK = Path(tempfile.gettempdir()) / "folio"
ID = re.compile(r"^[0-9a-f]{32}$")
CHUNK = 1 << 20


class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.uploads: dict[str, dict] = {}  # id -> {name, pages}
        self.results: dict[str, str] = {}  # id -> download filename
        self.active = 0  # requests in progress (uploads, merges): never shut down mid-work
        self.last_ping = time.monotonic()
        self.bye_at: float | None = None


def make_handler(state: State, port: int):
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class Handler(BaseHTTPRequestHandler):
        server_version = f"Folio/{__version__}"

        def log_message(self, *a):
            pass

        def _allowed(self) -> bool:
            # only this app's own page may drive the server: blocks other websites and DNS rebinding
            if self.headers.get("Host") not in hosts:
                return False
            origin = self.headers.get("Origin")
            return origin is None or origin.split("://", 1)[-1] in hosts

        def _json(self, code: int, obj) -> None:
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _body_json(self):
            n = int(self.headers.get("Content-Length") or 0)
            try:
                return json.loads(self.rfile.read(n) or b"null")
            except ValueError:
                return None

        def _send_file(self, path: Path, ctype: str, disposition: str | None = None) -> None:
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(path.stat().st_size))
            self.send_header("X-Content-Type-Options", "nosniff")
            if disposition:
                self.send_header("Content-Disposition", disposition)
            self.end_headers()
            with open(path, "rb") as f:
                shutil.copyfileobj(f, self.wfile, CHUNK)

        # ---- GET: the page, its assets, merged results ----
        def do_GET(self):
            if not self._allowed():
                return self.send_error(403)
            path = urlparse(self.path).path
            if path == "/":
                return self._send_file(WEB / "index.html", "text/html; charset=utf-8")
            if path.startswith("/static/"):
                f = (WEB / path[len("/static/"):]).resolve()
                if f.parent == WEB.resolve() and f.is_file():
                    ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
                    if ctype.startswith("text/") or ctype.endswith("javascript"):
                        ctype += "; charset=utf-8"
                    return self._send_file(f, ctype)
            m = re.fullmatch(r"/api/file/([0-9a-f]{32})", path)
            if m and m[1] in state.results:
                name = state.results[m[1]]
                kind = "attachment" if "download" in parse_qs(urlparse(self.path).query) else "inline"
                return self._send_file(WORK / f"out_{m[1]}.pdf", "application/pdf",
                                       f"{kind}; filename*=UTF-8''{quote(name)}")
            self.send_error(404)

        # ---- POST: the API ----
        def do_POST(self):
            if not self._allowed():
                return self.send_error(403)
            url = urlparse(self.path)
            route = {
                "/api/upload": self.upload, "/api/merge": self.merge, "/api/discard": self.discard,
                "/api/ping": self.ping, "/api/bye": self.bye, "/api/quit": self.quit,
            }.get(url.path)
            if not route:
                return self.send_error(404)
            with state.lock:
                state.active += 1
            try:
                route(url)
            finally:
                with state.lock:
                    state.active -= 1

        def upload(self, url):
            fid = uuid.uuid4().hex
            name = parse_qs(url.query).get("name", ["file.pdf"])[0][:255]
            dst = WORK / f"in_{fid}.pdf"
            left = int(self.headers.get("Content-Length") or 0)
            with open(dst, "wb") as f:  # streamed to disk: a file is never held in memory whole
                while left:
                    buf = self.rfile.read(min(CHUNK, left))
                    if not buf:
                        break
                    f.write(buf)
                    left -= len(buf)
            if left:
                dst.unlink(missing_ok=True)
                return self._json(400, {"error": "upload was interrupted"})
            try:
                pages = page_count(dst, name)
            except MergeError as e:
                dst.unlink(missing_ok=True)
                return self._json(422, {"error": str(e)})
            state.uploads[fid] = {"name": name, "pages": pages}
            self._json(200, {"id": fid, "pages": pages})

        def merge(self, url):
            req = self._body_json()
            if not isinstance(req, dict) or not isinstance(req.get("items"), list) or not req["items"]:
                return self._json(400, {"error": "Add some PDFs first."})
            parts = []
            for i, item in enumerate(req["items"], 1):
                fid = item.get("id") if isinstance(item, dict) else None
                info = state.uploads.get(fid) if isinstance(fid, str) else None
                if not info:
                    return self._json(400, {"error": f"File {i} is no longer available. Remove it and add it again."})
                title = re.sub(r"\.pdf$", "", info["name"], flags=re.I)
                try:
                    pages = parse_ranges(str(item.get("range") or ""), info["pages"])
                except MergeError as e:
                    return self._json(400, {"error": f"{info['name']}: {e}"})
                parts.append(Part(WORK / f"in_{fid}.pdf", title, pages, info["pages"]))

            name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", str(req.get("name") or "")).strip(" .") or "Merged"
            if not name.lower().endswith(".pdf"):
                name += ".pdf"
            rid = uuid.uuid4().hex
            out = WORK / f"out_{rid}.pdf"
            start = time.perf_counter()
            try:
                pages = merge(parts, out, bookmarks=bool(req.get("bookmarks", True)), title=name[:-4])
            except MergeError as e:
                return self._json(422, {"error": str(e)})
            state.results[rid] = name
            self._json(200, {"id": rid, "name": name, "pages": pages, "size": out.stat().st_size,
                             "seconds": round(time.perf_counter() - start, 2)})

        def discard(self, url):
            ids = self._body_json()
            for fid in ids if isinstance(ids, list) else []:
                if isinstance(fid, str) and ID.match(fid) and state.uploads.pop(fid, None):
                    (WORK / f"in_{fid}.pdf").unlink(missing_ok=True)
            self._json(200, {})

        def ping(self, url):
            state.last_ping, state.bye_at = time.monotonic(), None
            self._json(200, {"version": __version__})

        def bye(self, url):  # window closing (or reloading: the reload's ping cancels this)
            state.bye_at = time.monotonic()
            self._json(200, {})

        def quit(self, url):
            self._json(200, {})
            threading.Thread(target=self.server.shutdown, daemon=True).start()

    return Handler


def _watchdog(server: ThreadingHTTPServer, state: State) -> None:
    """Close the app when its window is gone: shortly after the window says goodbye, or after a
    long silence (background windows can be throttled to ~1 ping a minute, hence the generous limit)."""
    while True:
        time.sleep(2)
        now = time.monotonic()
        closed = state.bye_at is not None and now - state.bye_at > 8
        silent = now - state.last_ping > 300
        if state.active == 0 and (closed or silent):
            server.shutdown()
            return


def open_window(url: str) -> None:
    """Open as a standalone app window (Edge/Chrome app mode); fall back to a normal browser tab."""
    candidates = [
        Path(os.environ.get(v, "")) / sub
        for v in ("ProgramFiles(x86)", "ProgramFiles", "LocalAppData")
        for sub in (r"Microsoft\Edge\Application\msedge.exe", r"Google\Chrome\Application\chrome.exe")
    ] + [Path(p) for p in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                           "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/microsoft-edge")]
    for exe in candidates:
        if exe.is_file():
            subprocess.Popen([str(exe), f"--app={url}", "--window-size=1340,880"])
            return
    webbrowser.open(url)


def serve(port: int = PORT, mode: str = "app") -> None:
    """mode: "app" = own window, closes with it; "browser" = normal tab; "headless" = server only."""
    url = f"http://127.0.0.1:{port}/"
    with socket.socket() as s:
        if s.connect_ex(("127.0.0.1", port)) == 0:  # already running: just bring up a window
            if mode == "app":
                open_window(url)
            elif mode == "browser":
                webbrowser.open(url)
            return
    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True)
    state = State()
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(state, port))
    server.daemon_threads = True
    if mode == "app":
        threading.Thread(target=_watchdog, args=(server, state), daemon=True).start()
        open_window(url)
    else:
        print(f"Folio is running at {url}  (Ctrl+C to stop)", flush=True)
        if mode == "browser":
            webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        shutil.rmtree(WORK, ignore_errors=True)  # nothing is left behind in temp
