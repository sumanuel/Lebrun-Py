from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.exceptions import DatabaseUnavailable
from app.db.session import session_for


class BancosRepository:
    def get_banco(self, *, codigo: str) -> dict | None:
        codigo = (codigo or "").strip()
        if not codigo:
            return None

        sql = text(
            """
            SELECT ban_codigo, ban_nombre
            FROM admbancos
            WHERE ban_codigo = :codigo
            LIMIT 1
            """
        )

        try:
            with session_for(settings.db_sysadm) as s:
                row = s.execute(sql, {"codigo": codigo}).mappings().first()
                return dict(row) if row else None
        except SQLAlchemyError as e:
            raise DatabaseUnavailable("Error al cargar banco (sisadm).") from e

    def search(self, *, q: str | None, limit: int = 80) -> list[dict]:
        q = (q or "").strip()
        limit = max(1, min(int(limit or 80), 200))

        if not q:
            sql = text(
                """
                SELECT ban_codigo, ban_nombre
                FROM admbancos
                LIMIT :limit
                """
            )
            params = {"limit": limit}
        else:
            sql = text(
                """
                SELECT ban_codigo, ban_nombre
                FROM admbancos
                WHERE ban_codigo LIKE :term OR ban_nombre LIKE :term
                LIMIT :limit
                """
            )
            params = {"term": f"%{q}%", "limit": limit}

        try:
            with session_for(settings.db_sysadm) as s:
                rows = s.execute(sql, params).mappings().all()
                return [dict(r) for r in rows]
        except SQLAlchemyError as e:
            raise DatabaseUnavailable("Error al buscar bancos (sisadm).") from e
