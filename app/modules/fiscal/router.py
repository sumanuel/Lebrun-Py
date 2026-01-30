from __future__ import annotations

from fastapi import APIRouter, Body, Header, HTTPException, Query
from fastapi.responses import JSONResponse

from sqlalchemy import text

from app.core.config import settings
from app.db.session import session_for

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
    result: dict | None = Body(default=None),
    x_agent_token: str | None = Header(default=None, alias="X-Agent-Token"),
):
    _require_agent_token(x_agent_token)

    # Si es impresión de documento, intentamos actualizar campos fiscales en DB.
    enriched_result = dict(result or {}) if isinstance(result, dict) else None
    if ok and isinstance(enriched_result, dict) and enriched_result.get("printed"):
        try:
            tipdoc = str(enriched_result.get("tipdoc") or "").strip().upper()
            doc_numero = str(enriched_result.get("doc_numero") or "").strip()
            impfis = str(enriched_result.get("registered_machine_number") or "").strip()

            numfis = ""
            if tipdoc == "FAV":
                numfis = str(enriched_result.get("last_invoice_number") or "").strip()
            elif tipdoc == "DEV":
                numfis = str(enriched_result.get("last_credit_note_number") or "").strip()
            elif tipdoc == "NDE":
                numfis = str(enriched_result.get("last_debit_note_number") or "").strip()

            if tipdoc and doc_numero and numfis:
                with session_for(settings.db_sysadm) as s:
                    cols = {
                        str(r.get("Field")): r
                        for r in s.execute(text("SHOW COLUMNS FROM admdoccli"), {}).mappings().all()
                    }
                    updates: dict[str, object] = {}
                    if "dcli_numfis" in cols:
                        updates["dcli_numfis"] = numfis
                    if impfis and "dcli_impfis" in cols:
                        updates["dcli_impfis"] = impfis
                    if "dcli_impreso" in cols:
                        updates["dcli_impreso"] = "1"

                    if updates:
                        set_sql = ", ".join(f"{k} = :{k}" for k in updates.keys())
                        params = {**updates, "doc_numero": doc_numero, "tipdoc": tipdoc}
                        s.execute(
                            text(
                                f"""
                                UPDATE admdoccli
                                SET {set_sql}
                                WHERE dcli_numero = :doc_numero AND dcli_tipdoc = :tipdoc
                                """
                            ),
                            params,
                        )
                    s.commit()

                enriched_result["db_update_ok"] = True
                enriched_result["fiscal_doc_number"] = numfis
            else:
                enriched_result["db_update_ok"] = False
                enriched_result["db_update_error"] = "Faltan datos para actualizar DB (tipdoc/doc_numero/numfis)."
        except Exception as e:
            if isinstance(enriched_result, dict):
                enriched_result["db_update_ok"] = False
                enriched_result["db_update_error"] = str(e)

    store = FiscalJobStore(settings.fiscal_jobs_path)
    updated = store.complete(job_id=job_id, ok=ok, result=enriched_result if ok else result, error=error)
    if not updated:
        raise HTTPException(status_code=404, detail="Job no encontrado")
    return updated
