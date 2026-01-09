from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import settings
from app.core.exceptions import DatabaseUnavailable
from app.modules.auth.router import router as auth_router
from app.modules.menu.service import MenuService

app = FastAPI(title="Lebrun-Py")
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)

templates = Jinja2Templates(directory=str(settings.templates_dir))

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
        },
    )
