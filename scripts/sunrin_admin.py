#!/usr/bin/env python3
"""Zero-dependency local admin server for Sunrin whiteboard projects."""
from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
ADMIN = ROOT / "sunrin" / "admin"
sys.path.insert(0, str(ROOT / "scripts"))
from sunrin_build_project import TEMPLATES, build_project, load_brand, load_template  # noqa: E402


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ADMIN), **kwargs)

    def send_json(self, data: object, status: int = 200) -> None:
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/config":
            templates = []
            for file in sorted(TEMPLATES.glob("*.json")):
                data = json.loads(file.read_text(encoding="utf-8"))
                templates.append({"id": file.stem, "name": data.get("name", file.stem)})
            return self.send_json({"brand": load_brand(), "templates": templates})
        if path.startswith("/api/template/"):
            try:
                template_id = path.rsplit("/", 1)[-1]
                return self.send_json(load_template(template_id))
            except Exception as exc:
                return self.send_json({"error": str(exc)}, 404)
        return super().do_GET()

    def do_POST(self):
        if urlparse(self.path).path != "/api/projects":
            return self.send_json({"error": "Not found"}, 404)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            out = build_project(
                title=payload.get("title", "화이트보드 영상"),
                duration=float(payload.get("duration", 30)),
                aspect=payload.get("aspect", "16:9"),
                project_id=payload.get("project") or None,
                template_id=payload.get("template", "custom"),
                scenes=payload.get("scenes"),
            )
            rel = out.relative_to(ROOT).as_posix()
            return self.send_json({"ok": True, "projectPath": rel, "manifest": f"{rel}/project.json", "srt": f"{rel}/script.srt"})
        except Exception as exc:
            return self.send_json({"error": str(exc)}, 400)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    url = f"http://{args.host}:{args.port}"
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"SUNRIN_ADMIN={url}")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
