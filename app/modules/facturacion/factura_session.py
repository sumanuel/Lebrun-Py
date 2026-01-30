from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_DOWN


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


def _clamp_int(v: object, default: int = 1, min_v: int = 0, max_v: int = 10_000) -> int:
    try:
        n = int(str(v).strip())
    except Exception:
        return default
    return max(min_v, min(max_v, n))


def _trunc(v: Decimal, places: int = 6) -> Decimal:
    q = Decimal("1") if places <= 0 else Decimal("1").scaleb(-places)
    return v.quantize(q, rounding=ROUND_DOWN)


def _is_exento(v: object) -> bool:
    s = str(v or "").strip().lower()
    return s in {"1", "si", "sí", "s", "true", "t", "y", "yes"}


def invoice_default(tipdoc: str = "FAV") -> dict:
    return {
        "tipdoc": (tipdoc or "FAV").strip().upper() or "FAV",
        "fecha": date.today().isoformat(),
        "cliente": {"codigo": "", "rif": "", "nombre": "", "direccion": ""},
        "cliente_locked": False,
        "vendedor": {"codigo": "", "nombre": ""},
        "afectada": {"numero": "", "codigo": "", "numfis": ""},
        "afectada_locked": False,
        "obs": "",
        "cambio_precio": False,
        "producto": {"codigo": "", "nombre": "", "unidad": "", "cantidad": "1", "precio": ""},
        "items": [],
        "pagos": [],
        "totales": {
            "subtotal": "0.00",
            "des_items": "0.00",
            "base": "0.00",
            "total_prod": "0.00",
            "iva": "0.00",
            "neto": "0.00",
            "pagado": "0.00",
            "cambio": "0.00",
            "efectivo": "0.00",
            "cheques": "0.00",
            "tarjetas": "0.00",
        },
    }


def recalc(invoice: dict) -> None:
    items = invoice.get("items") or []
    pagos = invoice.get("pagos") or []

    subtotal = Decimal("0")
    total_prod = Decimal("0")
    des_items = Decimal("0")
    iva = Decimal("0")

    for it in items:
        qty = _d(it.get("cantidad"), Decimal("0"))
        price = _d(it.get("precio"), Decimal("0"))
        desc_pct = _d(it.get("desc"), Decimal("0"))
        line = qty * price
        disc = (line * (desc_pct / Decimal("100"))) if desc_pct > 0 else Decimal("0")
        total = line - disc

        exento = _is_exento(it.get("exento"))
        iva_pct = _d(it.get("iva_pct"), Decimal("0"))
        line_iva = Decimal("0") if (exento or iva_pct <= 0) else _trunc((total * iva_pct) / Decimal("100"), 6)
        it["iva"] = f"{line_iva:.6f}"

        it["total"] = f"{total:.2f}"
        subtotal += line
        des_items += disc
        total_prod += qty
        iva += line_iva

    base = subtotal - des_items
    neto = base + iva

    pagado = Decimal("0")
    efectivo = Decimal("0")
    cheques = Decimal("0")
    tarjetas = Decimal("0")

    for p in pagos:
        amt = _d(p.get("monto"), Decimal("0"))
        pagado += amt
        mode = str(p.get("modo") or "").strip().lower()
        if mode == "efectivo":
            efectivo += amt
        elif "cheque" in mode:
            cheques += amt
        elif "tarjeta" in mode:
            tarjetas += amt

    cambio = pagado - neto if pagado > neto else Decimal("0")

    invoice["totales"] = {
        "subtotal": f"{subtotal:.2f}",
        "des_items": f"{des_items:.2f}",
        "base": f"{base:.2f}",
        "total_prod": f"{total_prod:.2f}",
        "iva": f"{iva:.2f}",
        "neto": f"{neto:.2f}",
        "pagado": f"{pagado:.2f}",
        "cambio": f"{cambio:.2f}",
        "efectivo": f"{efectivo:.2f}",
        "cheques": f"{cheques:.2f}",
        "tarjetas": f"{tarjetas:.2f}",
    }


def add_item(invoice: dict, *, producto: dict, cantidad: object, precio: object, desc_pct: object = 0) -> None:
    items = invoice.setdefault("items", [])

    qty = _d(cantidad, Decimal("1"))
    if qty <= 0:
        qty = Decimal("1")

    pr = _d(precio, Decimal("0"))

    items.append(
        {
            "codigo": str(producto.get("codigo") or ""),
            "nombre": str(producto.get("descripcion") or producto.get("nombre") or ""),
            "unidad": str(producto.get("unidad") or ""),
            "exento": str(producto.get("exento") or ""),
            "iva_tipo": str(producto.get("iva_tipo") or ""),
            "iva_pct": f"{_d(producto.get('iva_pct'), Decimal('0')):.2f}",
            "cantidad": f"{qty:.2f}",
            "precio": f"{pr:.2f}",
            "desc": f"{_d(desc_pct, Decimal('0')):.2f}",
            "total": "0.00",
            "iva": "0.000000",
        }
    )
    recalc(invoice)


def remove_item(invoice: dict, idx: object) -> None:
    items = invoice.get("items") or []
    i = _clamp_int(idx, default=-1, min_v=-1, max_v=10_000)
    if 0 <= i < len(items):
        items.pop(i)
    invoice["items"] = items
    recalc(invoice)


def add_pago(invoice: dict, *, modo: str, banco: str, referencia: str, monto: object) -> None:
    pagos = invoice.setdefault("pagos", [])
    pagos.append(
        {
            "modo": (modo or "").strip(),
            "banco": (banco or "").strip(),
            "referencia": (referencia or "").strip(),
            "monto": f"{_d(monto, Decimal('0')):.2f}",
        }
    )
    recalc(invoice)


def remove_pago(invoice: dict, idx: object) -> None:
    pagos = invoice.get("pagos") or []
    i = _clamp_int(idx, default=-1, min_v=-1, max_v=10_000)
    if 0 <= i < len(pagos):
        pagos.pop(i)
    invoice["pagos"] = pagos
    recalc(invoice)


def clear(invoice: dict) -> dict:
    tipdoc = str(invoice.get("tipdoc") or "FAV")
    return invoice_default(tipdoc)
