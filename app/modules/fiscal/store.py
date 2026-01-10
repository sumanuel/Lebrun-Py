from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from uuid import uuid4

from app.modules.fiscal.models import FiscalJob, FiscalJobStatus, utc_now_iso


class FiscalJobStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def _read_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        raw = self.path.read_text(encoding="utf-8").strip()
        if not raw:
            return []
        return json.loads(raw)

    def _write_all(self, rows: list[dict]) -> None:
        self.path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    def enqueue(self, *, caja: str | None, job_type: str, payload: dict) -> FiscalJob:
        with self._lock:
            rows = self._read_all()
            job_id = uuid4().hex
            job = FiscalJob(
                id=job_id,
                created_at=utc_now_iso(),
                status=FiscalJobStatus.pending,
                caja=caja,
                job_type=job_type,
                payload=payload or {},
            )
            rows.append(
                {
                    "id": job.id,
                    "created_at": job.created_at,
                    "status": job.status.value,
                    "caja": job.caja,
                    "job_type": job.job_type,
                    "payload": job.payload,
                    "result": job.result,
                    "error": job.error,
                }
            )
            self._write_all(rows)
            return job

    def claim_next(self, *, caja: str | None = None) -> dict | None:
        with self._lock:
            rows = self._read_all()
            for row in rows:
                if row.get("status") != FiscalJobStatus.pending.value:
                    continue
                if caja and str(row.get("caja") or "") != str(caja):
                    continue
                row["status"] = FiscalJobStatus.processing.value
                self._write_all(rows)
                return row
            return None

    def complete(self, *, job_id: str, ok: bool, result: dict | None = None, error: str | None = None) -> dict | None:
        with self._lock:
            rows = self._read_all()
            for row in rows:
                if str(row.get("id")) != str(job_id):
                    continue
                row["status"] = FiscalJobStatus.completed.value if ok else FiscalJobStatus.failed.value
                row["result"] = result
                row["error"] = error
                self._write_all(rows)
                return row
            return None
