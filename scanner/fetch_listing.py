"""Turn a listing URL into text (+ screenshot) for the engine.

Primary: jev-ultrafast browser agent (handles JavaScript pages, "See more",
pop-ups), run through scanner/jev/fetch_listing.py. jev needs Python 3.12+, so
it runs as a subprocess via `uv` in its own environment.
Fallback: plain HTTP fetch + tag stripping, so a missing key or a jev failure
never breaks the agent or the demo."""
from __future__ import annotations

import html as _html
import json
import os
import re
import subprocess
import time
from pathlib import Path

import httpx

import core  # noqa: F401  loads our .env, so TYPESAFE_* / JEV_DIR reach the jev subprocess

SIDECAR = Path(__file__).resolve().parent / "jev" / "fetch_listing.py"


def fetch_listing(url: str) -> dict:
    jev_dir = os.environ.get("JEV_DIR")
    jev_error = None
    if jev_dir:
        try:
            return _via_jev(url, jev_dir)
        except Exception as e:
            jev_error = str(e)
    else:
        jev_error = "JEV_DIR not set"
    return {**_via_http(url), "jev_error": jev_error}


def _via_jev(url: str, jev_dir: str) -> dict:
    timeout = float(os.environ.get("JEV_TIMEOUT_MS", 45000)) / 1000
    jev_env = Path(jev_dir) / ".env"
    cmd = ["uv", "run", "--project", jev_dir, *(["--env-file", str(jev_env)] if jev_env.exists() else []), "python", str(SIDECAR), url]
    # Our environment (incl. TYPESAFE_BASE_URL / TYPESAFE_API_KEY from .env) is inherited by the subprocess.
    env = dict(os.environ)
    port = os.environ.get("JEV_CHROME_PORT")
    if port:
        # Use a dedicated Chrome (separate empty profile) instead of the user's everyday
        # browser: browser-harness connects to whatever websocket BU_CDP_WS names.
        env["BU_CDP_WS"] = httpx.get(f"http://127.0.0.1:{port}/json/version", timeout=3).json()["webSocketDebuggerUrl"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
    last = (proc.stdout.strip().splitlines() or ["{}"])[-1]
    try:
        r = json.loads(last)
    except json.JSONDecodeError:
        r = {}
    if not r.get("ok"):
        err_tail = (proc.stderr.strip().splitlines() or [""])[-1][:200]
        raise RuntimeError(r.get("error") or f"jev exited {proc.returncode}: {err_tail}")
    return {"url": r["url"], "title": r.get("title"), "text": r["text"], "screenshot_b64": r.get("screenshot_b64"),
            "screenshot_media_type": r.get("screenshot_media_type"), "via": "jev", "steps": r.get("steps"),
            "stopped": r.get("stopped"), "elapsed_ms": r.get("elapsed_ms")}


def _via_http(url: str) -> dict:
    t0 = time.perf_counter()
    res = httpx.get(url, headers={"user-agent": "Mozilla/5.0 (voucher-detector research; read-only)"}, timeout=15, follow_redirects=True)
    page = res.text
    title = re.search(r"<title[^>]*>([^<]*)</title>", page, re.I)
    text = re.sub(r"<(script|style|noscript)[\s\S]*?</\1>", " ", page, flags=re.I)
    text = re.sub(r"<br\s*/?>|</(p|div|li|h\d)>", "\n", text, flags=re.I)
    text = _html.unescape(re.sub(r"<[^>]+>", " ", text))
    text = re.sub(r"\n\s*\n+", "\n", re.sub(r"[ \t]+", " ", text)).strip()
    return {"url": str(res.url), "title": title.group(1).strip() if title else None, "text": text, "via": "http",
            "elapsed_ms": round((time.perf_counter() - t0) * 1000)}
