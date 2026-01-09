from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import session_for
from app.core.exceptions import DatabaseUnavailable


class AuthRepository:
    def list_companies(self, db_name: str):
        # confdatosempresa: empre_nombre, empre_codigo, empre_actual
        sql = text(
            """
            SELECT empre_nombre, empre_codigo, empre_actual
            FROM confdatosempresa
            ORDER BY empre_actual DESC, empre_codigo ASC
            """
        )
        try:
            with session_for(db_name) as s:
                rows = s.execute(sql).mappings().all()
                return [dict(r) for r in rows]
        except SQLAlchemyError as e:
            raise DatabaseUnavailable(
                "No se pudo conectar a MySQL. Revisa tu configuración (.env): host/usuario/clave y que la BD 'sysconf' exista."
            ) from e

    def get_user(self, db_name: str, username: str, password: str) -> dict[str, Any] | None:
        sql = text(
            """
            SELECT usu_mapmnu, usu_nombre, usu_codigo, usu_caja
            FROM confusuario
            WHERE usu_nombre = :username AND usu_clave = :password
            """
        )
        try:
            with session_for(db_name) as s:
                row = s.execute(sql, {"username": username, "password": password}).mappings().first()
                return dict(row) if row else None
        except SQLAlchemyError as e:
            raise DatabaseUnavailable(
                "No se pudo consultar usuarios en MySQL. Revisa credenciales y acceso a la BD 'sysconf'."
            ) from e

    def is_user_active(self, db_name: str, user_id: str) -> bool:
        sql = text(
            """
            SELECT usu_status
            FROM confusuario2
            WHERE usu_codigo = :user_id
            """
        )
        try:
            with session_for(db_name) as s:
                row = s.execute(sql, {"user_id": user_id}).mappings().first()
                if not row:
                    return False
                # En MySQL puede venir 0/1, 'True'/'False', etc.
                value = row["usu_status"]
                return str(value).lower() in {"1", "true", "t", "yes", "y"}
        except SQLAlchemyError as e:
            raise DatabaseUnavailable(
                "No se pudo validar estado del usuario. Revisa acceso a la BD 'sysconf'."
            ) from e

    def user_has_company_permission(self, db_name: str, user_id: str, company_code: str) -> bool:
        sql = text(
            """
            SELECT usu_administracion
            FROM confusuario2
            WHERE usu_codigo = :user_id
            """
        )
        try:
            with session_for(db_name) as s:
                row = s.execute(sql, {"user_id": user_id}).mappings().first()
                if not row or row["usu_administracion"] is None:
                    return False
                allowed = str(row["usu_administracion"]).split("-")
                return company_code in allowed
        except SQLAlchemyError as e:
            raise DatabaseUnavailable(
                "No se pudo validar permisos de compañía. Revisa acceso a la BD 'sysconf'."
            ) from e
