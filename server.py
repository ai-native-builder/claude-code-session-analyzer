#!/usr/bin/env python3
"""
Combined static file server + Anthropic CORS proxy.
Fixes "Failed to fetch" when calling api.anthropic.com from a local HTTP origin.

Usage:
    python3 server.py          # serves on http://localhost:8080
    python3 server.py 3000     # custom port
"""

import http.server
import urllib.request
import urllib.error
import sys
import os

PROXY_PATH = '/api/anthropic'
ANTHROPIC_URL = 'https://api.anthropic.com/v1/messages'
FORWARDED_HEADERS = ('x-api-key', 'anthropic-version', 'content-type')


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_OPTIONS(self):
        if self.path == PROXY_PATH:
            self.send_response(200)
            self._cors_headers()
            self.end_headers()

    def do_POST(self):
        if self.path != PROXY_PATH:
            self.send_error(404)
            return
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length)
        headers = {h: self.headers[h] for h in FORWARDED_HEADERS if self.headers.get(h)}
        req = urllib.request.Request(ANTHROPIC_URL, body, headers)
        try:
            resp = urllib.request.urlopen(req)
            self._proxy_response(200, resp.read())
        except urllib.error.HTTPError as e:
            self._proxy_response(e.code, e.read())

    def _proxy_response(self, status, data):
        self.send_response(status)
        self._cors_headers()
        self.send_header('content-type', 'application/json')
        self.end_headers()
        self.wfile.write(data)

    def _cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers',
                         'content-type, x-api-key, anthropic-version, anthropic-dangerous-allow-browser')

    def log_message(self, fmt, *args):
        pass  # suppress per-request noise


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    print(f'Serving on http://localhost:{port}')
    http.server.HTTPServer(('127.0.0.1', port), Handler).serve_forever()
