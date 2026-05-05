from __future__ import annotations

import csv
import io
import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .intake_queue import process_uploads
from .bdr_full_flow import qualification_criteria, save_qualification_criteria


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "output"
UPLOAD_DIR = ROOT / "uploads"
STATIC_DIR = ROOT / "web"
UPLOAD_JOBS_FILE = OUTPUT_DIR / "upload-jobs.json"
DEFAULT_PORT = int(os.getenv("PORT", "8787"))


def _load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _save_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def build_overview() -> dict:
    agents = _load_json(OUTPUT_DIR / "agent-status.json", [])
    findings = _load_json(OUTPUT_DIR / "findings.json", [])
    owners = _load_json(OUTPUT_DIR / "owner-summary.json", [])
    lead_samples = _load_json(OUTPUT_DIR / "cnc-lead-review-sample-5.json", [])
    upload_jobs = _load_json(UPLOAD_JOBS_FILE, [])
    intake_queue = _load_json(OUTPUT_DIR / "bdr-intake-queue.json", [])
    batch_review = _load_json(OUTPUT_DIR / "cnc-random-review-200.json", {})
    apollo_preview = _load_json(OUTPUT_DIR / "apollo-enrichment-preview.json", {})
    bdr_batch = _load_json(OUTPUT_DIR / "bdr-batch-results.json", {})
    bdr_history = _load_json(OUTPUT_DIR / "bdr-run-history.json", [])

    severity_counts = Counter((item.get("severity") or "unknown").lower() for item in findings)
    rule_counts = Counter(item.get("rule_id") or "unknown" for item in findings)
    active_agents = sum(1 for row in agents if (row.get("status") or "").lower() == "active")
    queue_by_agent = Counter(item.get("assigned_agent") or "unassigned" for item in intake_queue)
    queue_by_owner = Counter(item.get("assigned_owner") or "unassigned" for item in intake_queue)
    queue_by_priority = Counter(item.get("priority") or "unknown" for item in intake_queue)
    website_status = Counter(item.get("website_status") or "unknown" for item in intake_queue)
    contact_status = Counter(item.get("contact_status") or "unknown" for item in intake_queue)
    apollo_items = apollo_preview.get("items") or []
    apollo_org_hits = sum(1 for item in apollo_items if item.get("apollo_organizations"))
    apollo_people_hits = sum(1 for item in apollo_items if item.get("apollo_people"))

    blockers = []
    if website_status.get("needs_website_recovery", 0):
        blockers.append({
            "title": "Website recovery backlog",
            "detail": f"{website_status.get('needs_website_recovery', 0)} queue items still need a recoverable website before qualification can move fast.",
        })
    if contact_status.get("needs_contact_enrichment", 0):
        blockers.append({
            "title": "Contact enrichment gap",
            "detail": f"{contact_status.get('needs_contact_enrichment', 0)} queue items do not yet have a named contact or email.",
        })
    if queue_by_owner.get("unassigned", 0):
        blockers.append({
            "title": "Territory ownership gaps",
            "detail": f"{queue_by_owner.get('unassigned', 0)} queue items could not be mapped to a visible AE owner.",
        })

    next_actions = [
        {
            "title": "Run the daily Machining hygiene audit",
            "detail": "Generate fresh findings and send the highest-priority cleanup digest to Google Chat.",
            "value": len(findings),
        },
        {
            "title": "Process the CNC qualification queue",
            "detail": "Push high-priority website-ready items through qualification and enrichment first.",
            "value": queue_by_priority.get("high", 0),
        },
        {
            "title": "Clear routing blockers",
            "detail": "Resolve missing websites, contacts, and unmapped owner territories so the BDR agents can move faster.",
            "value": len(blockers),
        },
    ]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "active_agents": active_agents,
            "total_agents": len(agents),
            "findings": len(findings),
            "owners": len(owners),
            "lead_samples": len(lead_samples),
            "uploads": len(upload_jobs),
            "intake_queue": len(intake_queue),
            "medium_findings": severity_counts.get("medium", 0),
            "low_findings": severity_counts.get("low", 0),
            "batch_review_size": batch_review.get("batch_size", 0),
            "batch_archive_candidates": len(batch_review.get("archive_candidates", []) or []),
            "queue_high_priority": queue_by_priority.get("high", 0),
            "queue_owner_assigned": sum(1 for item in intake_queue if item.get("assigned_owner")),
            "queue_needs_website": website_status.get("needs_website_recovery", 0),
            "queue_needs_contact": contact_status.get("needs_contact_enrichment", 0),
            "apollo_preview_scanned": apollo_preview.get("queue_items_scanned", 0),
            "apollo_org_hits": apollo_org_hits,
            "apollo_people_hits": apollo_people_hits,
            "batch_created": bdr_batch.get("created", 0),
            "batch_skips": len(bdr_batch.get("skips") or []),
            "batch_errors": len(bdr_batch.get("errors") or []),
        },
        "agents": agents,
        "owners": owners[:10],
        "findings": findings[:20],
        "lead_samples": lead_samples[:10],
        "rule_counts": dict(rule_counts.most_common(8)),
        "uploads": upload_jobs[:20],
        "intake_queue": intake_queue[:20],
        "queue_by_agent": dict(queue_by_agent),
        "queue_by_owner": dict(queue_by_owner.most_common(8)),
        "queue_by_priority": dict(queue_by_priority),
        "website_status": dict(website_status),
        "contact_status": dict(contact_status),
        "blockers": blockers,
        "next_actions": next_actions,
        "batch_review": {
            "generated_at": batch_review.get("generated_at"),
            "batch_size": batch_review.get("batch_size", 0),
            "score_bands": batch_review.get("score_bands", {}),
            "recommendation_counts": batch_review.get("recommendation_counts", {}),
            "archive_candidates": (batch_review.get("archive_candidates") or [])[:10],
            "good_fits": (batch_review.get("good_fits") or [])[:10],
        },
        "apollo_preview": {
            "preview_generated_at": apollo_preview.get("preview_generated_at"),
            "queue_items_scanned": apollo_preview.get("queue_items_scanned", 0),
            "org_hits": apollo_org_hits,
            "people_hits": apollo_people_hits,
            "items": apollo_items[:10],
        },
        "qualification_criteria": qualification_criteria(),
        "bdr_batch": bdr_batch,
        "bdr_history": bdr_history[:10],
    }


