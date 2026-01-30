from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import os
from pathlib import Path


class TfhkaError(RuntimeError):
    pass


def _d(v: object, default: Decimal = Decimal("0")) -> Decimal:
    if v is None:
        return default
    if isinstance(v, Decimal):
        return v
    s = str(v).strip()
    if not s:
        return default
    s = s.replace(".", "").replace(",", ".") if s.count(",") == 1 and s.count(".") >= 1 else s.replace(",", ".")
    try:
        return Decimal(s)
    except InvalidOperation:
        return default


def _as_int_scaled(amount: Decimal, factor: int) -> int:
    if factor <= 0:
        return int(amount)
    q = Decimal("1")
    scaled = (amount * Decimal(factor)).quantize(q, rounding=ROUND_HALF_UP)
    return int(scaled)


@dataclass(frozen=True)
class TfhkaFiscalConfig:
    # Formato fiscal (defaults basados en globales.cs del WinForms)
    price_len: int = int(os.getenv("LEBRUN_FISCAL_PRICE_LEN", "9"))
    price_factor: int = int(os.getenv("LEBRUN_FISCAL_PRICE_FACTOR", "100"))
    qty_len: int = int(os.getenv("LEBRUN_FISCAL_QTY_LEN", "7"))
    qty_factor: int = int(os.getenv("LEBRUN_FISCAL_QTY_FACTOR", "1000"))
    pay_len: int = int(os.getenv("LEBRUN_FISCAL_PAY_LEN", "9"))
    pay_factor: int = int(os.getenv("LEBRUN_FISCAL_PAY_FACTOR", "100"))
    pad_char: str = os.getenv("LEBRUN_FISCAL_PAD_CHAR", "0") or "0"

    # Códigos de forma de pago (defaults desde globales/app.config)
    code_efectivo_bs: str = os.getenv("LEBRUN_FISCAL_CODE_EFECTIVO_BS", "03")
    code_efectivo_dol: str = os.getenv("LEBRUN_FISCAL_CODE_EFECTIVO_DOL", "02")
    code_divisa_igtf: str = os.getenv("LEBRUN_FISCAL_CODE_DIVISA_IGTF", "20")
    code_tarjeta: str = os.getenv("LEBRUN_FISCAL_CODE_TARJETA", "09")
    code_credito: str = os.getenv("LEBRUN_FISCAL_CODE_CREDITO", "13")
    code_cheque: str = os.getenv("LEBRUN_FISCAL_CODE_CHEQUE", "08")
    code_pagomovil: str = os.getenv("LEBRUN_FISCAL_CODE_PAGOMOVIL", "06")
    code_cashea: str = os.getenv("LEBRUN_FISCAL_CODE_CASHEA", "07")


@dataclass(frozen=True)
class PrintedDocInfo:
    registered_machine_number: str | None = None
    last_invoice_number: str | None = None
    last_credit_note_number: str | None = None
    last_debit_note_number: str | None = None
    daily_closure_counter: str | None = None


def _load_tfhka(dll_path: str):
    """Carga TfhkaNet.dll usando pythonnet.

    Se importa de forma lazy para que el agente pueda correr en modo stub
    incluso si pythonnet no está instalado.
    """

    try:
        import clr  # type: ignore
    except Exception as e:  # pragma: no cover
        raise TfhkaError(
            "No se pudo importar pythonnet (clr). Instale dependencias del fiscal-agent."
        ) from e

    dll = Path(dll_path)
    if not dll.exists():
        raise TfhkaError(f"No existe TfhkaNet.dll en: {dll}")

    try:
        clr.AddReference(str(dll))
    except Exception as e:
        raise TfhkaError(f"No se pudo cargar el assembly: {dll}") from e

    try:
        from TfhkaNet.IF.VE import Tfhka  # type: ignore
    except Exception as e:
        raise TfhkaError(
            "No se pudo importar TfhkaNet.IF.VE.Tfhka desde el DLL. Verifique versión/arquitectura."
        ) from e

    return Tfhka


def print_report_xz(*, report: str, com_port: str, dll_path: str) -> None:
    report = (report or "").strip().upper()
    if report not in {"X", "Z"}:
        raise TfhkaError(f"Reporte inválido: {report}")

    com_port = (com_port or "").strip()
    if not com_port:
        raise TfhkaError("Falta configurar LEBRUN_FISCAL_COM_PORT (ej: COM3)")

    dll_path = (dll_path or "").strip()
    if not dll_path:
        raise TfhkaError(
            "Falta configurar LEBRUN_TFHKA_DLL_PATH (ruta a TfhkaNet.dll en la PC fiscal)"
        )

    Tfhka = _load_tfhka(dll_path)

    impresora = Tfhka()
    opened = False

    try:
        ok = bool(impresora.OpenFpCtrl(com_port))
        opened = ok
        if not ok:
            raise TfhkaError(f"No se pudo abrir el puerto {com_port} (OpenFpCtrl=false)")

        ok = bool(impresora.CheckFPrinter())
        if not ok:
            raise TfhkaError("Impresora no responde / CheckFPrinter=false")

        if report == "X":
            impresora.PrintXReport()
        else:
            impresora.PrintZReport()

    except TfhkaError:
        raise
    except Exception as e:
        raise TfhkaError(str(e)) from e
    finally:
        if opened:
            try:
                impresora.CloseFpCtrl()
            except Exception:
                pass


