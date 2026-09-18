"""Vercel serverless entrypoint — exposes the Flask app.

Vercel rewrites every path to /api/index/<original>, so this middleware
strips the /api/index prefix and restores the original path for Flask.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app as flask_app  # noqa: E402

PREFIX = "/api/index"


class StripPrefix:
    def __init__(self, wrapped):
        self.wrapped = wrapped

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "") or "/"
        orig = path
        if path == PREFIX:
            path = "/"
        elif path.startswith(PREFIX + "/"):
            path = path[len(PREFIX):]
        environ["PATH_INFO"] = path
        environ["SCRIPT_NAME"] = ""

        def hooked_start(status, headers, exc_info=None):
            headers.append(("X-Dbg-Orig-Path", orig))
            headers.append(("X-Dbg-New-Path", path))
            return start_response(status, headers, exc_info)

        return self.wrapped(environ, hooked_start)


flask_app.wsgi_app = StripPrefix(flask_app.wsgi_app)

# Vercel looks for `app` in api/index.py
app = flask_app
