from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.exceptions import DatabaseUnavailable
from app.db.session import session_for
from app.modules.facturacion.factura_session import _d


def _zpad(value: object, width: int) -> str:
    s = str(value or "").strip()
    if not s:
        return ""
    return s.zfill(width)


def _table_columns(session, table: str) -> dict[str, dict]:
    rows = session.execute(text(f"SHOW COLUMNS FROM {table}"), {}).mappings().all()
    cols: dict[str, dict] = {}
    for r in rows:
        cols[str(r.get("Field"))] = {
            "type": str(r.get("Type") or ""),
            "null": str(r.get("Null") or ""),
            "key": str(r.get("Key") or ""),
            "default": r.get("Default"),
            "extra": str(r.get("Extra") or ""),
        }
    return cols


def _insert_row(session, table: str, cols: dict[str, dict], data: dict) -> None:
    payload = {k: v for k, v in (data or {}).items() if k in cols}
    if not payload:
        raise ValueError(f"No hay columnas para insertar en {table}")
    keys = list(payload.keys())
    fields = ",".join(keys)
    binds = ",".join(f":{k}" for k in keys)
    session.execute(text(f"INSERT INTO {table} ({fields}) VALUES ({binds})"), payload)


def _next_doc_numero(session, table: str, tipdoc: str, width: int = 10) -> str:
    # En el WinForms el correlativo se maneja por tipo de documento.
    # Implementación inicial: MAX + 1 dentro de la misma tabla.
    row = session.execute(
        text(
            f"""
            SELECT COALESCE(MAX(CAST(dcli_numero AS UNSIGNED)), 0) AS mx
            FROM {table}
            WHERE dcli_tipdoc = :tipdoc
            """
        ),
        {"tipdoc": tipdoc},
    ).mappings().first()
    mx = int(row.get("mx") or 0) if row else 0
    return _zpad(mx + 1, width)


@dataclass(frozen=True)
class SavedInvoice:
    id: str
    path: Path
    doc_numero: str | None = None
    doc_table: str | None = None