def _open_printer(*, com_port: str, dll_path: str):
    com_port = (com_port or "").strip()
    if not com_port:
        raise TfhkaError("Falta configurar LEBRUN_FISCAL_COM_PORT (ej: COM3)")

    dll_path = (dll_path or "").strip()
    if not dll_path:
        raise TfhkaError("Falta configurar LEBRUN_TFHKA_DLL_PATH (ruta a TfhkaNet.dll)")

    Tfhka = _load_tfhka(dll_path)
    impresora = Tfhka()

    ok = bool(impresora.OpenFpCtrl(com_port))
    if not ok:
        raise TfhkaError(f"No se pudo abrir el puerto {com_port} (OpenFpCtrl=false)")

    ok = bool(impresora.CheckFPrinter())
    if not ok:
        try:
            impresora.CloseFpCtrl()
        except Exception:
            pass
        raise TfhkaError("Impresora no responde / CheckFPrinter=false")

    return impresora


def _send_cmd(impresora, cmd: str) -> None:
    cmd = str(cmd or "")
    if not cmd:
        return
    try:
        ok = bool(impresora.SendCmd(cmd))
    except Exception as e:
        raise TfhkaError(f"SendCmd falló ({cmd}): {e}") from e

    if not ok:
        try:
            st = impresora.GetPrinterStatus()
            err = getattr(st, "PrinterErrorCode", None)
            code = getattr(st, "PrinterStatusCode", None)
            raise TfhkaError(f"Impresora rechazó cmd={cmd!r} err={err} status={code}")
        except TfhkaError:
            raise
        except Exception:
            raise TfhkaError(f"Impresora rechazó cmd={cmd!r}")

    try:
        st = impresora.GetPrinterStatus()
        err = int(getattr(st, "PrinterErrorCode", 0) or 0)
        if err != 0:
            code = getattr(st, "PrinterStatusCode", None)
            raise TfhkaError(f"Error impresora cmd={cmd!r} err={err} status={code}")
    except TfhkaError:
        raise
    except Exception:
        pass


def _fmt_num(n: int, *, total_len: int, pad_char: str) -> str:
    pad = (pad_char or "0")[0]
    s = str(abs(int(n)))
    return s.rjust(int(total_len), pad)


def _build_item_cmd(*, tipdoc: str, taxable: bool, price: Decimal, qty: Decimal, desc: str, cfg: TfhkaFiscalConfig) -> str:
    tipdoc = (tipdoc or "FAV").strip().upper() or "FAV"
    price_i = _as_int_scaled(price, cfg.price_factor)
    qty_i = _as_int_scaled(qty, cfg.qty_factor)

    lprecio = (cfg.pad_char or "0") + _fmt_num(price_i, total_len=cfg.price_len, pad_char=cfg.pad_char)
    lcant = (cfg.pad_char or "0") + _fmt_num(qty_i, total_len=cfg.qty_len, pad_char=cfg.pad_char)
    ldesc = (desc or "").strip()

    if tipdoc == "FAV":
        prefix = "!" if taxable else " "
    else:
        prefix = "d1" if taxable else "d0"

    return f"{prefix}{lprecio}{lcant}{ldesc}"


def _payment_code_for_mode(mode: str, *, cfg: TfhkaFiscalConfig, aplica_igtf: bool) -> str:
    m = (mode or "").strip().lower()
    if "tarjeta" in m:
        return cfg.code_tarjeta
    if "credito" in m or "crédito" in m:
        return cfg.code_credito
    if "cheque" in m:
        return cfg.code_cheque
    if "pago" in m and "mov" in m:
        return cfg.code_pagomovil
    if "cashea" in m:
        return cfg.code_cashea
    if "div" in m or "dol" in m or "$" in m:
        return cfg.code_divisa_igtf if aplica_igtf else cfg.code_efectivo_dol
    return cfg.code_efectivo_bs


def _build_payment_cmd(*, mode: str, amount: Decimal, cfg: TfhkaFiscalConfig, aplica_igtf: bool) -> str:
    code = _payment_code_for_mode(mode, cfg=cfg, aplica_igtf=aplica_igtf)
    amt_i = _as_int_scaled(amount, cfg.pay_factor)
    lamt = (cfg.pad_char or "0") + _fmt_num(amt_i, total_len=cfg.pay_len, pad_char=cfg.pad_char)
    return f"2{code}{lamt}"


