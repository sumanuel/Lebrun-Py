from __future__ import annotations

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.core.config import settings
from app.core.exceptions import DatabaseUnavailable
from app.modules.auth.service import AuthService

router = APIRouter()
templates = Jinja2Templates(directory=str(settings.templates_dir))


@router.get("/login", response_class=HTMLResponse)
def login_get(request: Request):
    service = AuthService()
    try:
        companies = service.list_companies()
    except DatabaseUnavailable as e:
        companies = []
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "companies": companies,
                "error": str(e),
            },
            status_code=503,
        )
    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "companies": companies,
            "error": None,
        },
    )


@router.post("/login")
def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    company_code: str = Form(...),
):
    service = AuthService()

    user = service.authenticate(username=username, password=password, company_code=company_code)
    if not user:
        try:
            companies = service.list_companies()
        except DatabaseUnavailable as e:
            return templates.TemplateResponse(
                "login.html",
                {
                    "request": request,
                    "companies": [],
                    "error": str(e),
                },
                status_code=503,
            )
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "companies": companies,
                "error": "Login o contraseña incorrectos, o sin permisos.",
            },
            status_code=401,
        )

    request.session["user"] = user
    request.session["company_code"] = company_code
    return RedirectResponse(url="/", status_code=302)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)
