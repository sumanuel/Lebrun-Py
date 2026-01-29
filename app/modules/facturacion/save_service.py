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


def _next_doc_numero(session, tipdoc: str) -> str:
    """Obtiene el siguiente correlativo del sistema (WinForms) por tipo documento.

    Tabla: admtipdoccli.ctd_correlativo
    - El WinForms lee ctd_correlativo y devuelve +1 (12 dígitos).
    - Luego, al guardar, actualiza ctd_correlativo al número usado.

    Aquí lo hacemos de forma transaccional con FOR UPDATE para evitar duplicados.
    """

    row = session.execute(
        text(
            """
            SELECT ctd_correlativo
            FROM admtipdoccli
            WHERE ctd_tipo = :tipdoc
            FOR UPDATE
            """
        ),
        {"tipdoc": tipdoc},
    ).mappings().first()
    current_s = str((row or {}).get("ctd_correlativo") or "").strip()
    current = int(current_s or "0")
    return str(current + 1).zfill(12)


def _update_correlativo(session, tipdoc: str, used_numero: str) -> None:
    used_numero = str(used_numero or "").strip()
    if not used_numero:
        return
    session.execute(
        text(
            """
            UPDATE admtipdoccli
            SET ctd_correlativo = :used
            WHERE ctd_tipo = :tipdoc
            """
        ),
        {"used": used_numero, "tipdoc": tipdoc},
    )


