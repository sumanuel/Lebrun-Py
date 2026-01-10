from __future__ import annotations

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.core.config import settings
from app.core.exceptions import DatabaseUnavailable
from app.modules.facturacion.repository import FacturacionRepository
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
            menu = MenuService().build_menu(str(menu_map))
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
    limit: int = Query(100),
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
                limit=limit,
            )
        except DatabaseUnavailable as e:
            error = str(e)

    return templates.TemplateResponse(
        "facturacion/facturas.html",
        {
            "request": request,
            "user": user,
            "menu": menu,
            "active_href": "/facturacion/facturas",
            "title": "Facturas - Lebrun",
            "rows": rows,
            "error": error,
            "caja": caja,
            "tipdoc": (tipdoc or "FAV").strip().upper(),
            "q": q,
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

    # Stub seguro: solo registra la intención.
    request.session["flash"] = (
        f"Orden registrada: Reporte {action}. Próximo paso: integrar servicio local/impresora fiscal."
    )
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
def facturacion_factura_nueva(request: Request):
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
            "active_href": "/facturacion/factura/nueva",
            "title": "Nueva Factura - Lebrun",
            "page_title": "Nueva Factura",
            "message": "Stub: aquí irá la migración de frmFactura (FAV).",
            "numero": None,
            "codigo": None,
        },
    )


@router.get("/facturacion/devolucion/nueva", response_class=HTMLResponse)
def facturacion_devolucion_nueva(request: Request):
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
            "numero": None,
            "codigo": None,
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
