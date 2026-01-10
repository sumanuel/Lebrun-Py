from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class FiscalJobStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


@dataclass(frozen=True)
class FiscalJob:
    id: str
    created_at: str
    status: FiscalJobStatus
    caja: str | None
    job_type: str
    payload: dict
    result: dict | None = None
    error: str | None = None


def utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
