#!/usr/bin/env python3
"""Tiny /model_stat HTTP service using os.stat (no Salad /download).

Modes:
  --serve-only --port 8090     # just /model_stat (and /healthz)
  --proxy-upstream HOST:PORT   # listen on --port (default 3000), handle /model_stat,
                               # proxy all other traffic to upstream (comfyui-api)

This is the mechanism exposed on the Salad container public port when used as
entrypoint wrapper: upstream comfyui-api binds 127.0.0.1:3001; this process
binds 0.0.0.0:3000.
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

# Allow import when copied next to this file inside the image
sys.path.insert(0, str(Path(__file__).resolve().parent))
from model_stat_lib import REQUIRED_SPECS, stat_all  # noqa: E402


def _json_bytes(obj: Any) -> bytes:
    return json.dumps(obj, separators=(",", ":"), default=str).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    upstream_host = "127.0.0.1"
    upstream_port = 3001
    proxy = False
    models_root: Path | None = None

    def log_message(self, fmt: str, *args) -> None:  # quieter
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, code: int, body: bytes, content_type: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path or "/"
        if path in ("/model_stat", "/model_stat/"):
            try:
                result = stat_all(root=self.models_root)
                code = 200 if result.get("ok") else 409
                self._send(code, _json_bytes(result))
            except Exception as e:
                self._send(500, _json_bytes({"ok": False, "error": str(e), "trace": traceback.format_exc()[-500:]}))
            return
        if path in ("/healthz", "/model_stat/healthz"):
            self._send(200, _json_bytes({"ok": True, "service": "model_stat"}))
            return
        if self.proxy:
            self._proxy()
            return
        self._send(404, _json_bytes({"error": "not_found", "path": path}))

    def do_POST(self) -> None:  # noqa: N802
        if self.proxy:
            self._proxy()
            return
        self._send(405, _json_bytes({"error": "method_not_allowed"}))

    def do_PUT(self) -> None:  # noqa: N802
        if self.proxy:
            self._proxy()
            return
        self._send(405, _json_bytes({"error": "method_not_allowed"}))

    def do_DELETE(self) -> None:  # noqa: N802
        if self.proxy:
            self._proxy()
            return
        self._send(405, _json_bytes({"error": "method_not_allowed"}))

    def do_PATCH(self) -> None:  # noqa: N802
        if self.proxy:
            self._proxy()
            return
        self._send(405, _json_bytes({"error": "method_not_allowed"}))

    def do_HEAD(self) -> None:  # noqa: N802
        if self.proxy:
            self._proxy()
            return
        self._send(405, b"")

    def do_OPTIONS(self) -> None:  # noqa: N802
        if self.proxy:
            self._proxy()
            return
        self._send(204, b"")

    def _proxy(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        try:
            conn = HTTPConnection(self.upstream_host, self.upstream_port, timeout=600)
            headers = {k: v for k, v in self.headers.items() if k.lower() != "host"}
            conn.request(self.command, self.path, body=body, headers=headers)
            resp = conn.getresponse()
            data = resp.read()
            self.send_response(resp.status)
            for k, v in resp.getheaders():
                if k.lower() in ("transfer-encoding", "connection", "content-encoding"):
                    continue
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            conn.close()
        except Exception as e:
            self._send(502, _json_bytes({"error": "upstream_unreachable", "detail": str(e)[:300]}))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="model_stat os.stat HTTP service")
    ap.add_argument("--port", type=int, default=3000)
    ap.add_argument("--bind", default="0.0.0.0")
    ap.add_argument("--proxy-upstream", default="", help="host:port of comfyui-api")
    ap.add_argument("--serve-only", action="store_true")
    ap.add_argument("--models-root", default="", help="test remap root containing models/...")
    args = ap.parse_args(argv)

    Handler.proxy = bool(args.proxy_upstream) and not args.serve_only
    if args.proxy_upstream:
        host, _, port_s = args.proxy_upstream.partition(":")
        Handler.upstream_host = host or "127.0.0.1"
        Handler.upstream_port = int(port_s or "3001")
    Handler.models_root = Path(args.models_root) if args.models_root else None

    httpd = ThreadingHTTPServer((args.bind, args.port), Handler)
    mode = "proxy+stat" if Handler.proxy else "serve-only"
    print(
        f"model_stat listening on {args.bind}:{args.port} mode={mode} "
        f"specs={len(REQUIRED_SPECS)} upstream={Handler.upstream_host}:{Handler.upstream_port}",
        flush=True,
    )
    httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
