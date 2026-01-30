from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from app.core.config import settings
from app.core.exceptions import DatabaseUnavailable
from app.modules.clientes.repository import ClientesRepository
from app.modules.bancos.repository import BancosRepository
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
from app.modules.facturacion.importdev_session import (
    add_reversado,
    can_total as importdev_can_total,
    clear as importdev_clear,
    init_state as importdev_init_state,
    load_items as importdev_load_items,
    remove_reversado as importdev_remove_reversado,
    select_item as importdev_select_item,
    total_fill as importdev_total_fill,
    zpad,
)
from app.modules.fiscal.service import FiscalService
from app.modules.menu.service import MenuService
from app.modules.vendedores.repository import VendedoresRepository
from app.modules.ventas.repository import VentasRepository
from app.modules.facturacion.save_service import InvoiceSaveService

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


def _get_importdev_state(request: Request) -> dict | None:
    st = request.session.get("importdev")
    return st if isinstance(st, dict) else None


def _set_importdev_state(request: Request, state: dict) -> None:
    request.session["importdev"] = state


def _ensure_importdev_loaded(
    *,
    request: Request,
    ref_numero: str,
    ref_codigo: str,
    tipo: str,
) -> tuple[dict, dict | None, str | None]:
    """Inicializa/carga la devolución desde DB a sesión.

    Devuelve: (state, ref, error)
    """

    tipo = (tipo or "Parcial").strip().title()
    if tipo not in {"Parcial", "Total"}:
        tipo = "Parcial"

    state = _get_importdev_state(request)
    if not state or (state.get("ref") or {}).get("numero") != ref_numero or (state.get("ref") or {}).get("codigo") != ref_codigo:
        state = importdev_init_state(ref_numero=ref_numero, ref_codigo=ref_codigo, tipo=tipo)

    if not state.get("locked"):
        state["tipo"] = tipo

    error: str | None = None
    ref: dict | None = None

    try:
        repo = FacturacionRepository()
        ref = repo.get_documento_header(numero=ref_numero, codigo=ref_codigo)
        items = repo.list_items_factura_afectada(numero=ref_numero, codigo=ref_codigo, tipdoc="FAV")
        importdev_load_items(state, items)
        state["ref"]["numero"] = ref_numero
        state["ref"]["codigo"] = ref_codigo
        state["ref"]["numfis"] = str((ref or {}).get("dcli_numfis") or "")

        # Vendor de la factura afectada: tomamos el primero (en WinForms viene de facDev.VendedorFactura).
        vend = ""
        for it in items or []:
            vend = str(it.get("mov_vendedor") or "").strip()
            if vend:
                break
        state["ref"]["vendedor"] = vend
    except DatabaseUnavailable as e:
        error = str(e)
    except Exception as e:
        error = str(e)

    _set_importdev_state(request, state)
    return state, ref, error


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
            "today": date.today().isoformat(),
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
def facturacion_clave_confirmacion(
    request: Request,
    next: str | None = Query(None),
    scope: str | None = Query(None),
):
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
            "next": next or "",
            "scope": (scope or "").strip().lower(),
        },
    )


@router.post("/facturacion/clave-confirmacion")
def facturacion_clave_confirmacion_post(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
    next: str = Form(""),
    scope: str = Form(""),
):
    user, redirect = _require_user(request)
    if redirect:
        return redirect

    # Stub: validación real pendiente (supervisión/permisos).
    if not (username or "").strip() or not (password or "").strip():
        request.session["flash"] = "Debe indicar usuario y contraseña."
        return RedirectResponse(url="/facturacion/clave-confirmacion", status_code=303)

    scope_norm = (scope or "").strip().lower() or "importdev"

    if scope_norm == "factura":
        request.session["factura_supervisor_ok"] = True
        request.session["factura_supervisor_user"] = (username or "").strip()
    else:
        # Marcador para flujos que requieren supervisor (ej: importar devolución Total)
        request.session["importdev_supervisor_ok"] = True
        request.session["importdev_supervisor_user"] = (username or "").strip()

    request.session["flash"] = "Confirmación registrada (stub)."
    if (next or "").strip():
        return RedirectResponse(url=next.strip(), status_code=303)
    return RedirectResponse(url="/facturacion/clave-confirmacion", status_code=303)