def print_document(*, tipdoc: str, invoice: dict, com_port: str, dll_path: str) -> PrintedDocInfo:
    """Imprime un documento fiscal usando TFHKA.

    `invoice` es el diccionario de sesión/snapshot (incluye cliente/items/pagos/totales).
    """

    tipdoc = (tipdoc or "FAV").strip().upper() or "FAV"
    if tipdoc not in {"FAV", "DEV", "NDE"}:
        tipdoc = "FAV"

    cfg = TfhkaFiscalConfig()
    impresora = _open_printer(com_port=com_port, dll_path=dll_path)
    opened = True

    try:
        inv = invoice or {}
        cliente = inv.get("cliente") or {}
        vendedor = inv.get("vendedor") or {}
        totales = inv.get("totales") or {}

        rif = str(cliente.get("rif") or "").strip()
        nombre = str(cliente.get("nombre") or "").strip()
        direccion = str(cliente.get("direccion") or "").strip()
        tel = str(cliente.get("telefono") or cliente.get("telefonos") or "").strip()
        vend = str(vendedor.get("nombre") or "").strip()
        numero = str(inv.get("doc_numero") or inv.get("numero") or inv.get("doc") or "").strip()

        if rif:
            _send_cmd(impresora, f"iR*{rif}")

        if tipdoc in {"DEV", "NDE"}:
            afectada = inv.get("afectada") or {}
            numfis = str(afectada.get("numfis") or "").strip()
            fecha_fac = str(afectada.get("fecha") or afectada.get("fec_emis") or "").strip()
            imp_fis = str(afectada.get("impfis") or afectada.get("monto") or "").strip()
            if not numfis or not fecha_fac or not imp_fis:
                raise TfhkaError("DEV/NDE requieren afectada.numfis, afectada.fecha y afectada.impfis para iF*/iD*/iI*")
            _send_cmd(impresora, f"iF*{numfis}")
            _send_cmd(impresora, f"iD*{fecha_fac}")
            _send_cmd(impresora, f"iI*{imp_fis}")

        if nombre:
            _send_cmd(impresora, f"iS*{nombre}")
        if direccion:
            _send_cmd(impresora, f"i00Dirc: {direccion}")
        if tel:
            _send_cmd(impresora, f"i01Tlf: {tel}")
        if vend:
            _send_cmd(impresora, f"i02Vendedor: {vend}")
        if numero:
            _send_cmd(impresora, f"i03Numero: {numero}")

        items = inv.get("items") or []
        if not items:
            raise TfhkaError("Documento sin items")

        mostrar_codigo = (os.getenv("LEBRUN_FISCAL_SHOW_ITEM_CODE") or "0").strip() in {"1", "true", "True", "yes", "YES"}

        for it in items:
            codigo = str(it.get("codigo") or "").strip()
            nombre_it = str(it.get("nombre") or "").strip()
            desc = f"{codigo}-{nombre_it}" if (mostrar_codigo and codigo) else (nombre_it or codigo)
            desc = desc.strip()

            qty = _d(it.get("cantidad"), Decimal("0"))
            price = _d(it.get("precio"), Decimal("0"))
            desc_pct = _d(it.get("desc"), Decimal("0"))

            # Para evitar comandos q- (descuentos), imprimimos precio neto.
            if desc_pct > 0:
                price = (price * (Decimal("100") - desc_pct) / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            exento_raw = str(it.get("exento") or "").strip().lower()
            iva_pct = _d(it.get("iva_pct"), Decimal("0"))
            taxable = not (exento_raw in {"1", "si", "sí", "s", "true", "t", "y", "yes"} or iva_pct <= 0)

            cmd = _build_item_cmd(tipdoc=tipdoc, taxable=taxable, price=price, qty=qty, desc=desc, cfg=cfg)
            _send_cmd(impresora, cmd)

        _send_cmd(impresora, "3")
        _send_cmd(impresora, "101")

        pagos = inv.get("pagos") or []
        neto = _d(totales.get("neto"), Decimal("0"))

        aplica_igtf = bool(inv.get("aplicaigtf") or inv.get("aplica_igtf") or False)
        if not aplica_igtf:
            for p in pagos:
                m = str(p.get("modo") or "").lower()
                if "div" in m or "dol" in m or "$" in m:
                    aplica_igtf = True
                    break

        if pagos:
            for p in pagos:
                amt = _d(p.get("monto"), Decimal("0"))
                if amt <= 0:
                    continue
                mode = str(p.get("modo") or "")
                _send_cmd(impresora, _build_payment_cmd(mode=mode, amount=amt, cfg=cfg, aplica_igtf=aplica_igtf))
        else:
            if neto > 0:
                _send_cmd(impresora, _build_payment_cmd(mode="credito", amount=neto, cfg=cfg, aplica_igtf=aplica_igtf))

        if aplica_igtf:
            _send_cmd(impresora, "199")

        try:
            s1 = impresora.GetS1PrinterData()
            return PrintedDocInfo(
                registered_machine_number=str(getattr(s1, "RegisteredMachineNumber", "") or "") or None,
                last_invoice_number=str(getattr(s1, "LastInvoiceNumber", "") or "") or None,
                last_credit_note_number=str(getattr(s1, "LastCreditNoteNumber", "") or "") or None,
                last_debit_note_number=str(getattr(s1, "LastDebitNoteNumber", "") or "") or None,
                daily_closure_counter=str(getattr(s1, "DailyClosureCounter", "") or "") or None,
            )
        except Exception:
            return PrintedDocInfo()

    finally:
        if opened:
            try:
                impresora.CloseFpCtrl()
            except Exception:
                pass
