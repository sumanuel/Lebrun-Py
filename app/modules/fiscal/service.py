from __future__ import annotations

from pathlib import Path

from app.core.config import settings
from app.modules.fiscal.store import FiscalJobStore


class FiscalService:
    def __init__(self) -> None:
        self.store = FiscalJobStore(settings.fiscal_jobs_path)

    def enqueue_report(self, *, caja: str | None, report_type: str, requested_by: str | None) -> str:
        report_type = (report_type or "").strip().upper()
        if report_type not in {"X", "Z"}:
            raise ValueError("report_type inválido")
        job = self.store.enqueue(
            caja=str(caja) if caja is not None else None,
            job_type="REPORT_ZX",
            payload={"report": report_type, "requested_by": requested_by},
        )
        return job.id
