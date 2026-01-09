from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings
from app.modules.auth.repository import AuthRepository


@dataclass(frozen=True)
class AuthenticatedUser:
    id: str
    username: str
    menu_map: str
    caja: str | None


class AuthService:
    def __init__(self) -> None:
        self.repo = AuthRepository()

    def list_companies(self):
        return self.repo.list_companies(db_name=settings.db_sysconf)

    def authenticate(self, username: str, password: str, company_code: str):
        # Nota: esto replica el flujo de C# de forma mínima.
        # - valida usuario en sysconf.confusuario
        # - valida activo (confusuario2)
        # - valida permiso a compañía (usu_administracion contiene códigos separados por '-')
        user_row = self.repo.get_user(db_name=settings.db_sysconf, username=username, password=password)
        if not user_row:
            return None

        user_id = str(user_row["usu_codigo"])
        menu_map = str(user_row["usu_mapmnu"])
        caja = user_row.get("usu_caja")

        if not self.repo.is_user_active(db_name=settings.db_sysconf, user_id=user_id):
            return None

        if not self.repo.user_has_company_permission(db_name=settings.db_sysconf, user_id=user_id, company_code=company_code):
            return None

        return {
            "id": user_id,
            "username": str(user_row["usu_nombre"]),
            "menu_map": menu_map,
            "caja": str(caja) if caja is not None else None,
        }
