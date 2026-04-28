from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable

from .models import Finding


SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_type TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    notes_json TEXT
);

CREATE TABLE IF NOT EXISTS findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    rule_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    owner_id INTEGER,
    severity TEXT NOT NULL,
    confidence REAL NOT NULL,
    summary TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    suggested_action TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(run_id) REFERENCES runs(id)
);
"""


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(SCHEMA)
        return conn

    def insert_run(self, run_type: str, notes: dict | None = None) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO runs (run_type, notes_json) VALUES (?, ?)",
                (run_type, json.dumps(notes or {})),
            )
            conn.commit()
            return int(cur.lastrowid)

    def insert_findings(self, run_id: int, findings: Iterable[Finding]) -> None:
        rows = [
            (
                run_id,
                finding.rule_id,
                finding.entity_type,
                finding.entity_id,
                finding.owner_id,
                finding.severity,
                finding.confidence,
                finding.summary,
                json.dumps(finding.evidence),
                finding.suggested_action,
            )
            for finding in findings
        ]
        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO findings (
                    run_id, rule_id, entity_type, entity_id, owner_id, severity,
                    confidence, summary, evidence_json, suggested_action
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            conn.commit()
