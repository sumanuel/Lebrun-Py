from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.exceptions import DatabaseUnavailable
from app.db.session import session_for


class FacturacionRepository:
    def _list_documentos_from_table(
        self,
        *,
        table: str,
        caja: str,
        tipdoc: str,
        q: str | None,
        date_from: str | None,
        date_to: str | None,
        limit: int,
    ) -> list[dict]:
        # Nota: usamos DISTINCT en lugar de GROUP BY para evitar fallas con ONLY_FULL_GROUP_BY.
        # LIMIT se inyecta como entero clamped para evitar problemas de binding en MySQL.
        base_sql = f"""
            SELECT DISTINCT
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
            FROM {table}
            LEFT OUTER JOIN admclientes
              ON admclientes.cli_codigo = {table}.dcli_codigo
            WHERE dcli_tipdoc = :tipdoc
              AND dcli_caja = :caja
              AND (dcli_cerrado != '1' OR dcli_cerrado IS NULL)
        """

        params: dict = {"tipdoc": tipdoc, "caja": caja}

        if date_from and date_from.strip():
            base_sql += "\n  AND DATE(dcli_fecha) >= :date_from"
            params["date_from"] = date_from.strip()

        if date_to and date_to.strip():
            base_sql += "\n  AND DATE(dcli_fecha) <= :date_to"
            params["date_to"] = date_to.strip()

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

        base_sql += f"""
            ORDER BY dcli_fecha DESC, dcli_numero DESC, dcli_codigo ASC
            LIMIT {int(limit)}
        """

        sql = text(base_sql)

        with session_for(settings.db_sysadm) as s:
            rows = s.execute(sql, params).mappings().all()
            return [dict(r) for r in rows]

    def list_documentos(
        self,
        *,
        caja: str,
        tipdoc: str = "FAV",
        q: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        tipdoc = (tipdoc or "").strip().upper() or "FAV"
        if tipdoc not in {"FAV", "DEV", "NDE"}:
            tipdoc = "FAV"

        # En lbxFacturas el comportamiento esperado es "últimas 100".
        limit = max(1, min(int(limit or 100), 100))

        try:
            # Tabla principal usada por el WinForms/implementación previa.
            return self._list_documentos_from_table(
                table="admdoccli2",
                caja=caja,
                tipdoc=tipdoc,
                q=q,
                date_from=date_from,
                date_to=date_to,
                limit=limit,
            )
        except SQLAlchemyError as e:
            # Fallback: en algunas instalaciones la tabla puede ser admdoccli.
            try:
                return self._list_documentos_from_table(
                    table="admdoccli",
                    caja=caja,
                    tipdoc=tipdoc,
                    q=q,
                    date_from=date_from,
                    date_to=date_to,
                    limit=limit,
                )
            except SQLAlchemyError as e2:
                msg = str(getattr(getattr(e2, "orig", None), "args", None) or str(e2))
                raise DatabaseUnavailable(f"Error al cargar facturas (sisadm): {msg}") from e2
