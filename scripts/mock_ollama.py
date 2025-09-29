#!/usr/bin/env python3
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse


class MockOllamaHandler(BaseHTTPRequestHandler):
    server_version = "MockOllama/0.1"

    def _send(self, code=200, body=b"", content_type="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            self._send(200, b"ok", content_type="text/plain")
            return
        if path == "/api/tags":
            body = json.dumps({"models": [{"name": "qwen2.5:0.5b"}]}).encode()
            self._send(200, body)
            return
        self._send(404, b"{}")

    def do_POST(self):
        path = urlparse(self.path).path
        if path != "/api/generate":
            self._send(404, b"{}")
            return
        length = int(self.headers.get("Content-Length", "0"))
        data = self.rfile.read(length) if length else b"{}"
        try:
            req = json.loads(data.decode() or "{}")
        except Exception:
            req = {}
        prompt = req.get("prompt", "Base domain: Mock\nCount: 3")
        stream = bool(req.get("stream"))
        # Try to extract count from prompt
        count = 3
        for line in str(prompt).splitlines():
            if line.lower().startswith("count:"):
                try:
                    count = int(line.split(":", 1)[1].strip())
                except Exception:
                    pass
        names = [f"MockName{i+1}" for i in range(max(1, count))]
        if stream:
            # Return newline-delimited JSON objects with response chunks
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()
            for i, name in enumerate(names):
                obj = {"response": name + ("\n" if i < len(names) - 1 else ""), "done": False}
                self.wfile.write((json.dumps(obj) + "\n").encode())
            done = {"done": True, "eval_count": 10, "eval_duration": 5_000_000}
            self.wfile.write((json.dumps(done) + "\n").encode())
            return
        else:
            body = {
                "response": "\n".join(names),
                "eval_count": 10,
                "eval_duration": 5_000_000,
            }
            self._send(200, json.dumps(body).encode())


def run(addr="127.0.0.1", port=11434):
    httpd = HTTPServer((addr, port), MockOllamaHandler)
    print(f"Mock Ollama listening on http://{addr}:{port}")
    httpd.serve_forever()


if __name__ == "__main__":
    run()

