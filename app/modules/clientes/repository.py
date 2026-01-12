from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.exceptions import DatabaseUnavailable
from app.db.session import session_for


class ClientesRepository:
    def get_cliente(self, *, codigo: str) -> dict | None:
        codigo = (codigo or "").strip()
        if not codigo:
            return None

        sql = text(
            """
            SELECT
              cli_codigo,
              cli_rif,
              cli_nombre,
              cli_direcc
            FROM admclientes
            WHERE cli_codigo = :codigo
            LIMIT 1
            """
        )

        try:
            with session_for(settings.db_sysadm) as s:
                row = s.execute(sql, {"codigo": codigo}).mappings().first()
                return dict(row) if row else None
        except SQLAlchemyError as e:
            raise DatabaseUnavailable("Error al cargar cliente (sisadm).") from e
