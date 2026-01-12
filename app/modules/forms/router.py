from __future__ import annotations

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.core.config import settings
from app.core.exceptions import DatabaseUnavailable
from app.modules.clientes.repository import ClientesRepository
from app.modules.facturacion.repository import FacturacionRepository
from app.modules.facturacion.factura_session import (
    add_item,
    add_pago,
    clear as clear_invoice,
    invoice_default,
    recalc,
    remove_item,
    remove_pago,
)
from app.modules.fiscal.service import FiscalService
from app.modules.menu.service import MenuService
from app.modules.ventas.repository import VentasRepository

router = APIRouter(tags=["forms"])
templates = Jinja2Templates(directory=str(settings.templates_dir))


def _require_user(request: Request):
    user = request.session.get("user")
    if not user:
        return None, RedirectResponse(url="/login", status_code=302)
    return user, None


def _load_menu(user: dict) -> list[dict]:
    menu = []
    menu_map = user.get("menu_map")
    if menu_map:
        try:
            menu = MenuService().build_menu(str(menu_map), user=user)
        except Exception:
            menu = []
    return menu


def _render_form_page(request: Request, title: str, description: str):
    user, redirect = _require_user(request)
    if redirect:
        return redirect

    menu = _load_menu(user)
    active_href = str(request.url.path)

    return templates.TemplateResponse(
        "form_page.html",
        {
            "request": request,
            "user": user,
            "menu": menu,
            "active_href": active_href,
            "title": f"{title} - Lebrun",
            "page_title": title,
            "description": description,
        },
    )


@router.get("/facturacion/facturas", response_class=HTMLResponse)
def facturacion_facturas(
    request: Request,
    tipdoc: str = Query("FAV"),
    q: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
):
    user, redirect = _require_user(request)
    if redirect:
        return redirect

    menu = _load_menu(user)
    caja = user.get("caja")

    rows: list[dict] = []
    error: str | None = None

    if not caja:
        error = "El usuario no tiene 'caja' asignada; no se puede listar facturas."
    else:
        try:
            rows = FacturacionRepository().list_documentos(
                caja=str(caja),
                tipdoc=str(tipdoc or "FAV"),
                q=(q or None),
                date_from=(date_from or None),
                date_to=(date_to or None),
                limit=100,
            )
        except DatabaseUnavailable as e:
            error = str(e)

    return templates.TemplateResponse(
        "facturacion/facturas.html",
        {
            "request": request,
            "user": user,
            "menu": menu,
            "active_href": f"/facturacion/facturas?tipdoc={(tipdoc or 'FAV').strip().upper()}",
            "title": "Facturas - Lebrun",
            "rows": rows,
            "error": error,
            "caja": caja,
            "tipdoc": (tipdoc or "FAV").strip().upper(),
            "q": q,
            "date_from": date_from,
            "date_to": date_to,
        },
    )


@router.get("/ventas/visor-precios", response_class=HTMLResponse)
def ventas_visor_precios(
    request: Request,
    q: str | None = Query(None),
    by: str = Query("descripcion"),
    limit: int = Query(100),
):
    user, redirect = _require_user(request)
    if redirect:
        return redirect

    menu = _load_menu(user)

    rows: list[dict] = []
    error: str | None = None
    try:
        rows = VentasRepository().list_productos(q=(q or None), by=by, limit=limit)
    except DatabaseUnavailable as e:
        error = str(e)

    return templates.TemplateResponse(
        "ventas/visor_precios.html",
        {
            "request": request,
            "user": user,
            "menu": menu,
            "active_href": "/ventas/visor-precios",
            "title": "Visor de Precios - Lebrun",
            "rows": rows,
            "error": error,
            "q": q,
            "by": (by or "descripcion").strip().lower(),
        },
    )


@router.get("/ventas/consulta-articulos", response_class=HTMLResponse)
def ventas_consulta_articulos(request: Request):
    # Alias más explícito para el WinForms `frmConsultaArticulos`.
    user, redirect = _require_user(request)
    if redirect:
        return redirect
    return RedirectResponse(url="/ventas/visor-precios", status_code=302)


@router.get("/facturacion/reportes/zx", response_class=HTMLResponse)
def facturacion_reportes_zx(request: Request):
    user, redirect = _require_user(request)
    if redirect:
        return redirect

    menu = _load_menu(user)
    message = request.session.pop("flash", None)

    return templates.TemplateResponse(
        "facturacion/reportes_zx.html",
        {
            "request": request,
            "user": user,
            "menu": menu,
            "active_href": "/facturacion/reportes/zx",
            "title": "Reportes Z/X - Lebrun",
            "message": message,
            "error": None,
        },
    )


