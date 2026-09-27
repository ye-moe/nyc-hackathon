"""Human verification of labels. Agents pre-label; a person has the final say.

    python -m eval.review --by "Myra"      then open http://localhost:4321

Shows each listing with its current label and both blind agent labels.
Disagreements come first. Keys: 1/2/3 pick a label, Enter accepts the
suggested one, Backspace goes back (held keys are ignored). Every save writes
`label`, `verified_by`, and `verified_at` straight into the source .jsonl.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
FILES = [p for p in ("data/labeled/dev.jsonl", "data/labeled/holdout.jsonl", "data/labeled/holdout_v2.jsonl") if (ROOT / p).exists()]
AGENTS = {"A": "data/labeled/agent/labeler_A.jsonl", "B": "data/labeled/agent/labeler_B.jsonl"}
LABELS = {"violation", "needs_review", "no_issue_found"}
PAGE = (Path(__file__).with_name("review_page.html")).read_text()


def read_jsonl(rel: str) -> list:
    p = ROOT / rel
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []


class Save(BaseModel):
    file: str
    id: str
    label: str


def build_app(by: str) -> FastAPI:
    app = FastAPI()

    @app.get("/", response_class=HTMLResponse)
    def page():
        return PAGE.replace("__BY__", json.dumps(by))

    @app.get("/api/queue")
    def queue():
        agent: dict = {}
        for k, p in AGENTS.items():
            for r in read_jsonl(p):
                agent.setdefault(r["id"], {})[k] = r
        items = []
        for f in FILES:
            for r in read_jsonl(f):
                a = agent.get(r["id"], {})
                votes = {v for v in (r.get("label"), a.get("A", {}).get("label"), a.get("B", {}).get("label")) if v}
                items.append({"file": f, "row": r, "A": a.get("A"), "B": a.get("B"), "disagree": len(votes) > 1,
                              "minConf": min(a.get("A", {}).get("confidence", 1), a.get("B", {}).get("confidence", 1))})
        # Unverified first; among those, disagreements, then least-confident agent calls.
        items.sort(key=lambda x: (bool(x["row"].get("verified_by")), not x["disagree"], x["minConf"]))
        return items

    @app.post("/api/save")
    def save(s: Save):
        if s.file not in FILES or s.label not in LABELS:
            raise HTTPException(400, "bad request")
        rows = read_jsonl(s.file)
        r = next((x for x in rows if x["id"] == s.id), None)
        if not r:
            raise HTTPException(400, "unknown id")
        if r["label"] != s.label:
            r["previous_label"] = r["label"]
        r.update(label=s.label, verified_by=by, verified_at=datetime.now(timezone.utc).isoformat())
        (ROOT / s.file).write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rows))
        return {"ok": True}

    return app


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--by", required=True, help="your name, recorded on every label you verify")
    a = ap.parse_args()
    port = int(os.environ.get("PORT", 4321))
    print(f"label review for {a.by}: http://localhost:{port}")
    uvicorn.run(build_app(a.by), host="127.0.0.1", port=port, log_level="warning")