@router.get("/facturacion/importar-devolucion", response_class=HTMLResponse)
def facturacion_importar_devolucion(
    request: Request,
    q: str | None = Query(None),
    ref_numero: str | None = Query(None),
    ref_codigo: str | None = Query(None),
    tipo: str | None = Query(None),
):
    user, redirect = _require_user(request)
    if redirect:
        return redirect

    menu = _load_menu(user)
    message = request.session.pop("flash", None)

    error: str | None = None
    ref: dict | None = None

    ref_numero_s = (ref_numero or "").strip() if ref_numero else ""
    ref_codigo_s = (ref_codigo or "").strip() if ref_codigo else ""
    tipo_norm = (tipo or "Parcial").strip().title()
    if tipo_norm not in {"Parcial", "Total"}:
        tipo_norm = "Parcial"

    state = _get_importdev_state(request)

    if ref_numero_s and ref_codigo_s:
        state, ref, error = _ensure_importdev_loaded(
            request=request,
            ref_numero=ref_numero_s,
            ref_codigo=ref_codigo_s,
            tipo=tipo_norm,
        )
    else:
        # Sin referencia: mostrar pantalla vacía.
        if not state or (state.get("ref") or {}).get("numero") or (state.get("ref") or {}).get("codigo"):
            state = importdev_init_state(ref_numero="", ref_codigo="", tipo=tipo_norm)
            _set_importdev_state(request, state)

    # Si venimos de una confirmación de supervisor para Total, ejecutar el equivalente a despuesConfirmacion(true,...)
    if state and state.get("pending_total") and request.session.get("importdev_supervisor_ok"):
        if not state.get("locked"):
            if importdev_can_total(state):
                importdev_total_fill(state)
                state["locked"] = True
            else:
                request.session["flash"] = "No se puede Procesar la devolución Total!!"
        state["pending_total"] = False
        request.session.pop("importdev_supervisor_ok", None)
        request.session.pop("importdev_supervisor_user", None)
        _set_importdev_state(request, state)

    items = (state.get("items") or []) if state else []
    reversados = (state.get("reversados") or []) if state else []

    selected_codigo = str((state or {}).get("selected_codigo") or "")
    selected_item = None
    if selected_codigo:
        for it in items:
            if str(it.get("mov_codigo") or "") == selected_codigo:
                selected_item = it
                break

    return templates.TemplateResponse(
        "facturacion/importar_devolucion.html",
        {
            "request": request,
            "user": user,
            "menu": menu,
            "active_href": "/facturacion/importar-devolucion",
            "title": "Importar Devolución - Lebrun",
            "message": message,
            "error": error,
            "q": q,
            "ref": ref,
            "items": items,
            "reversados": reversados,
            "tipo": str((state or {}).get("tipo") or tipo_norm),
            "ref_numero": ref_numero_s,
            "ref_codigo": ref_codigo_s,
            "locked": bool((state or {}).get("locked")),
            "selected_codigo": selected_codigo,
            "selected_item": selected_item,
        },
    )