@router.post("/facturacion/reportes/zx")
def facturacion_reportes_zx_post(request: Request, action: str = Form("")):
    user, redirect = _require_user(request)
    if redirect:
        return redirect

    action = (action or "").strip().upper()
    if action not in {"X", "Z"}:
        request.session["flash"] = "Acción inválida."
        return RedirectResponse(url="/facturacion/reportes/zx", status_code=303)

    caja = user.get("caja")
    try:
        job_id = FiscalService().enqueue_report(
            caja=str(caja) if caja is not None else None,
            report_type=action,
            requested_by=str(user.get("username") or ""),
        )
        request.session["flash"] = f"Orden encolada: Reporte {action}. Job: {job_id}"
    except Exception as e:
        request.session["flash"] = f"No se pudo encolar el reporte: {e}"
    return RedirectResponse(url="/facturacion/reportes/zx", status_code=303)


@router.get("/facturacion/reportes/zx/run")
def facturacion_reportes_zx_run(request: Request, action: str = Query("")):
    # Permite que un item de menú "Reporte X" / "Reporte Z" ejecute directo.
    user, redirect = _require_user(request)
    if redirect:
        return redirect

    action = (action or "").strip().upper()
    if action not in {"X", "Z"}:
        request.session["flash"] = "Acción inválida."
        return RedirectResponse(url="/facturacion/reportes/zx", status_code=303)

    caja = user.get("caja")
    try:
        job_id = FiscalService().enqueue_report(
            caja=str(caja) if caja is not None else None,
            report_type=action,
            requested_by=str(user.get("username") or ""),
        )
        request.session["flash"] = f"Orden encolada: Reporte {action}. Job: {job_id}"
    except Exception as e:
        request.session["flash"] = f"No se pudo encolar el reporte: {e}"
    return RedirectResponse(url="/facturacion/reportes/zx", status_code=303)


@router.get("/facturacion/cierre-caja", response_class=HTMLResponse)
def facturacion_cierre_caja(request: Request):
    user, redirect = _require_user(request)
    if redirect:
        return redirect

    menu = _load_menu(user)
    message = request.session.pop("flash", None)
    caja = user.get("caja")

    return templates.TemplateResponse(
        "facturacion/cierre_caja.html",
        {
            "request": request,
            "user": user,
            "menu": menu,
            "active_href": "/facturacion/cierre-caja",
            "title": "Cierre de Caja - Lebrun",
            "message": message,
            "error": None,
            "caja": caja,
        },
    )


@router.post("/facturacion/cierre-caja")
def facturacion_cierre_caja_post(request: Request):
    user, redirect = _require_user(request)
    if redirect:
        return redirect

    # Stub: en WinForms esto valida caja activa y genera reporte.
    caja = user.get("caja")
    if not caja:
        request.session["flash"] = "No se puede cerrar: usuario sin caja asignada."
    else:
        request.session["flash"] = (
            f"Solicitud registrada: cierre de caja {caja}. Próximo paso: migrar lógica de cierre + reportes."
        )
    return RedirectResponse(url="/facturacion/cierre-caja", status_code=303)


@router.get("/facturacion/clave-confirmacion", response_class=HTMLResponse)
def facturacion_clave_confirmacion(request: Request):
    user, redirect = _require_user(request)
    if redirect:
        return redirect

    menu = _load_menu(user)
    message = request.session.pop("flash", None)

    return templates.TemplateResponse(
        "facturacion/clave_confirmacion.html",
        {
            "request": request,
            "user": user,
            "menu": menu,
            "active_href": "/facturacion/clave-confirmacion",
            "title": "Clave de Confirmación - Lebrun",
            "message": message,
            "error": None,
        },
    )


@router.post("/facturacion/clave-confirmacion")
def facturacion_clave_confirmacion_post(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
):
    user, redirect = _require_user(request)
    if redirect:
        return redirect

    # Stub: validación real pendiente (supervisión/permisos).
    if not (username or "").strip() or not (password or "").strip():
        request.session["flash"] = "Debe indicar usuario y contraseña."
        return RedirectResponse(url="/facturacion/clave-confirmacion", status_code=303)

    request.session["flash"] = "Confirmación registrada (stub). Próximo paso: validar supervisor en sysconf + permisos."
    return RedirectResponse(url="/facturacion/clave-confirmacion", status_code=303)