_filename_re = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_filename(name: str) -> str:
    name = (name or "upload.csv").split("/")[-1].split("\\")[-1]
    cleaned = _filename_re.sub("-", name).strip("-.")
    return cleaned or "upload.csv"



def _parse_multipart_csv(content_type: str, body: bytes) -> tuple[str, bytes]:
    match = re.search(r"boundary=([^;]+)", content_type)
    if not match:
        raise ValueError("Missing multipart boundary")
    boundary = match.group(1).strip().strip('"').encode()
    parts = body.split(b"--" + boundary)
    for part in parts:
        if b"Content-Disposition" not in part:
            continue
        if b"name=\"file\"" not in part:
            continue
        headers, _, data = part.partition(b"\r\n\r\n")
        filename_match = re.search(br'filename="([^"]+)"', headers)
        filename = filename_match.group(1).decode("utf-8", errors="ignore") if filename_match else "upload.csv"
        data = data.rstrip(b"\r\n")
        return _safe_filename(filename), data
    raise ValueError("No CSV file found in upload")



def _summarize_csv(name: str, content: bytes, stored_path: Path) -> dict:
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    headers = reader.fieldnames or []
    sample_rows = []
    row_count = 0
    for row in reader:
        row_count += 1
        if len(sample_rows) < 3:
            sample_rows.append(row)
    now = datetime.now(timezone.utc)
    return {
        "id": now.strftime("%Y%m%d%H%M%S"),
        "filename": name,
        "stored_path": str(stored_path.relative_to(ROOT)),
        "uploaded_at": now.isoformat(),
        "row_count": row_count,
        "headers": headers,
        "sample_rows": sample_rows,
        "status": "queued",
        "notes": "Ready for AI BDR ingestion pipeline",
    }


INDEX_HTML = (STATIC_DIR / "index.html").read_text(encoding="utf-8") if (STATIC_DIR / "index.html").exists() else ""


