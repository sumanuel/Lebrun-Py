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

    def search(self, *, q: str | None, limit: int = 50) -> list[dict]:
        q = (q or "").strip()
        limit = max(1, min(int(limit or 50), 200))
        if not q:
            # Para el modal: si hay muchas filas en admclientes, un listado "general" puede
            # ser costoso. Traemos clientes recientes basados en documentos.
            sql_recent = text(
                f"""
                                SELECT c.cli_codigo, c.cli_rif, c.cli_nombre
                FROM admclientes c
                JOIN (
                  SELECT dcli_codigo, MAX(dcli_fecha) AS max_fecha
                  FROM admdoccli2
                  GROUP BY dcli_codigo
                  ORDER BY max_fecha DESC
                  LIMIT {limit}
                ) r ON r.dcli_codigo = c.cli_codigo
                ORDER BY r.max_fecha DESC
                """
            )

            sql_fallback = text(
                f"""
                SELECT cli_codigo, cli_rif, cli_nombre
                FROM admclientes
                LIMIT {limit}
                """
            )

            try:
                with session_for(settings.db_sysadm) as s:
                    rows = s.execute(sql_recent, {}).mappings().all()
                    return [dict(r) for r in rows]
            except SQLAlchemyError:
                # Fallback simple (si admdoccli2 no existe o falla la query)
                try:
                    with session_for(settings.db_sysadm) as s:
                        rows = s.execute(sql_fallback, {}).mappings().all()
                        return [dict(r) for r in rows]
                except SQLAlchemyError as e:
                    raise DatabaseUnavailable(f"Error al buscar clientes (sisadm): {e}") from e
        else:
            sql = text(
                f"""
                SELECT cli_codigo, cli_rif, cli_nombre
                FROM admclientes
                WHERE cli_codigo LIKE :term OR cli_nombre LIKE :term
                ORDER BY cli_codigo
                LIMIT {limit}
                """
            )
            params = {"term": f"%{q}%"}

        try:
            with session_for(settings.db_sysadm) as s:
                rows = s.execute(sql, params).mappings().all()
                return [dict(r) for r in rows]
        except SQLAlchemyError as e:
            raise DatabaseUnavailable(f"Error al buscar clientes (sisadm): {e}") from e
