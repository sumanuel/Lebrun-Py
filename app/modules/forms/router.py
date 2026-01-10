from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.core.config import settings
from app.modules.menu.service import MenuService

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


@router.get("/ventas/visor-precios", response_class=HTMLResponse)
def ventas_visor_precios(request: Request):
    return _render_form_page(
        request,
        title="Visor de Precios",
        description="Consulta rápida de artículos/precios. Implementación inicial: UI + navegación.",
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
