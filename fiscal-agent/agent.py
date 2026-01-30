from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

from tfhka_driver import TfhkaError, print_document, print_report_xz


def _env(name: str, default: str | None = None) -> str:
    val = os.getenv(name, default)
    if val is None:
        raise RuntimeError(f"Missing env var: {name}")
    return val


def _utc_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def log(msg: str) -> None:
    line = f"[{_utc_iso()}] {msg}"
    print(line, flush=True)


def complete_job(session: requests.Session, base_url: str, token: str, job_id: str, ok: bool, error: str | None = None) -> None:
    url = f"{base_url.rstrip('/')}/api/fiscal/{job_id}/complete"
    headers = {"X-Agent-Token": token}
    params = {"ok": str(bool(ok)).lower()}
    if error:
        params["error"] = error

    # Se permite incluir result (JSON) si el servidor lo soporta.
    payload: dict | None = None
    if ok:
        result = getattr(complete_job, "_last_result", None)
        if isinstance(result, dict) and result:
            payload = result
    r = session.post(url, headers=headers, params=params, json=payload, timeout=20)
    if r.status_code >= 400:
        raise RuntimeError(f"complete failed: {r.status_code} {r.text}")


def _load_invoice_snapshot(invoice_id: str) -> dict:
    invoice_id = str(invoice_id or "").strip()
    if not invoice_id:
        raise RuntimeError("PRINT_DOC: falta invoice_id")

    base = Path(os.getenv("LEBRUN_INVOICES_PATH", "").strip() or (Path(__file__).resolve().parents[1] / "data" / "invoices"))
    path = base / f"factura_{invoice_id}.json"
    if not path.exists():
        raise RuntimeError(f"PRINT_DOC: no existe snapshot: {path}")

    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    inv = data.get("invoice")
    if not isinstance(inv, dict):
        raise RuntimeError("PRINT_DOC: snapshot inválido (invoice no es dict)")

    # Pasamos doc_numero al dict para imprimir encabezado.
    doc_numero = data.get("doc_numero")
    if doc_numero:
        inv = {**inv, "doc_numero": str(doc_numero)}
    return inv


def execute_job_stub(job: dict) -> None:
    # Aquí es donde se integrará el driver/SDK fiscal.
    # Por ahora solo simulamos ejecución y dejamos huella en logs.
    job_type = str(job.get("job_type") or "")
    payload = job.get("payload") or {}
    caja = job.get("caja")

    if job_type == "REPORT_ZX":
        report = str(payload.get("report") or "").upper()
        if report not in {"X", "Z"}:
            raise RuntimeError(f"Reporte inválido: {report}")
        log(f"[STUB] Ejecutando reporte {report} para caja={caja} payload={json.dumps(payload, ensure_ascii=False)}")
        time.sleep(1.0)
        return

    if job_type == "PRINT_DOC":
        invoice_id = str(payload.get("invoice_id") or "")
        tipdoc = str(payload.get("tipdoc") or "FAV").strip().upper() or "FAV"
        log(f"[STUB] Imprimiendo doc tipdoc={tipdoc} invoice_id={invoice_id} caja={caja} payload={json.dumps(payload, ensure_ascii=False)}")
        time.sleep(1.0)
        return

    raise RuntimeError(f"Job type no soportado: {job_type}")