def _safe_select_one(session, *, table: str, wanted: list[str], where_sql: str, params: dict) -> dict:
    cols = _table_columns(session, table)
    selected = [c for c in wanted if c in cols]
    if not selected:
        return {}
    sql = text(f"SELECT {', '.join(selected)} FROM {table} WHERE {where_sql} LIMIT 1")
    row = session.execute(sql, params).mappings().first()
    return dict(row) if row else {}


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
        empresa = str(user.get("empresa") or user.get("company_code") or "").strip()

        # WinForms arma fechas/hora desde DateTime.Now; usamos ISO para fecha y hh:mm:ss tt para hora.
        fecha = datetime.now().date().isoformat()
        hora_12 = datetime.now().strftime("%I:%M:%S %p")

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

        # admdoccli2 suele llenarse por trigger desde admdoccli.
        header_table = "admdoccli"

        try:
            with session_for(settings.db_sysadm) as s:
                cols = _table_columns(s, header_table)

                cli_row = _safe_select_one(
                    s,
                    table="admclientes",
                    wanted=["cli_condipag", "cli_tiplista"],
                    where_sql="cli_codigo = :c",
                    params={"c": cli_codigo},
                )
                condic = str(cli_row.get("cli_condipag") or "").strip()
                tipo_lista = str(cli_row.get("cli_tiplista") or "").strip()

                doc_numero = _next_doc_numero(s, tipdoc)

                # Totales derivados adicionales (para acercarnos a WinForms)
                items = invoice.get("items") or []
                base_ex = Decimal("0")
                iva_gn = Decimal("0")
                iva_rd = Decimal("0")
                for it in items:
                    total_line = _d(it.get("total"))
                    iva_line = _d(it.get("iva"))
                    exento = str(it.get("exento") or "").strip().lower() in {"1", "si", "sí", "s", "true", "t", "y", "yes"}
                    if exento:
                        base_ex += total_line
                    iva_tipo = str(it.get("iva_tipo") or "").strip().upper()
                    if iva_tipo == "GN":
                        iva_gn += iva_line
                    elif iva_tipo in {"RD", "A"}:
                        iva_rd += iva_line

                tiptra = "D" if tipdoc == "FAV" else "C"
                tipafe = "CTZ" if tipdoc == "CTZ" else "FAV"
                cxc = "1" if tipdoc in {"FAV", "CTZ", "NDE"} else "-1"

                sucursal = ("0000" + empresa) if empresa else " "
                facafe_value = doc_numero if tipdoc == "FAV" else facafe

                numgtr = str(afectada.get("numfis") or "").strip() or " "
                if tipdoc == "FAV":
                    numgtr = " "

                header = {
                    # Equivalente a crearSentenciaCabecera (los que existan se insertan)
                    "dcli_cbtnum": " ",
                    "dcli_cencos": "0000000001",
                    "dcli_codigo": cli_codigo,
                    "dcli_codmon": "Bs",
                    "dcli_sucursal": sucursal,
                    "dcli_transpo": " ",
                    "dcli_codven": vend_codigo,
                    "dcli_condic": condic or " ",
                    "dcli_destino": "Nacional",
                    "dcli_origen": "Nacional",
                    "dcli_estado": estado,
                    "dcli_expexp": estado,
                    "dcli_facafe": facafe_value or " ",
                    "dcli_girnum": "",
                    "dcli_hora": hora_12,
                    "dcli_modfis": " ",
                    "dcli_numero": doc_numero,
                    "dcli_numfis": " ",
                    "dcli_numgtr": numgtr,
                    "dcli_plaexp": " ",
                    "dcli_recnum": " ",
                    "dcli_serfis": " ",
                    "dcli_succli": " ",
                    "dcli_tipafe": tipafe,
                    "dcli_tipdoc": tipdoc,
                    "dcli_tiptra": tiptra,
                    "dcli_usuario": usuario,
                    "dcli_zona": " ",
                    "dcli_fecharecep": fecha,
                    "dcli_fchven": fecha,
                    "dcli_fecha": fecha,
                    "dcli_anufis": " ",
                    "dcli_crerecibo": " ",
                    "dcli_impreso": "0",
                    "dcli_invmon": "Bs",
                    "dcli_estatus": estado,
                    "dcli_baseneta": f"{base:.2f}",
                    "dcli_cxc": cxc,
                    "dcli_dcto": "0.00",
                    "dcli_otroimp": "0",
                    "dcli_mtocomisio": "0",
                    "dcli_mtoiva": f"{iva:.2f}",
                    "dcli_neto": f"{neto:.2f}",
                    "dcli_numpag": " ",
                    "dcli_otros": "0",
                    "dcli_plazo": "0",
                    "dcli_recargo": "0",
                    "dclli_valcamb": "1",
                    "dcli_dctobs": "0.00",
                    "dcli_totdivi": f"{neto:.2f}",
                    "dcli_descitem": f"{des_items:.2f}",
                    "dcli_descdoc": "0.00",
                    "dcli_subbase": f"{base_ex:.2f}",
                    "doc_impo": f"{base:.2f}",
                    "dcli_cantproduc": str(int(_d(totals.get("total_prod")) or 0)),
                    "dcli_impresora": " ",
                    "dcli_caja": caja,
                    "dcli_cerrado": "0",
                    "dcli_cosfac": "0.00",
                    "dcli_cosfac_n": "0.00",
                    "dcli_cosfac_i": "0.00",
                    "dcli_base_n": "0.00",
                    "dcli_base_i": "0.00",
                    "dcli_saldo": f"{saldo:.2f}",
                    "dcli_facafe2": " ",
                    "dcli_subtotal": f"{base:.2f}",
                    "dcli_ivaGN": f"{iva_gn:.2f}",
                    "dcli_ivaRD": f"{iva_rd:.2f}",
                }

                if supervisor_user:
                    header.setdefault("dcli_aprob1", supervisor_user)

                _insert_row(s, header_table, cols, header)

                # Items (WinForms: agregarArticulo + guardarDetalleFac)
                items_cols = _table_columns(s, "adminvmov")
                for idx, it in enumerate(items, start=1):
                    inv_code = str(it.get("codigo") or "").strip()
                    qty = _d(it.get("cantidad"))
                    price = _d(it.get("precio"))
                    desc = _d(it.get("desc"))
                    total = _d(it.get("total"))
                    iva_line = _d(it.get("iva"))
                    iva_pct = _d(it.get("iva_pct"))

                    mov_docaso = "FAV" if tipdoc == "DEV" else tipdoc
                    mov_codtra = "S000" if tipdoc == "FAV" else "E000"
                    mov_contab = "1" if tipdoc == "DEV" else "-1"
                    mov_fisico = "1" if tipdoc == "DEV" else "-1"
                    mov_logico = "1" if tipdoc == "DEV" else "-1"

                    mov_lista = (tipo_lista or "A").strip() or "A"
                    mov_item = str(idx).zfill(3)

                    item_row = {
                        "mov_docaso": mov_docaso,
                        "mov_tipoaso": "",
                        "mov_cencos": "0000000001",
                        "mov_codalm": "000001",
                        "mov_cdcomp": " ",
                        "mov_codcta": cli_codigo,
                        "mov_codigo": inv_code,
                        "mov_codsuc": sucursal,
                        "mov_codtra": mov_codtra,
                        "mov_vendedor": vend_codigo,
                        "mov_docume": doc_numero,
                        "mov_hora": hora_12,
                        "mov_item": mov_item,
                        "mov_itemaso": " ",
                        "mov_itemcomp": " ",
                        "mov_lista": mov_lista,
                        "mov_lote": " ",
                        "mov_tipdoc": tipdoc,
                        "mov_ivatip": str(it.get("iva_tipo") or "").strip(),
                        "mov_tipo": "V",
                        "mov_undmed": str(it.get("unidad") or "").strip(),
                        "mov_usuario": str(user.get("id") or usuario),
                        "mov_fechven": fecha,
                        "mov_fecha": fecha,
                        "mov_bandas": "0",
                        "mov_cant": f"{qty:.6f}",
                        "mov_contab": mov_contab,
                        "mov_costo": "0.00",
                        "mov_cxund": "1",
                        "mov_desc": f"{desc:.6f}",
                        "mov_expendio": "0",
                        "mov_export": "0",
                        "mov_fisico": mov_fisico,
                        "mov_import": "0",
                        "mov_otimp": "0",
                        "mov_impprodu": "0",
                        "mov_invact": "1",
                        "mov_iva": f"{iva_line:.6f}",
                        "mov_logico": mov_logico,
                        "mov_mtocom": "0",
                        "mov_memo": " ",
                        "mov_precio": f"{price:.6f}",
                        "mov_total": f"{total:.6f}",
                        "mov_talla": "0",
                        "mov_color": "0",
                        "mov_arancel": "0",
                        "mov_kilos": "0",
                        "mov_impuesto": "0",
                        "mov_cosmon": f"{price:.6f}",
                        "mov_totalmon": f"{total:.6f}",
                        "mov_precio_ini": "0.00",
                        "mov_porciva": f"{iva_pct:.6f}",
                    }
                    _insert_row(s, "adminvmov", items_cols, item_row)

                # Pagos
                pagos = invoice.get("pagos") or []
                if pagos:
                    pagos_cols = _table_columns(s, "admmovcaja")
                    r = s.execute(
                        text("SELECT COALESCE(MAX(CAST(movc_numtra AS UNSIGNED)), 0) AS mx FROM admmovcaja"),
                        {},
                    ).mappings().first()
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
                            "movc_hora": hora_12,
                            "movc_vendedor": vend_codigo,
                            "movc_codcaja": caja,
                            "movc_tipomovc": "MOVCAJAV",
                            "movc_estatus": "Activo",
                            "movc_valcam": "0.00",
                            "movc_memo": " ",
                        }
                        _insert_row(s, "admmovcaja", pagos_cols, pago_row)

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
                            "movc_hora": hora_12,
                            "movc_vendedor": vend_codigo,
                            "movc_codcaja": caja,
                            "movc_tipomovc": "MOVCAJAV",
                            "movc_estatus": "Activo",
                            "movc_valcam": f"{cambio:.2f}",
                            "movc_memo": " ",
                        }
                        _insert_row(s, "admmovcaja", pagos_cols, cambio_row)

                _update_correlativo(s, tipdoc, doc_numero)

                # CxC (WinForms: guardarSalcli)
                try:
                    sal_cols = _table_columns(s, "admsalcli")
                except Exception:
                    sal_cols = {}

                if sal_cols:
                    contado = neto
                    sal_actual = (contado - pagado) if tipdoc == "FAV" else (pagado - contado)
                    sal_row = {
                        "cli_codigo": cli_codigo,
                        "sal_actual": f"{sal_actual:.2f}",
                        "TipoDoc": tipdoc,
                        "NroDocum": doc_numero,
                        "CodVend": vend_codigo,
                        "FechaEmision": fecha,
                        "FechaVenc": fecha,
                        "FechaCarga": fecha,
                        "MontoTotal": f"{contado:.2f}",
                        "MontoCob": f"{contado:.2f}",
                        "CostoFact": "0.00",
                        "MontoNac": "0.00",
                        "MontoImp": "0.00",
                        "NroCaja": caja,
                        "CondPago": condic or " ",
                        "MontoIva": f"{iva:.2f}",
                        "dcli_cosfac_n": "0.00",
                        "dcli_cosfac_i": "0.00",
                        "dcli_facafe": doc_numero,
                        "dcli_tipdoc2": tipdoc,
                        "dcli_numfis": " ",
                        "Status": "0",
                    }
                    _insert_row(s, "admsalcli", sal_cols, sal_row)

                return doc_numero, header_table
        except SQLAlchemyError as e:
            msg = str(getattr(getattr(e, "orig", None), "args", None) or str(e))
            raise DatabaseUnavailable(f"Error guardando factura (sisadm): {msg}") from e
        except Exception as e:
            raise

    def save(self, *, invoice: dict, user: dict | None = None) -> SavedInvoice:
        # Compatibilidad: si alguien lo usa directo, sigue guardando snapshot.
        return self.save_snapshot(invoice=invoice, user=user)