@router.post("/facturacion/importar-devolucion")
def facturacion_importar_devolucion_post(
    request: Request,
    action: str = Form(""),
    ref_numero: str = Form(""),
    ref_codigo: str = Form(""),
    tipo: str = Form("Parcial"),
    sel_codigo: str = Form(""),
    cant: str = Form(""),
    del_codigo: str = Form(""),
):
    user, redirect = _require_user(request)
    if redirect:
        return redirect

    ref_numero_s = (ref_numero or "").strip()
    ref_codigo_s = (ref_codigo or "").strip()
    tipo_norm = (tipo or "Parcial").strip().title()
    if tipo_norm not in {"Parcial", "Total"}:
        tipo_norm = "Parcial"

    if not ref_numero_s or not ref_codigo_s:
        request.session["flash"] = "Indique Num Fac + Cliente y presione Aceptar."
        return RedirectResponse(url="/facturacion/importar-devolucion", status_code=303)

    state, _ref, error = _ensure_importdev_loaded(
        request=request,
        ref_numero=ref_numero_s,
        ref_codigo=ref_codigo_s,
        tipo=tipo_norm,
    )

    if error:
        request.session["flash"] = error
        return RedirectResponse(
            url=f"/facturacion/importar-devolucion?ref_numero={ref_numero_s}&ref_codigo={ref_codigo_s}&tipo={tipo_norm}",
            status_code=303,
        )

    action = (action or "").strip().lower()

    if action == "select_item":
        if not state.get("locked"):
            importdev_select_item(state, sel_codigo)

    elif action == "add_reversado":
        if state.get("locked"):
            request.session["flash"] = "La devolución está bloqueada. Use Reset si necesita cambiar."
        else:
            codigo = (sel_codigo or "").strip() or str(state.get("selected_codigo") or "").strip()
            try:
                cantidad = int(float((cant or "0").strip() or "0"))
            except Exception:
                cantidad = 0
            msg = add_reversado(state, codigo=codigo, cantidad=cantidad)
            if msg:
                request.session["flash"] = msg

    elif action == "remove_reversado":
        if not state.get("locked"):
            importdev_remove_reversado(state, del_codigo)

    elif action == "reset":
        state = importdev_clear(state)

    elif action == "procesar_total":
        if state.get("locked"):
            request.session["flash"] = "La devolución ya fue procesada."
        else:
            if not importdev_can_total(state):
                request.session["flash"] = "No se puede Procesar la devolución Total!!"
            else:
                state["pending_total"] = True
                _set_importdev_state(request, state)
                next_url = f"/facturacion/importar-devolucion?ref_numero={ref_numero_s}&ref_codigo={ref_codigo_s}&tipo=Total"
                return RedirectResponse(url=f"/facturacion/clave-confirmacion?next={next_url}", status_code=303)

    elif action == "aceptar_devolucion":
        if not (state.get("reversados") or []):
            request.session["flash"] = "Debe agregar items a reversar."
        else:
            # Crear documento DEV en sesión usando la pantalla de factura.
            inv = invoice_default("DEV")
            # cliente
            cli = ClientesRepository().get_cliente(codigo=ref_codigo_s)
            if cli:
                inv["cliente"] = {
                    "codigo": str(cli.get("cli_codigo") or ""),
                    "rif": str(cli.get("cli_rif") or ""),
                    "nombre": str(cli.get("cli_nombre") or ""),
                    "direccion": str(cli.get("cli_direcc") or ""),
                }
            # vendedor
            vend_code = zpad(str((state.get("ref") or {}).get("vendedor") or ""), 10)
            if vend_code:
                vend = VendedoresRepository().get_vendedor(codigo=vend_code)
                inv["vendedor"] = {"codigo": vend_code, "nombre": str((vend or {}).get("ven_nombre") or "")}

            # referencia afectada (para mostrar y/o usar en guardar luego)
            inv["afectada"] = {
                "numero": ref_numero_s,
                "codigo": ref_codigo_s,
                "numfis": str((state.get("ref") or {}).get("numfis") or ""),
            }

            for r in state.get("reversados") or []:
                add_item(
                    inv,
                    producto={
                        "codigo": str(r.get("codigo") or ""),
                        "descripcion": str(r.get("producto") or ""),
                        "unidad": str(r.get("und") or ""),
                    },
                    cantidad=str(r.get("cant") or "0"),
                    precio=str(r.get("precio") or "0"),
                    desc_pct=str(r.get("des") or "0"),
                )

            recalc(inv)
            request.session["factura"] = inv
            request.session["flash"] = "Devolución preparada. Revise y confirme el documento."
            return RedirectResponse(url="/facturacion/factura/nueva?tipdoc=DEV", status_code=303)

    _set_importdev_state(request, state)
    return RedirectResponse(
        url=f"/facturacion/importar-devolucion?ref_numero={ref_numero_s}&ref_codigo={ref_codigo_s}&tipo={tipo_norm}",
        status_code=303,
    )


