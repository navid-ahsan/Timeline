import json
import os
import psycopg2
from datetime import datetime, timezone
from dataclasses import dataclass, asdict


@dataclass
class AuditEntry:
    patient_id: str
    worker_id: str
    action: str
    llm_suggestion: dict
    human_decision: dict
    diff: dict
    timestamp: str = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc).isoformat()


def write_audit(entry: AuditEntry):
    db_url = os.environ["DATABASE_URL"]
    with psycopg2.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO audit_log
                    (timestamp, patient_id, worker_id, action, llm_suggestion, human_decision, diff)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    entry.timestamp,
                    entry.patient_id,
                    entry.worker_id,
                    entry.action,
                    json.dumps(entry.llm_suggestion),
                    json.dumps(entry.human_decision),
                    json.dumps(entry.diff),
                ),
            )
        conn.commit()
