from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.modules.fiscal.store import FiscalJobStore

router = APIRouter(prefix="/api/fiscal", tags=["fiscal-agent"])


def _require_agent_token(x_agent_token: str | None) -> None:
    expected = settings.fiscal_agent_token
    if not expected:
        raise HTTPException(status_code=503, detail="Fiscal agent token no configurado")
    if not x_agent_token or x_agent_token != expected:
        raise HTTPException(status_code=401, detail="Token inválido")


@router.get("/next")
def next_job(
    caja: str | None = Query(None),
    x_agent_token: str | None = Header(default=None, alias="X-Agent-Token"),
):
    _require_agent_token(x_agent_token)
    store = FiscalJobStore(settings.fiscal_jobs_path)
    job = store.claim_next(caja=caja)
    if not job:
        return JSONResponse(status_code=204, content=None)
    return job


@router.post("/{job_id}/complete")
def complete_job(
    job_id: str,
    ok: bool = Query(True),
    error: str | None = Query(None),
    x_agent_token: str | None = Header(default=None, alias="X-Agent-Token"),
):
    _require_agent_token(x_agent_token)
    store = FiscalJobStore(settings.fiscal_jobs_path)
    updated = store.complete(job_id=job_id, ok=ok, result=None, error=error)
    if not updated:
        raise HTTPException(status_code=404, detail="Job no encontrado")
    return updated
