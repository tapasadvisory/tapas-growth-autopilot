"""Approval workflow + tamper-evident audit log.

This is a gate and a record only: nothing in this module publishes,
posts or sends anything. Every approval event appends an audit_logs row
whose tamper_proof_checksum chains to the previous row:

    sha256(previous_checksum + timestamp + event_type + actor
           + target_entity + outcome + details_json)

The genesis previous checksum is 64 zeros. Changing any earlier row
breaks every later checksum.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any

GENESIS_CHECKSUM = "0" * 64


def write_audit_log(
    conn: sqlite3.Connection,
    *,
    timestamp: str,
    event_type: str,
    actor: str,
    target_entity: str,
    outcome: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    details_json = json.dumps(details or {}, ensure_ascii=False, sort_keys=True)
    row = conn.execute(
        "SELECT tamper_proof_checksum FROM audit_logs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    previous = row["tamper_proof_checksum"] if row else GENESIS_CHECKSUM
    payload = previous + timestamp + event_type + actor + target_entity + outcome + details_json
    checksum = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    cursor = conn.execute(
        """INSERT INTO audit_logs(timestamp,event_type,actor,target_entity,outcome,details_json,tamper_proof_checksum)
           VALUES(?,?,?,?,?,?,?)""",
        (timestamp, event_type, actor, target_entity, outcome, details_json, checksum),
    )
    return {
        "id": cursor.lastrowid,
        "timestamp": timestamp,
        "event_type": event_type,
        "actor": actor,
        "target_entity": target_entity,
        "outcome": outcome,
        "details": details or {},
        "tamper_proof_checksum": checksum,
    }
