from __future__ import annotations

from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import settings
from app.core.exceptions import DatabaseUnavailable
from app.modules.auth.router import router as auth_router
from app.modules.menu.service import MenuService

app = FastAPI(title="Lebrun-Py")
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)

templates = Jinja2Templates(directory=str(settings.templates_dir))

static_dir = settings.templates_dir.parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

app.include_router(auth_router)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    # Placeholder: aquí luego renderizamos el menú dinámico y el selector de compañía.
    menu_map = user.get("menu_map")
    menu = []
    if menu_map:
        try:
            menu = MenuService().build_menu(str(menu_map))
        except Exception:
            # Si falla el menú, mostramos menú vacío
            menu = []
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "user": user,
            "menu": menu,
            "title": "Principal - Lebrun",
        },
    )


@app.get("/open", response_class=HTMLResponse)
async def open_form(request: Request, form: str = Query("")):
    user = request.session.get("user")
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    menu_map = user.get("menu_map")
    menu = []
    if menu_map:
        try:
            menu = MenuService().build_menu(str(menu_map))
        except Exception:
            menu = []

    return templates.TemplateResponse(
        "open.html",
        {
            "request": request,
            "user": user,
            "menu": menu,
            "form": form,
            "title": f"{form} - Lebrun" if form else "Lebrun",
        },
    )