def execute_job(job: dict) -> None:
    # Reset del resultado a reportar por cada job.
    try:
        complete_job._last_result = None
    except Exception:
        pass

    job_type = str(job.get("job_type") or "")
    payload = job.get("payload") or {}
    caja = job.get("caja")

    # Modo explícito: stub (útil para demos sin impresora)
    mode = (os.getenv("LEBRUN_FISCAL_MODE") or "").strip().lower()
    if mode in {"stub", "simulate", "sim"}:
        return execute_job_stub(job)

    if job_type == "REPORT_ZX":
        report = str(payload.get("report") or "").upper()
        com_port = os.getenv("LEBRUN_FISCAL_COM_PORT")
        dll_path = os.getenv("LEBRUN_TFHKA_DLL_PATH")

        log(
            f"Ejecutando TFHKA reporte {report} caja={caja} com={com_port or '(sin COM)'} dll={(dll_path or '').strip() or '(sin dll)'}"
        )
        print_report_xz(report=report, com_port=str(com_port or ""), dll_path=str(dll_path or ""))
        return

    if job_type == "PRINT_DOC":
        invoice_id = str(payload.get("invoice_id") or "").strip()
        tipdoc = str(payload.get("tipdoc") or "FAV").strip().upper() or "FAV"
        com_port = os.getenv("LEBRUN_FISCAL_COM_PORT")
        dll_path = os.getenv("LEBRUN_TFHKA_DLL_PATH")

        inv = _load_invoice_snapshot(invoice_id)
        doc_numero = str(inv.get("doc_numero") or payload.get("doc_numero") or "").strip() or None
        log(
            f"Ejecutando TFHKA PRINT_DOC tipdoc={tipdoc} caja={caja} invoice_id={invoice_id} com={com_port or '(sin COM)'} dll={(dll_path or '').strip() or '(sin dll)'}"
        )

        info = print_document(tipdoc=tipdoc, invoice=inv, com_port=str(com_port or ""), dll_path=str(dll_path or ""))
        # Adjuntar resultado para reportarlo al backend.
        complete_job._last_result = {
            "invoice_id": invoice_id,
            "tipdoc": tipdoc,
            "doc_numero": doc_numero,
            "printed": True,
            "registered_machine_number": info.registered_machine_number,
            "last_invoice_number": info.last_invoice_number,
            "last_credit_note_number": info.last_credit_note_number,
            "last_debit_note_number": info.last_debit_note_number,
            "daily_closure_counter": info.daily_closure_counter,
        }
        return

    raise RuntimeError(f"Job type no soportado: {job_type}")


def main() -> int:
    base_url = _env("LEBRUN_SERVER_URL")
    token = _env("LEBRUN_FISCAL_AGENT_TOKEN")
    caja = os.getenv("LEBRUN_FISCAL_CAJA")
    poll_seconds = float(os.getenv("LEBRUN_FISCAL_POLL_SECONDS", "2"))

    headers = {"X-Agent-Token": token}

    log("Fiscal Agent iniciado")
    log(f"Servidor: {base_url}")
    log(f"Caja: {caja or '(sin filtro)'}")

    with requests.Session() as session:
        while True:
            try:
                url = f"{base_url.rstrip('/')}/api/fiscal/next"
                params = {}
                if caja:
                    params["caja"] = caja

                r = session.get(url, headers=headers, params=params, timeout=30)
                if r.status_code == 204:
                    time.sleep(poll_seconds)
                    continue

                if r.status_code == 401:
                    log("ERROR: Token inválido (401).")
                    time.sleep(5)
                    continue

                if r.status_code >= 400:
                    log(f"ERROR: next failed {r.status_code} {r.text}")
                    time.sleep(2)
                    continue

                job = r.json()
                job_id = str(job.get("id") or "")
                if not job_id:
                    log("ERROR: Job inválido (sin id)")
                    time.sleep(1)
                    continue

                log(f"Job recibido: {job_id} type={job.get('job_type')} caja={job.get('caja')}")

                try:
                    execute_job(job)
                except Exception as e:
                    err = str(e)
                    log(f"ERROR ejecutando job {job_id}: {err}")
                    try:
                        complete_job(session, base_url, token, job_id, ok=False, error=err)
                    except Exception as e2:
                        log(f"ERROR reportando fallo job {job_id}: {e2}")
                    time.sleep(1)
                    continue

                try:
                    complete_job(session, base_url, token, job_id, ok=True)
                    log(f"Job completado: {job_id}")
                except Exception as e:
                    log(f"ERROR reportando completado job {job_id}: {e}")

            except KeyboardInterrupt:
                log("Fiscal Agent detenido por usuario")
                return 0
            except Exception as e:
                log(f"ERROR general: {e}")
                time.sleep(2)


if __name__ == "__main__":
    raise SystemExit(main())
