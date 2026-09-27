"""Open a listing URL with jev-ultrafast, expand it, and return its text + screenshot.

    uv run --project $JEV_DIR --env-file $JEV_DIR/.env python scanner/jev/fetch_listing.py <url>

Prints one JSON object to stdout. Read-only by construction: we drive jev's
predict/act steps ourselves and refuse any action that could contact a
landlord (typing into a field, or clicking contact/apply/message/call/etc.).
The goal prompt asks for the same thing, but the guard doesn't rely on the
model obeying it.
"""
import json
import re
import sys
import time

import os

import jev_ultrafast.model as _jev_model
from jev_ultrafast import Agent
from jev_ultrafast.browser import StalePage

# TypeSafe's hosted API is paused. OpenJev (github.com/razorback16/openjev)
# serves the same /v1/systemone API with an open model, hosted free at Codiv or
# self-hosted. jev-ultrafast hardcodes TypeSafe's URL, so redirect it here
# instead of forking jev:
#   TYPESAFE_BASE_URL=https://api.codiv.ai   TYPESAFE_API_KEY=sk-codiv-...   TYPESAFE_MODEL=openjev-latest
_BASE = os.environ.get("TYPESAFE_BASE_URL", "").rstrip("/")
if _BASE:
    _post_json = _jev_model.post_json

    def _redirected(url, key, body):
        return _post_json(url.replace("https://api.typesafe.ai", _BASE, 1), key, body)

    _jev_model.post_json = _redirected

GOAL = """Reveal the complete rental listing description on this page.
Close cookie banners, pop-ups, and sign-up prompts. Click "See more", "Read more",
"Show full description", or similar to expand truncated text. Scroll if the description is below.
Never contact anyone, never send a message, never apply, never fill or submit any form, never log in.
DONE as soon as the full listing description is visible."""

MAX_ACTIONS = 12

# Anything that could reach a landlord or create an account. Checked against
# the element's label before every click.
UNSAFE_LABEL = re.compile(
    r"contact|message|send|reply|apply|application|email|e-mail|call|phone|text\s+(?:the\s+)?(?:owner|landlord|agent)|"
    r"schedule|tour|request|book|submit|sign\s*(?:in|up)|log\s*in|register|inquir|ask\s+a\s+question|chat|whatsapp",
    re.IGNORECASE,
)


def unsafe(action):
    if action["kind"] == "fill":
        return "typing into fields is disabled"
    if action["kind"] == "click" and UNSAFE_LABEL.search(action.get("label") or ""):
        return f"click on '{action['label']}' could contact the landlord"
    return None


def fetch(url):
    started = time.perf_counter()
    steps, stopped_reason = [], None
    with Agent(url, GOAL, screenshots=True) as agent:
        state = agent.state
        for _ in range(MAX_ACTIONS * 2):
            try:
                agent.command("predict", {})
                choice = state["decision"]["choice"]
                if choice in {"DONE", "BLOCKED"}:
                    agent.command("act", {"fingerprint": state["page"]["fingerprint"]})
                    stopped_reason = choice.lower()
                    break
                action = next(a for a in state["page"]["actions"] if a["id"] == choice)
                reason = unsafe(action)
                if reason:
                    stopped_reason = f"guardrail: {reason}"
                    break
                agent.command("act", {"fingerprint": state["page"]["fingerprint"]})
                steps.append({"kind": action["kind"], "label": action.get("label")})
                if len(steps) >= MAX_ACTIONS:
                    stopped_reason = "action budget"
                    break
            except StalePage:
                state["decision"] = None
                state["page"] = agent.browser.observe(screenshot=True)
            except ValueError as e:     # jev's own budget/"run has stopped" errors
                stopped_reason = str(e)
                break

        page = state["page"]
        try:
            # jev's snapshot caps text at 6000 chars; read the whole body for analysis.
            full_text = agent.browser.evaluate("document.body.innerText") or page.get("text", "")
        except Exception:
            full_text = page.get("text", "")
        return {
            "ok": True,
            "url": page.get("url", url),
            "title": page.get("title"),
            "text": full_text,
            "screenshot_b64": page.get("screenshot"),   # JPEG, base64
            "screenshot_media_type": "image/jpeg",
            "steps": steps,
            "stopped": stopped_reason,
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
        }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(json.dumps({"ok": False, "error": "usage: fetch_listing.py <url>"}))
        sys.exit(2)
    try:
        print(json.dumps(fetch(sys.argv[1])))
    except Exception as e:  # the caller falls back to a plain HTTP fetch
        print(json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"}))
        sys.exit(1)