@router.get("/facturacion/importar-devolucion", response_class=HTMLResponse)
def facturacion_importar_devolucion(request: Request, q: str | None = Query(None)):
    user, redirect = _require_user(request)
    if redirect:
        return redirect

    menu = _load_menu(user)
    message = request.session.pop("flash", None)

    return templates.TemplateResponse(
        "facturacion/importar_devolucion.html",
        {
            "request": request,
            "user": user,
            "menu": menu,
            "active_href": "/facturacion/importar-devolucion",
            "title": "Importar Devolución - Lebrun",
            "message": message,
            "error": None,
            "q": q,
        },
    )


@router.get("/facturacion/factura/nueva", response_class=HTMLResponse)
def facturacion_factura_nueva(request: Request, tipdoc: str = Query("FAV")):
    user, redirect = _require_user(request)
    if redirect:
        return redirect
    menu = _load_menu(user)

    tipdoc = (tipdoc or "FAV").strip().upper() or "FAV"
    if tipdoc not in {"FAV", "DEV", "NDE"}:
        tipdoc = "FAV"

    inv = request.session.get("factura")
    if not isinstance(inv, dict):
        inv = invoice_default(tipdoc)
    inv["tipdoc"] = tipdoc
    recalc(inv)
    request.session["factura"] = inv

    return templates.TemplateResponse(
        "facturacion/frm_factura.html",
        {
            "request": request,
            "user": user,
            "menu": menu,
            "active_href": "/facturacion/factura/nueva",
            "title": "Factura - Lebrun",
            "page_title": "Factura",
            "message": None,
            "inv": inv,
        },
    )


@router.post("/facturacion/factura/nueva", response_class=HTMLResponse)
def facturacion_factura_nueva_post(
    request: Request,
    tipdoc: str = Form("FAV"),
    action: str = Form(""),
    # cliente
    cli_codigo: str = Form(""),
    # producto
    prod_codigo: str = Form(""),
    prod_cantidad: str = Form("1"),
    prod_precio: str = Form(""),
    prod_desc: str = Form("0"),
    remove_item_idx: str = Form(""),
    # pago
    pago_modo: str = Form("Efectivo"),
    pago_banco: str = Form(""),
    pago_ref: str = Form(""),
    pago_monto: str = Form(""),
    remove_pago_idx: str = Form(""),
):
    user, redirect = _require_user(request)
    if redirect:
        return redirect

    menu = _load_menu(user)

    tipdoc = (tipdoc or "FAV").strip().upper() or "FAV"
    if tipdoc not in {"FAV", "DEV", "NDE"}:
        tipdoc = "FAV"

    inv = request.session.get("factura")
    if not isinstance(inv, dict):
        inv = invoice_default(tipdoc)
    inv["tipdoc"] = tipdoc

    action = (action or "").strip().lower()
    message: str | None = None

    try:
        if action == "buscar_cliente":
            cli_codigo = (cli_codigo or "").strip()
            if not cli_codigo:
                message = "Indique un código de cliente."
            else:
                row = ClientesRepository().get_cliente(codigo=cli_codigo)
                if not row:
                    message = f"Cliente no encontrado: {cli_codigo}"
                else:
                    inv["cliente"] = {
                        "codigo": str(row.get("cli_codigo") or ""),
                        "rif": str(row.get("cli_rif") or ""),
                        "nombre": str(row.get("cli_nombre") or ""),
                        "direccion": str(row.get("cli_direcc") or ""),
                    }
        elif action == "agregar_item":
            code = (prod_codigo or "").strip()
            if not code:
                message = "Indique un código de producto."
            else:
                prod = VentasRepository().get_producto_by_codigo(codigo=code)
                if not prod:
                    message = f"Producto no encontrado: {code}"
                else:
                    precio = prod_precio.strip() if (prod_precio or "").strip() else str(prod.get("Precio") or "0")
                    add_item(
                        inv,
                        producto={
                            "codigo": prod.get("Codigo"),
                            "descripcion": prod.get("Descripcion"),
                            "unidad": prod.get("Unidad"),
                        },
                        cantidad=prod_cantidad,
                        precio=precio,
                        desc_pct=prod_desc,
                    )
                    inv["producto"] = {"codigo": "", "nombre": "", "unidad": "", "cantidad": "1", "precio": ""}
        elif action == "eliminar_item":
            remove_item(inv, remove_item_idx)
        elif action == "agregar_pago":
            modo = (pago_modo or "").strip()
            if not (pago_monto or "").strip():
                message = "Indique monto a abonar."
            else:
                # Reglas simples (WinForms exige banco+numero si no es efectivo)
                if modo.lower() != "efectivo":
                    if not (pago_banco or "").strip() or not (pago_ref or "").strip():
                        message = "Para este modo de pago debe indicar banco y número/referencia."
                    else:
                        add_pago(inv, modo=modo, banco=pago_banco, referencia=pago_ref, monto=pago_monto)
                else:
                    add_pago(inv, modo=modo, banco="N/A", referencia="N/A", monto=pago_monto)
        elif action == "eliminar_pago":
            remove_pago(inv, remove_pago_idx)
        elif action == "limpiar":
            inv = clear_invoice(inv)
            inv["tipdoc"] = tipdoc
        else:
            # action vacío o no soportado: no hacer nada
            pass
    except DatabaseUnavailable as e:
        message = str(e)
    except Exception as e:
        message = str(e)

    recalc(inv)
    request.session["factura"] = inv

    return templates.TemplateResponse(
        "facturacion/frm_factura.html",
        {
            "request": request,
            "user": user,
            "menu": menu,
            "active_href": "/facturacion/factura/nueva",
            "title": "Factura - Lebrun",
            "page_title": "Factura",
            "message": message,
            "inv": inv,
        },
    )


