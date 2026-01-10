from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.exceptions import DatabaseUnavailable
from app.db.session import session_for


class FacturacionRepository:
    def list_documentos(
        self,
        *,
        caja: str,
        tipdoc: str = "FAV",
        q: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        tipdoc = (tipdoc or "").strip().upper() or "FAV"
        if tipdoc not in {"FAV", "DEV", "NDE"}:
            tipdoc = "FAV"

        limit = max(1, min(int(limit or 100), 300))

        base_sql = """
            SELECT
              dcli_numero,
              dcli_codigo,
              cli_nombre,
              dcli_fecha,
              dcli_estado,
              dcli_neto,
              dcli_tiptra,
              dcli_baseneta,
              dcli_numfis,
              dcli_impreso,
              dcli_tipdoc,
              dcli_codmon,
              dcli_facafe
            FROM admdoccli2
            LEFT OUTER JOIN admclientes
              ON admclientes.cli_codigo = admdoccli2.dcli_codigo
            WHERE dcli_tipdoc = :tipdoc
              AND dcli_caja = :caja
              AND (dcli_cerrado != '1' OR dcli_cerrado IS NULL)
        """

        params: dict = {"tipdoc": tipdoc, "caja": caja, "limit": limit}

        if q and q.strip():
            term = f"%{q.strip()}%"
            base_sql += """
              AND (
                dcli_numero LIKE :term
                OR dcli_numfis LIKE :term
                OR dcli_codigo LIKE :term
                OR cli_nombre LIKE :term
              )
            """
            params["term"] = term

        base_sql += """
            GROUP BY dcli_codigo, dcli_numero
            ORDER BY dcli_numero DESC, dcli_codigo ASC
            LIMIT :limit
        """

        sql = text(base_sql)

        try:
            with session_for(settings.db_sysadm) as s:
                rows = s.execute(sql, params).mappings().all()
                return [dict(r) for r in rows]
        except SQLAlchemyError as e:
            raise DatabaseUnavailable("Error al cargar facturas (sisadm).") from e