@router.get("/api/lookups/clientes")
def api_lookup_clientes(request: Request, q: str = Query("")):
    user, redirect = _require_user(request)
    if redirect:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    q = (q or "").strip()

    try:
        repo = ClientesRepository()
        items = repo.search(q=q, limit=80)
        return {"items": items}
    except DatabaseUnavailable as e:
        return JSONResponse({"error": str(e), "items": []}, status_code=503)


@router.get("/api/lookups/vendedores")
def api_lookup_vendedores(request: Request, q: str = Query("")):
    user, redirect = _require_user(request)
    if redirect:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        items = VendedoresRepository().search(q=(q or "").strip(), limit=50)
        return {"items": items}
    except DatabaseUnavailable as e:
        return JSONResponse({"error": str(e), "items": []}, status_code=503)


@router.get("/api/lookups/productos")
def api_lookup_productos(request: Request, q: str = Query(""), by: str = Query("descripcion")):
    user, redirect = _require_user(request)
    if redirect:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    by = (by or "descripcion").strip().lower()
    try:
        rows = VentasRepository().list_productos(q=(q or "").strip() or None, by=by, limit=80)
        return {"items": rows}
    except DatabaseUnavailable as e:
        return JSONResponse({"error": str(e), "items": []}, status_code=503)


@router.get("/api/lookups/bancos")
def api_lookup_bancos(request: Request, q: str = Query("")):
    user, redirect = _require_user(request)
    if redirect:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        items = BancosRepository().search(q=(q or "").strip(), limit=80)
        return {"items": items}
    except DatabaseUnavailable as e:
        return JSONResponse({"error": str(e), "items": []}, status_code=503)


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
    inv.setdefault("pago_form", {"modo": "Efectivo", "banco": "", "ref": "", "monto": ""})
    recalc(inv)
    request.session["factura"] = inv

    message = request.session.pop("flash", None)

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
            "hide_topbar": True,
        },
    )


