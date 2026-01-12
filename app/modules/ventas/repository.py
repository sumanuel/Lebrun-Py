from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.exceptions import DatabaseUnavailable
from app.db.session import session_for


@dataclass(frozen=True)
class ProductoRow:
    codigo: str
    descripcion: str
    unidad: str | None
    precio: float | None
    existencia: float | None
    exento: str | None


class VentasRepository:
    def get_producto_by_codigo(self, *, codigo: str) -> dict | None:
        codigo = (codigo or "").strip()
        if not codigo:
            return None

        sql = text(
            """
            SELECT
              adminv.inv_codigo AS Codigo,
              adminv.inv_descri AS Descripcion,
              adminvmed.ime_undmed AS Unidad,
              admprecios.pre_precio AS Precio,
              existencia AS Existencia,
              inv_ex AS Exento
            FROM adminv
            LEFT OUTER JOIN adminv2 ON adminv.inv_codigo = adminv2.inv2_codigo
            LEFT JOIN adminvmed ON adminvmed.ime_codigo = adminv.inv_codigo
            LEFT JOIN admprecios
              ON admprecios.pre_codigo = adminv.inv_codigo
             AND admprecios.pre_lista = 'A'
             AND admprecios.pre_act = '1'
            WHERE inv_estado = 'Activo'
              AND pre_undmed = ime_undmed
              AND adminv.inv_codigo = :code
            LIMIT 1
            """
        )

        try:
            with session_for(settings.db_sysadm) as s:
                row = s.execute(sql, {"code": codigo}).mappings().first()
                return dict(row) if row else None
        except SQLAlchemyError as e:
            raise DatabaseUnavailable("Error al buscar producto (sisadm).") from e

    def list_productos(
        self,
        *,
        q: str | None = None,
        by: str = "descripcion",
        limit: int = 100,
    ) -> list[dict]:
        limit = max(1, min(int(limit or 100), 300))
        by = (by or "descripcion").strip().lower()
        if by not in {"codigo", "descripcion", "grupo"}:
            by = "descripcion"

        base_sql = """
            SELECT
              adminv.inv_codigo AS Codigo,
              adminv.inv_descri AS Descripcion,
              adminvmed.ime_undmed AS Unidad,
              admprecios.pre_precio AS Precio,
              existencia AS Existencia,
              inv_ex AS Exento,
              precio_pmvp AS PMVP,
              inv_proced AS Procedencia,
              ult_provee AS pro_principal
            FROM adminv
            LEFT OUTER JOIN adminv2 ON adminv.inv_codigo = adminv2.inv2_codigo
            LEFT JOIN adminvmed ON adminvmed.ime_codigo = adminv.inv_codigo
            LEFT JOIN admprecios
              ON admprecios.pre_codigo = adminv.inv_codigo
             AND admprecios.pre_lista = 'A'
             AND admprecios.pre_act = '1'
            LEFT JOIN admgrupo ON adminv.inv_grupo = admgrupo.gru_codigo
            WHERE inv_estado = 'Activo'
              AND pre_undmed = ime_undmed
              AND existencia > 0
        """

        params: dict = {"limit": limit}

        if q and q.strip():
            qv = q.strip()
            if by == "codigo":
                # En WinForms lo rellena a 15 dígitos y busca "a partir de".
                try:
                    qv_num = str(int(qv)).zfill(15)
                except ValueError:
                    qv_num = qv
                base_sql += " AND adminv.inv_codigo >= :code "
                params["code"] = qv_num
            elif by == "grupo":
                base_sql += " AND admgrupo.gru_descri LIKE :term "
                params["term"] = f"%{qv}%"
            else:
                base_sql += " AND adminv.inv_descri LIKE :term "
                params["term"] = f"%{qv}%"

        base_sql += """
            GROUP BY inv_codigo
            ORDER BY inv_codigo
            LIMIT :limit
        """

        sql = text(base_sql)

        try:
            with session_for(settings.db_sysadm) as s:
                rows = s.execute(sql, params).mappings().all()
                return [dict(r) for r in rows]
        except SQLAlchemyError as e:
            raise DatabaseUnavailable("Error al cargar artículos (sisadm).") from e
