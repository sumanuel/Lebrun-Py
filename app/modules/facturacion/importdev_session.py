from __future__ import annotations

from dataclasses import dataclass


def _to_int(v: object, default: int = 0) -> int:
    try:
        return int(float(str(v).strip()))
    except Exception:
        return default


def _is_digits(s: str) -> bool:
    return bool(s) and s.isdigit()


def zpad(code: str, width: int) -> str:
    code = (code or "").strip()
    if _is_digits(code) and len(code) < width:
        return code.zfill(width)
    return code


def init_state(*, ref_numero: str, ref_codigo: str, tipo: str = "Parcial") -> dict:
    tipo = (tipo or "Parcial").strip().title()
    if tipo not in {"Parcial", "Total"}:
        tipo = "Parcial"

    return {
        "ref": {"numero": (ref_numero or "").strip(), "codigo": (ref_codigo or "").strip()},
        "tipo": tipo,
        "locked": False,
        "items": [],
        "reversados": [],
        "selected_codigo": "",
        "cantidad": "",
        "unidad": "",
        "supervisor": {"user": ""},
    }


def load_items(state: dict, items: list[dict]) -> None:
    # items: rows de adminvmov + adminv (ver Factura.itemsFac)
    norm = []
    for it in items or []:
        mov_cant = _to_int(it.get("mov_cant"))
        mov_export = _to_int(it.get("mov_export"))
        saldo = max(0, mov_cant - mov_export)
        norm.append(
            {
                "mov_item": str(it.get("mov_item") or ""),
                "mov_codigo": str(it.get("mov_codigo") or ""),
                "colProducto": str(it.get("colProducto") or ""),
                "mov_undmed": str(it.get("mov_undmed") or ""),
                "mov_cant": mov_cant,
                "mov_desc": str(it.get("mov_desc") or "0"),
                "mov_precio": str(it.get("mov_precio") or "0"),
                "mov_total": str(it.get("mov_total") or "0"),
                "mov_export": mov_export,
                "Saldo": saldo,
            }
        )
    state["items"] = norm


def can_total(state: dict) -> bool:
    # WinForms: no permite Total si algún item ya está exportado completo (mov_cant == Exportado)
    for it in state.get("items") or []:
        if _to_int(it.get("mov_cant")) == _to_int(it.get("mov_export")):
            return False
    return True


def select_item(state: dict, codigo: str) -> None:
    codigo = (codigo or "").strip()
    for it in state.get("items") or []:
        if str(it.get("mov_codigo") or "") == codigo:
            state["selected_codigo"] = codigo
            state["unidad"] = str(it.get("mov_undmed") or "")
            return


def add_reversado(state: dict, *, codigo: str, cantidad: int) -> str | None:
    codigo = (codigo or "").strip()
    if not codigo:
        return "Indique un producto."

    cantidad = max(0, int(cantidad or 0))
    if cantidad <= 0:
        return "Necesita una cantidad para reversar."

    items = state.get("items") or []
    target = None
    for it in items:
        if str(it.get("mov_codigo") or "") == codigo:
            target = it
            break

    if not target:
        return "Producto no pertenece a la factura."

    saldo = _to_int(target.get("Saldo"))
    if saldo <= 0:
        return "Ya se exportaron toda la cantidad de ítems para este artículo."

    if cantidad > saldo:
        return "La cantidad a reversar no puede ser mayor que la cantidad facturada."

    # WinForms: si agregas el mismo código, reemplaza (1 fila por producto)
    reversados = state.get("reversados") or []
    existing = None
    for r in reversados:
        if str(r.get("codigo") or "") == codigo:
            existing = r
            break

    if existing:
        prev = _to_int(existing.get("cant"))
        # devolver saldo previo
        target["Saldo"] = saldo + prev
        saldo = _to_int(target.get("Saldo"))
        if cantidad > saldo:
            # volver a poner como estaba
            target["Saldo"] = saldo - prev
            return "La cantidad a reversar no puede ser mayor que la cantidad facturada."
        existing["cant"] = cantidad
        existing["total"] = float(existing.get("precio") or 0) * cantidad
    else:
        reversados.append(
            {
                "mov_item": str(target.get("mov_item") or ""),
                "codigo": codigo,
                "producto": str(target.get("colProducto") or ""),
                "und": str(target.get("mov_undmed") or ""),
                "cant": cantidad,
                "precio": float(str(target.get("mov_precio") or "0").replace(",", ".")),
                "des": str(target.get("mov_desc") or "0"),
                "total": float(str(target.get("mov_precio") or "0").replace(",", ".")) * cantidad,
            }
        )
        state["reversados"] = reversados

    # actualizar saldo
    target["Saldo"] = _to_int(target.get("Saldo")) - cantidad
    state["selected_codigo"] = ""
    state["cantidad"] = ""
    state["unidad"] = ""
    return None


def remove_reversado(state: dict, codigo: str) -> None:
    codigo = (codigo or "").strip()
    reversados = state.get("reversados") or []
    removed = None
    kept = []
    for r in reversados:
        if str(r.get("codigo") or "") == codigo and removed is None:
            removed = r
        else:
            kept.append(r)

    state["reversados"] = kept
    if removed:
        # restaurar saldo
        for it in state.get("items") or []:
            if str(it.get("mov_codigo") or "") == codigo:
                it["Saldo"] = _to_int(it.get("Saldo")) + _to_int(removed.get("cant"))
                break


def total_fill(state: dict) -> None:
    # Agrega todos los items con su saldo pendiente
    state["reversados"] = []
    for it in state.get("items") or []:
        saldo = _to_int(it.get("Saldo"))
        if saldo > 0:
            add_reversado(state, codigo=str(it.get("mov_codigo") or ""), cantidad=saldo)


def clear(state: dict) -> dict:
    ref = state.get("ref") or {}
    return init_state(ref_numero=str(ref.get("numero") or ""), ref_codigo=str(ref.get("codigo") or ""), tipo=str(state.get("tipo") or "Parcial"))