@router.post("/facturacion/factura/nueva", response_class=HTMLResponse)
def facturacion_factura_nueva_post(
    request: Request,
    tipdoc: str = Form("FAV"),
    action: str = Form(""),
    # cliente
    cli_codigo: str = Form(""),
    # vendedor
    vend_codigo: str = Form(""),
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
    inv.setdefault("pago_form", {"modo": "Efectivo", "banco": "", "ref": "", "monto": ""})

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
        elif action == "buscar_vendedor":
            vend_codigo = zpad((vend_codigo or "").strip(), 10)
            if not vend_codigo:
                message = "Indique un código de vendedor."
            else:
                row = VendedoresRepository().get_vendedor(codigo=vend_codigo)
                if not row:
                    message = f"Vendedor no encontrado: {vend_codigo}"
                else:
                    inv["vendedor"] = {
                        "codigo": str(row.get("ven_codigo") or ""),
                        "nombre": str(row.get("ven_nombre") or ""),
                    }
        elif action == "buscar_producto":
            code = zpad((prod_codigo or "").strip(), 15)
            if not code:
                message = "Indique un código de producto."
            else:
                prod = VentasRepository().get_producto_by_codigo(codigo=code)
                if not prod:
                    message = f"Producto no encontrado: {code}"
                    inv["producto"] = {"codigo": code, "nombre": "", "unidad": "", "cantidad": "1", "precio": ""}
                else:
                    inv["producto"] = {
                        "codigo": str(prod.get("Codigo") or ""),
                        "nombre": str(prod.get("Descripcion") or ""),
                        "unidad": str(prod.get("Unidad") or ""),
                        "cantidad": str((prod_cantidad or "1").strip() or "1"),
                        "precio": str(prod.get("Precio") or ""),
                    }
        elif action == "agregar_item":
            code = (prod_codigo or "").strip() or str((inv.get("producto") or {}).get("codigo") or "").strip()
            code = zpad(code, 15)
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
                            "exento": prod.get("Exento"),
                            "iva_tipo": prod.get("IvaTipo"),
                            "iva_pct": prod.get("IvaPct"),
                        },
                        cantidad=prod_cantidad,
                        precio=precio,
                        desc_pct=prod_desc,
                    )
                    inv["producto"] = {"codigo": "", "nombre": "", "unidad": "", "cantidad": "1", "precio": ""}
        elif action == "eliminar_item":
            remove_item(inv, remove_item_idx)
        elif action == "agregar_pago":
            modo = (pago_modo or "").strip() or "Efectivo"
            monto_raw = (pago_monto or "").strip()

            inv["pago_form"] = {
                "modo": modo,
                "banco": (pago_banco or "").strip(),
                "ref": (pago_ref or "").strip(),
                "monto": monto_raw,
            }

            if not monto_raw:
                message = "El Monto Abonar no puede quedar Vacio!!"
            else:
                from app.modules.facturacion.factura_session import _d

                monto = _d(monto_raw)
                if monto <= 0:
                    message = "El monto debe ser mayor que 0"
                else:
                    requiere_banco = modo in {"Tarjeta de Debito", "Tarjeta de Credito", "Cheque"}
                    if requiere_banco and not (pago_banco or "").strip():
                        message = f"Para el Modo de pago {modo} el campo Banco no puede quedar Vacio!!"
                    else:
                        banco = (pago_banco or "").strip() if requiere_banco else "N/A"
                        referencia = (pago_ref or "").strip() if requiere_banco else "N/A"
                        add_pago(inv, modo=modo, banco=banco, referencia=referencia, monto=monto_raw)

                        # Al agregar exitosamente, limpiamos monto/ref pero mantenemos modo/banco.
                        inv["pago_form"] = {
                            "modo": modo,
                            "banco": (pago_banco or "").strip() if requiere_banco else "",
                            "ref": "",
                            "monto": "",
                        }
        elif action == "eliminar_pago":
            remove_pago(inv, remove_pago_idx)
        elif action == "limpiar":
            inv = clear_invoice(inv)
            inv["tipdoc"] = tipdoc
            inv["pago_form"] = {"modo": "Efectivo", "banco": "", "ref": "", "monto": ""}
        else:
            # action vacío o no soportado: no hacer nada
            pass
    except DatabaseUnavailable as e:
        message = str(e)
    except Exception as e:
        message = str(e)

    recalc(inv)
    request.session["factura"] = inv

    # PRG: evitar duplicados al refrescar (F5 reenvía el último POST)
    if message:
        request.session["flash"] = message
    return RedirectResponse(url=f"/facturacion/factura/nueva?tipdoc={tipdoc}", status_code=303)


def _validate_factura_ready(inv: dict) -> str | None:
    if not (inv.get("items") or []):
        return "El documento Debe Tener algun Articulo!!"
    vend_codigo = str((inv.get("vendedor") or {}).get("codigo") or "").strip()
    if not vend_codigo:
        return "Debe Seleccionar un vendedor Activo!!"
    cli_codigo = str((inv.get("cliente") or {}).get("codigo") or "").strip()
    if not cli_codigo:
        return "Debe Seleccionar un cliente."
    return None


def _requires_supervisor(inv: dict) -> bool:
    from app.modules.facturacion.factura_session import _d

    neto = _d((inv.get("totales") or {}).get("neto"))
    pagado = _d((inv.get("totales") or {}).get("pagado"))
    return pagado < neto


def _save_factura(*, inv: dict, user: dict, print_enabled: bool, supervisor_user: str | None = None) -> tuple[str, str, str | None]:
    svc = InvoiceSaveService()
    doc_numero, table = svc.save_to_db(invoice=inv, user=user, supervisor_user=supervisor_user)
    snap = svc.save_snapshot(invoice=inv, user=user, doc_numero=doc_numero)

    job_id: str | None = None
    if print_enabled:
        caja = user.get("caja")
        job_id = FiscalService().enqueue_print_doc(
            caja=str(caja) if caja is not None else None,
            requested_by=str(user.get("username") or ""),
            payload={"invoice_id": snap.id, "doc_numero": doc_numero, "tipdoc": inv.get("tipdoc"), "table": table},
        )

    return doc_numero, snap.id, job_id