class InvoiceSaveService:
    """Persistencia inicial para validar data sin impresora fiscal.

    En esta fase guardamos un snapshot JSON del documento en disco.
    (Luego se migra el INSERT real a tablas: admdoccli/adminvmov/admmovcaja.)
    """

    def __init__(self) -> None:
        self.base_path: Path = settings.invoices_path
        self.base_path.mkdir(parents=True, exist_ok=True)

    def save_snapshot(self, *, invoice: dict, user: dict | None = None, doc_numero: str | None = None) -> SavedInvoice:
        inv_id = uuid4().hex
        payload = {
            "id": inv_id,
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "user": {
                "username": (user or {}).get("username"),
                "caja": (user or {}).get("caja"),
                "empresa": (user or {}).get("empresa"),
            },
            "doc_numero": doc_numero,
            "invoice": invoice,
        }
        path = self.base_path / f"factura_{inv_id}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return SavedInvoice(id=inv_id, path=path, doc_numero=doc_numero)

    def save_to_db(self, *, invoice: dict, user: dict, supervisor_user: str | None = None) -> tuple[str, str]:
        """Guarda la factura en MySQL (sysadm).

        Devuelve (doc_numero, tabla_usada).
        """

        tipdoc = (invoice.get("tipdoc") or "FAV").strip().upper() or "FAV"
        if tipdoc not in {"FAV", "DEV", "NDE"}:
            tipdoc = "FAV"

        cliente = invoice.get("cliente") or {}
        vendedor = invoice.get("vendedor") or {}

        cli_codigo = str(cliente.get("codigo") or "").strip()
        vend_codigo = str(vendedor.get("codigo") or "").strip()
        caja = str(user.get("caja") or "").strip()

        fecha = str(invoice.get("fecha") or "").strip()
        if not fecha:
            fecha = datetime.now().date().isoformat()
        hora = datetime.now().strftime("%H:%M:%S")

        totals = invoice.get("totales") or {}
        subtotal = _d(totals.get("subtotal"))
        des_items = _d(totals.get("des_items"))
        base = _d(totals.get("base"))
        iva = _d(totals.get("iva"))
        neto = _d(totals.get("neto"))
        pagado = _d(totals.get("pagado"))
        cambio = _d(totals.get("cambio"))

        saldo = neto - pagado
        if saldo < Decimal("0"):
            saldo = Decimal("0")
        estado = "Pagado" if pagado >= neto else "Activo"
        usuario = str(user.get("username") or "").strip()

        afectada = invoice.get("afectada") or {}
        facafe = str(afectada.get("numero") or "").strip()

        header_tables = ["admdoccli2", "admdoccli"]

        try:
            with session_for(settings.db_sysadm) as s:
                last_error: Exception | None = None
                for table in header_tables:
                    try:
                        cols = _table_columns(s, table)
                        doc_numero = _next_doc_numero(s, table, tipdoc)

                        header = {
                            "dcli_numero": doc_numero,
                            "dcli_tipdoc": tipdoc,
                            "dcli_codigo": cli_codigo,
                            "dcli_codven": vend_codigo,
                            "dcli_caja": caja,
                            "dcli_fecha": fecha,
                            "dcli_hora": hora,
                            "dcli_estado": estado,
                            "dcli_baseneta": f"{base:.2f}",
                            "dcli_mtoiva": f"{iva:.2f}",
                            "dcli_neto": f"{neto:.2f}",
                            "dcli_subtotal": f"{subtotal:.2f}",
                            "dcli_descitem": f"{des_items:.2f}",
                            "dcli_saldo": f"{saldo:.2f}",
                            "dcli_impreso": "0",
                            "dcli_cerrado": "0",
                            "dcli_usuario": usuario,
                        }

                        if facafe:
                            header["dcli_facafe"] = facafe

                        if supervisor_user:
                            header.setdefault("dcli_aprob1", supervisor_user)

                        _insert_row(s, table, cols, header)

                        # Items
                        items_cols = _table_columns(s, "adminvmov")
                        items = invoice.get("items") or []
                        for idx, it in enumerate(items, start=1):
                            qty = _d(it.get("cantidad"))
                            price = _d(it.get("precio"))
                            desc = _d(it.get("desc"))
                            total = _d(it.get("total"))
                            iva_line = _d(it.get("iva"))
                            item_row = {
                                "mov_docume": doc_numero,
                                "mov_tipdoc": tipdoc,
                                "mov_codcta": cli_codigo,
                                "mov_item": idx,
                                "mov_codigo": str(it.get("codigo") or "").strip(),
                                "mov_undmed": str(it.get("unidad") or "").strip(),
                                "mov_cant": f"{qty:.6f}",
                                "mov_precio": f"{price:.6f}",
                                "mov_desc": f"{desc:.6f}",
                                "mov_total": f"{total:.6f}",
                                "mov_fecha": fecha,
                                "mov_hora": hora,
                                "mov_vendedor": vend_codigo,
                            }
                            # IVA si existe en la tabla
                            item_row["mov_iva"] = f"{iva_line:.6f}"
                            item_row["mov_ivatip"] = str(it.get("iva_tipo") or "").strip()
                            _insert_row(s, "adminvmov", items_cols, item_row)

                        # Pagos
                        pagos = invoice.get("pagos") or []
                        if pagos:
                            pagos_cols = _table_columns(s, "admmovcaja")
                            # movc_numtra: correlativo simple
                            r = s.execute(text("SELECT COALESCE(MAX(CAST(movc_numtra AS UNSIGNED)), 0) AS mx FROM admmovcaja"), {}).mappings().first()
                            movc_numtra = int((r or {}).get("mx") or 0)

                            def map_forpag(modo: str) -> str:
                                m = (modo or "").strip().lower()
                                if m == "efectivo":
                                    return "EFECTIVO"
                                if "cheque" in m:
                                    return "CHEQUE"
                                if "debito" in m:
                                    return "TARJETA-D"
                                if "credito" in m:
                                    return "TARJETA-C"
                                return (modo or "").strip().upper() or "OTRO"

                            for p in pagos:
                                movc_numtra += 1
                                monto = _d(p.get("monto"))
                                forpag = map_forpag(str(p.get("modo") or ""))
                                pago_row = {
                                    "movc_numtra": movc_numtra,
                                    "movc_codmaestr": cli_codigo,
                                    "movc_numdoc": doc_numero,
                                    "movc_descrioper": "Mov Caja en Ventas",
                                    "movc_operacion": "D",
                                    "movc_forpag": forpag,
                                    "mocv_forpag": forpag,
                                    "movc_tipoctaban": str(p.get("banco") or "").strip() or "N/A",
                                    "movc_numero": str(p.get("referencia") or "").strip() or " ",
                                    "movc_monto": f"{monto:.2f}",
                                    "movc_fchemision": fecha,
                                    "movc_hora": hora,
                                    "movc_vendedor": vend_codigo,
                                    "movc_codcaja": caja,
                                    "movc_tipomovc": "MOVCAJAV",
                                    "movc_estatus": "Activo",
                                    "movc_valcam": "0.00",
                                    "movc_memo": " ",
                                }
                                _insert_row(s, "admmovcaja", pagos_cols, pago_row)

                            # Cambio (si aplica)
                            if cambio > Decimal("0"):
                                movc_numtra += 1
                                cambio_row = {
                                    "movc_numtra": movc_numtra,
                                    "movc_codmaestr": cli_codigo,
                                    "movc_numdoc": doc_numero,
                                    "movc_descrioper": "Mov Caja en Ventas",
                                    "movc_operacion": "D",
                                    "movc_forpag": "CAMBIO",
                                    "mocv_forpag": "CAMBIO",
                                    "movc_tipoctaban": "N/A",
                                    "movc_numero": " ",
                                    "movc_monto": f"{cambio:.2f}",
                                    "movc_fchemision": fecha,
                                    "movc_hora": hora,
                                    "movc_vendedor": vend_codigo,
                                    "movc_codcaja": caja,
                                    "movc_tipomovc": "MOVCAJAV",
                                    "movc_estatus": "Activo",
                                    "movc_valcam": f"{cambio:.2f}",
                                    "movc_memo": " ",
                                }
                                _insert_row(s, "admmovcaja", pagos_cols, cambio_row)

                        return doc_numero, table
                    except Exception as e:
                        last_error = e
                        continue

                raise last_error or RuntimeError("No se pudo guardar en admdoccli2/admdoccli")
        except SQLAlchemyError as e:
            msg = str(getattr(getattr(e, "orig", None), "args", None) or str(e))
            raise DatabaseUnavailable(f"Error guardando factura (sisadm): {msg}") from e
        except Exception as e:
            raise

    def save(self, *, invoice: dict, user: dict | None = None) -> SavedInvoice:
        # Compatibilidad: si alguien lo usa directo, sigue guardando snapshot.
        return self.save_snapshot(invoice=invoice, user=user)