@router.get("/facturacion/devolucion/nueva", response_class=HTMLResponse)
def facturacion_devolucion_nueva(
    request: Request,
    ref_numero: str | None = Query(None),
    ref_codigo: str | None = Query(None),
):
    user, redirect = _require_user(request)
    if redirect:
        return redirect
    menu = _load_menu(user)
    return templates.TemplateResponse(
        "facturacion/factura_stub.html",
        {
            "request": request,
            "user": user,
            "menu": menu,
            "active_href": "/facturacion/devolucion/nueva",
            "title": "Nueva Devolución - Lebrun",
            "page_title": "Nueva Devolución",
            "message": "Stub: aquí irá la creación de DEV y el flujo de importación parcial/total.",
            "numero": ref_numero,
            "codigo": ref_codigo,
        },
    )


@router.get("/facturacion/facturas/ver", response_class=HTMLResponse)
def facturacion_facturas_ver(
    request: Request,
    numero: str | None = Query(None),
    codigo: str | None = Query(None),
):
    user, redirect = _require_user(request)
    if redirect:
        return redirect
    menu = _load_menu(user)
    return templates.TemplateResponse(
        "facturacion/factura_stub.html",
        {
            "request": request,
            "user": user,
            "menu": menu,
            "active_href": "/facturacion/facturas",
            "title": "Ver Documento - Lebrun",
            "page_title": "Ver Documento",
            "message": "Stub: ver detalle del documento (cabecera + items).",
            "numero": numero,
            "codigo": codigo,
        },
    )


@router.get("/facturacion/facturas/imprimir", response_class=HTMLResponse)
def facturacion_facturas_imprimir(
    request: Request,
    numero: str | None = Query(None),
    codigo: str | None = Query(None),
):
    user, redirect = _require_user(request)
    if redirect:
        return redirect
    menu = _load_menu(user)
    return templates.TemplateResponse(
        "facturacion/factura_stub.html",
        {
            "request": request,
            "user": user,
            "menu": menu,
            "active_href": "/facturacion/facturas",
            "title": "Imprimir Documento - Lebrun",
            "page_title": "Imprimir Documento",
            "message": "Stub: aquí irá la integración de impresión (fiscal/no fiscal).",
            "numero": numero,
            "codigo": codigo,
        },
    )


@router.get("/ventas/pagare", response_class=HTMLResponse)
def ventas_pagare(request: Request):
    return _render_form_page(
        request,
        title="Pagaré",
        description="Registro y consulta de pagarés. Implementación inicial: UI + navegación.",
    )


@router.get("/administracion/parametros-contables", response_class=HTMLResponse)
def admin_parametros_contables(request: Request):
    return _render_form_page(
        request,
        title="Parámetros Contables",
        description="Parámetros base de contabilidad. Implementación inicial: UI + navegación.",
    )


@router.get("/contabilidad/plan-cuentas", response_class=HTMLResponse)
def conta_plan_cuentas(request: Request):
    return _render_form_page(
        request,
        title="Plan de Cuentas",
        description="Consulta del plan de cuentas. Implementación inicial: UI + navegación.",
    )


@router.get("/contabilidad/comprobante-cierre", response_class=HTMLResponse)
def conta_comprobante_cierre(request: Request):
    return _render_form_page(
        request,
        title="Comprobante de Cierre",
        description="Consulta/gestión de comprobantes de cierre. Implementación inicial: UI + navegación.",
    )