@router.post("/facturacion/factura/confirmar")
def facturacion_factura_confirmar_post(request: Request, print: str = Form("0")):
    user, redirect = _require_user(request)
    if redirect:
        return redirect

    inv = request.session.get("factura")
    if not isinstance(inv, dict):
        request.session["flash"] = "No hay un documento en sesión."
        return RedirectResponse(url="/facturacion/facturas?tipdoc=FAV", status_code=303)

    inv.setdefault("pago_form", {"modo": "Efectivo", "banco": "", "ref": "", "monto": ""})
    recalc(inv)
    request.session["factura"] = inv
    tipdoc = (inv.get("tipdoc") or "FAV").strip().upper() or "FAV"

    msg = _validate_factura_ready(inv)
    if msg:
        request.session["flash"] = msg
        return RedirectResponse(url=f"/facturacion/factura/nueva?tipdoc={tipdoc}", status_code=303)

    if _requires_supervisor(inv) and not request.session.get("factura_supervisor_ok"):
        request.session["factura_confirm_pending"] = {"print": (print or "0").strip()}
        return RedirectResponse(url="/facturacion/clave-confirmacion?scope=factura&next=/facturacion/factura/confirmar/finish", status_code=303)

    # Sin supervisor o ya autorizado
    try:
        do_print = (print or "0").strip() == "1" and bool(getattr(settings, "invoice_print_enabled", False))
        doc_numero, snap_id, job_id = _save_factura(inv=inv, user=user, print_enabled=do_print)
        if do_print:
            request.session["flash"] = (
                f"Documento guardado: {doc_numero}. Snapshot: {snap_id}. Impresión encolada: {job_id}"
                if job_id
                else f"Documento guardado: {doc_numero}. Snapshot: {snap_id}."
            )
        else:
            request.session["flash"] = f"Documento guardado (sin imprimir): {doc_numero}. Snapshot: {snap_id}"
        request.session["factura"] = clear_invoice(inv)
    except Exception as e:
        request.session["flash"] = f"No se pudo guardar: {e}"
        return RedirectResponse(url=f"/facturacion/factura/nueva?tipdoc={tipdoc}", status_code=303)

    return RedirectResponse(url=f"/facturacion/facturas?tipdoc={tipdoc}", status_code=303)