class Handler(BaseHTTPRequestHandler):
    server_version = "AMFGSalesDashboard/0.1"

    def _send_json(self, payload, status=HTTPStatus.OK):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_html(self, html: str, status=HTTPStatus.OK):
        data = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_not_found(self):
        self._send_json({"error": "not_found"}, status=HTTPStatus.NOT_FOUND)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            self._send_html(INDEX_HTML)
            return
        if parsed.path == "/health":
            self._send_json({"ok": True, "service": "amfg-sales-dashboard"})
            return
        if parsed.path == "/api/overview":
            self._send_json(build_overview())
            return
        if parsed.path == "/api/uploads":
            self._send_json(_load_json(UPLOAD_JOBS_FILE, []))
            return
        if parsed.path == "/api/intake-queue":
            self._send_json(_load_json(OUTPUT_DIR / "bdr-intake-queue.json", []))
            return
        if parsed.path == "/api/batch-review":
            self._send_json(_load_json(OUTPUT_DIR / "cnc-random-review-200.json", {}))
            return
        if parsed.path == "/api/apollo-preview":
            self._send_json(_load_json(OUTPUT_DIR / "apollo-enrichment-preview.json", {}))
            return
        if parsed.path == "/api/bdr-batch-results":
            self._send_json(_load_json(OUTPUT_DIR / "bdr-batch-results.json", {}))
            return
        if parsed.path == "/api/bdr-run-history":
            self._send_json(_load_json(OUTPUT_DIR / "bdr-run-history.json", []))
            return
        self._send_not_found()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/upload-csv":
            content_length = int(self.headers.get("Content-Length", "0") or 0)
            content_type = self.headers.get("Content-Type", "")
            body = self.rfile.read(content_length)

            try:
                filename, content = _parse_multipart_csv(content_type, body)
                timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
                UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
                stored_path = UPLOAD_DIR / f"{timestamp}-{filename}"
                stored_path.write_bytes(content)

                summary = _summarize_csv(filename, content, stored_path)
                jobs = _load_json(UPLOAD_JOBS_FILE, [])
                jobs.insert(0, summary)
                _save_json(UPLOAD_JOBS_FILE, jobs)
                self._send_json(summary, status=HTTPStatus.CREATED)
            except Exception as exc:
                self._send_json({"error": "upload_failed", "detail": escape(str(exc))}, status=HTTPStatus.BAD_REQUEST)
            return

        if parsed.path == "/api/process-uploads":
            try:
                result = process_uploads()
                self._send_json(result, status=HTTPStatus.OK)
            except Exception as exc:
                self._send_json({"error": "processing_failed", "detail": escape(str(exc))}, status=HTTPStatus.BAD_REQUEST)
            return

        if parsed.path == "/api/qualification-criteria":
            content_length = int(self.headers.get("Content-Length", "0") or 0)
            body = self.rfile.read(content_length)
            try:
                payload = json.loads(body.decode("utf-8"))
                saved = save_qualification_criteria(payload)
                self._send_json(saved)
            except Exception as exc:
                self._send_json({"error": "criteria_update_failed", "detail": escape(str(exc))}, status=HTTPStatus.BAD_REQUEST)
            return

        self._send_not_found()


    def do_DELETE(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/uploads":
            self._send_not_found()
            return

        query = parse_qs(parsed.query)
        upload_id = (query.get("id") or [""])[0]
        if not upload_id:
            self._send_json({"error": "missing_id"}, status=HTTPStatus.BAD_REQUEST)
            return

        jobs = _load_json(UPLOAD_JOBS_FILE, [])
        kept = []
        deleted = None
        for job in jobs:
            if str(job.get("id")) == upload_id and deleted is None:
                deleted = job
                continue
            kept.append(job)

        if not deleted:
            self._send_json({"error": "not_found"}, status=HTTPStatus.NOT_FOUND)
            return

        stored_path = ROOT / str(deleted.get("stored_path") or "")
        if stored_path.exists():
            stored_path.unlink()

        queue = _load_json(OUTPUT_DIR / "bdr-intake-queue.json", [])
        queue = [item for item in queue if str(item.get("source_upload_id")) != upload_id]
        _save_json(OUTPUT_DIR / "bdr-intake-queue.json", queue)
        _save_json(UPLOAD_JOBS_FILE, kept)
        self._send_json({"deleted": upload_id, "remaining_uploads": len(kept), "remaining_queue": len(queue)})


def main(port: int = DEFAULT_PORT) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"AMFG sales dashboard running on http://0.0.0.0:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