@router.get("/facturacion/factura/confirmar/finish")
def facturacion_factura_confirmar_finish(request: Request):
    user, redirect = _require_user(request)
    if redirect:
        return redirect

    inv = request.session.get("factura")
    pending = request.session.pop("factura_confirm_pending", None)
    tipdoc = "FAV"
    if isinstance(inv, dict):
        tipdoc = (inv.get("tipdoc") or "FAV").strip().upper() or "FAV"

    if not isinstance(inv, dict) or not pending:
        request.session["flash"] = "No hay confirmación pendiente."
        return RedirectResponse(url=f"/facturacion/factura/nueva?tipdoc={tipdoc}", status_code=303)

    if not request.session.get("factura_supervisor_ok"):
        request.session["flash"] = "Se requiere clave de supervisor."
        return RedirectResponse(url=f"/facturacion/factura/nueva?tipdoc={tipdoc}", status_code=303)

    # Consumir autorización (one-shot) pero conservar el usuario para auditar
    supervisor_user = str(request.session.get("factura_supervisor_user") or "").strip() or None
    request.session.pop("factura_supervisor_ok", None)
    request.session.pop("factura_supervisor_user", None)

    inv.setdefault("pago_form", {"modo": "Efectivo", "banco": "", "ref": "", "monto": ""})
    recalc(inv)

    msg = _validate_factura_ready(inv)
    if msg:
        request.session["flash"] = msg
        return RedirectResponse(url=f"/facturacion/factura/nueva?tipdoc={tipdoc}", status_code=303)

    try:
        print_flag = str((pending or {}).get("print") or "0").strip()
        do_print = print_flag == "1" and bool(getattr(settings, "invoice_print_enabled", False))
        doc_numero, snap_id, job_id = _save_factura(inv=inv, user=user, print_enabled=do_print, supervisor_user=supervisor_user)
        if do_print:
            request.session["flash"] = (
                f"Documento guardado: {doc_numero}. Snapshot: {snap_id}. Impresión encolada: {job_id}"
                if job_id
                else f"Documento guardado: {doc_numero}. Snapshot: {snap_id}."
            )
        else:
            request.session["flash"] = f"Documento guardado (sin imprimir): {doc_numero}. Snapshot: {snap_id}"
        request.session["factura"] = clear_invoice(inv)
    except Exception as e:
        request.session["flash"] = f"No se pudo guardar: {e}"
        return RedirectResponse(url=f"/facturacion/factura/nueva?tipdoc={tipdoc}", status_code=303)

    return RedirectResponse(url=f"/facturacion/facturas?tipdoc={tipdoc}", status_code=303)


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
    tipdoc: str | None = Query(None),
):
    user, redirect = _require_user(request)
    if redirect:
        return redirect
    menu = _load_menu(user)

    from decimal import Decimal, InvalidOperation

    def _d(v: object, default: Decimal = Decimal("0")) -> Decimal:
        if v is None:
            return default
        s = str(v).strip()
        if not s:
            return default
        s = s.replace(".", "").replace(",", ".") if s.count(",") == 1 and s.count(".") >= 1 else s.replace(",", ".")
        try:
            return Decimal(s)
        except InvalidOperation:
            return default

    def _fmt2(v: Decimal) -> str:
        return f"{v:.2f}"

    numero_s = (numero or "").strip()
    codigo_s = (codigo or "").strip()
    tipdoc_s = (tipdoc or "").strip().upper() or ""
    if tipdoc_s not in {"FAV", "DEV", "NDE"}:
        tipdoc_s = ""

    header: dict | None = None
    items: list[dict] = []
    pagos_rows: list[dict] = []
    error: str | None = None

    if not numero_s or not codigo_s:
        error = "Debe indicar número y cliente (código) para ver el documento."
        tipdoc_eff = tipdoc_s or "FAV"
    else:
        try:
            repo = FacturacionRepository()
            header = repo.get_documento_header(numero=numero_s, codigo=codigo_s)
            tipdoc_eff = tipdoc_s or str((header or {}).get("dcli_tipdoc") or "").strip().upper() or "FAV"
            if tipdoc_eff not in {"FAV", "DEV", "NDE"}:
                tipdoc_eff = "FAV"
            items = repo.list_items_documento(numero=numero_s, codigo=codigo_s, tipdoc=tipdoc_eff)
            pagos_rows = repo.list_pagos_documento(numero=numero_s, codigo=codigo_s)
        except DatabaseUnavailable as e:
            error = str(e)
            tipdoc_eff = tipdoc_s or "FAV"
        except Exception as e:
            error = str(e)
            tipdoc_eff = tipdoc_s or "FAV"

    inv = invoice_default(tipdoc_eff)
    inv["tipdoc"] = tipdoc_eff
    inv.setdefault("pago_form", {"modo": "Efectivo", "banco": "", "ref": "", "monto": ""})

    if header:
        inv["numero"] = str(header.get("dcli_numero") or numero_s)
        inv["fecha"] = str(header.get("dcli_fecha") or "") or inv.get("fecha")
        inv["obs"] = str(header.get("dcli_observa") or "")
        inv["numfis"] = str(header.get("dcli_numfis") or "")

    # Cliente
    try:
        cli_row = ClientesRepository().get_cliente(codigo=codigo_s) if codigo_s else None
    except Exception:
        cli_row = None
    inv["cliente"] = {
        "codigo": codigo_s,
        "rif": str((cli_row or {}).get("cli_rif") or ""),
        "nombre": str((cli_row or {}).get("cli_nombre") or (header or {}).get("cli_nombre") or ""),
        "direccion": str((cli_row or {}).get("cli_direcc") or ""),
    }

    # Vendedor
    vend_codigo = str((header or {}).get("dcli_vendedor") or "").strip()
    if not vend_codigo:
        for it in items or []:
            vend_codigo = str(it.get("mov_vendedor") or "").strip()
            if vend_codigo:
                break
    vend_codigo = zpad(vend_codigo, 10) if vend_codigo else ""
    try:
        vend_row = VendedoresRepository().get_vendedor(codigo=vend_codigo) if vend_codigo else None
    except Exception:
        vend_row = None
    inv["vendedor"] = {
        "codigo": vend_codigo,
        "nombre": str((vend_row or {}).get("ven_nombre") or ""),
    }

    # Items
    inv_items: list[dict] = []
    total_prod = Decimal("0")
    for r in items or []:
        qty = _d(r.get("mov_cant"), Decimal("0"))
        total_prod += qty
        inv_items.append(
            {
                "codigo": str(r.get("mov_codigo") or ""),
                "nombre": str(r.get("colProducto") or ""),
                "unidad": str(r.get("mov_undmed") or ""),
                "cantidad": _fmt2(qty),
                "precio": str(r.get("mov_precio") or "0.00"),
                "desc": str(r.get("mov_desc") or "0.00"),
                "total": str(r.get("mov_total") or "0.00"),
                "exento": "",
                "iva_tipo": "",
                "iva_pct": "0.00",
                "iva": "0.000000",
            }
        )
    inv["items"] = inv_items

    # Pagos (excluimos CAMBIO del listado; lo mostramos en totales)
    inv_pagos: list[dict] = []
    pagado = Decimal("0")
    efectivo = Decimal("0")
    cheques = Decimal("0")
    tarjetas = Decimal("0")
    cambio = Decimal("0")

    for p in pagos_rows or []:
        modo = str(p.get("movc_forpag") or p.get("mocv_forpag") or "").strip()
        monto = _d(p.get("movc_monto"), Decimal("0"))
        if modo.upper() == "CAMBIO":
            cambio += monto
            continue
        inv_pagos.append(
            {
                "modo": modo,
                "banco": str(p.get("movc_tipoctaban") or ""),
                "referencia": str(p.get("movc_numero") or ""),
                "monto": _fmt2(monto),
            }
        )
        pagado += monto
        ml = modo.lower()
        if "efectivo" in ml:
            efectivo += monto
        elif "cheque" in ml:
            cheques += monto
        elif "tarjeta" in ml:
            tarjetas += monto

    inv["pagos"] = inv_pagos

    # Totales preferimos los del header (para no recalcular con IVA desconocido)
    des_items = _d((header or {}).get("dcli_desc"), Decimal("0"))
    base = _d((header or {}).get("dcli_baseneta"), Decimal("0"))
    iva = _d((header or {}).get("dcli_iva"), Decimal("0"))
    neto = _d((header or {}).get("dcli_neto"), base + iva)
    subtotal = base + des_items

    inv["totales"] = {
        "subtotal": _fmt2(subtotal),
        "des_items": _fmt2(des_items),
        "base": _fmt2(base),
        "total_prod": _fmt2(total_prod),
        "iva": _fmt2(iva),
        "neto": _fmt2(neto),
        "pagado": _fmt2(pagado),
        "cambio": _fmt2(cambio),
        "efectivo": _fmt2(efectivo),
        "cheques": _fmt2(cheques),
        "tarjetas": _fmt2(tarjetas),
    }

    titulo_doc = "Factura de Venta" if tipdoc_eff == "FAV" else ("Devolución" if tipdoc_eff == "DEV" else "Nota de Débito")
    message = error

    return templates.TemplateResponse(
        "facturacion/frm_factura.html",
        {
            "request": request,
            "user": user,
            "menu": menu,
            "active_href": "/facturacion/facturas",
            "title": f"Ver Documento - {titulo_doc} - Lebrun",
            "page_title": f"Ver Documento - {titulo_doc}",
            "message": message,
            "inv": inv,
            "hide_topbar": True,
            "view_only": True,
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
