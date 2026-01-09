from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import session_for
from app.core.exceptions import DatabaseUnavailable


class MenuRepository:
    def list_modules_for_map(self, db_name: str, menu_map: str) -> list[str]:
        # mmn_modulo = nombre del módulo (ej: BANCOS, CLIENTES, etc)
        sql = text(
            """
            SELECT DISTINCT mmn_modulo
            FROM confmapamenu
            WHERE mmn_codigo = :menu_map
              AND mmn_activo = true
            ORDER BY mmn_modulo ASC
            """
        )
        try:
            with session_for(db_name) as s:
                rows = s.execute(sql, {"menu_map": menu_map}).all()
                return [str(r[0]) for r in rows if r and r[0] is not None]
        except SQLAlchemyError as e:
            raise DatabaseUnavailable("Error al cargar módulos del menú.") from e

    def load_module_menu(self, db_name: str, module_name: str, menu_map: str) -> list[dict]:
        # Replica del C# Compania.cargarMenuPrincipal(nombreMenu, mapaMenu)
        sql = text(
            """
            SELECT
              menu_padre   AS padre,
              menu_subpadre AS subpadre,
              menu_hijo    AS hijo,
              menu_ruta    AS mmn_formulario,
              menu_nombre
            FROM conf_menu
            LEFT JOIN confmapamenu
              ON conf_menu.menu_antiguo = confmapamenu.mmn_menu
            WHERE confmapamenu.mmn_modulo = :module_name
              AND conf_menu.menu_padre = :module_name
              AND confmapamenu.mmn_codigo = :menu_map
              AND confmapamenu.mmn_activo = true
            ORDER BY menu_subpadre ASC, menu_hijo ASC
            """
        )
        try:
            with session_for(db_name) as s:
                rows = s.execute(
                    sql,
                    {"module_name": module_name, "menu_map": menu_map},
                ).mappings().all()
                return [dict(r) for r in rows]
        except SQLAlchemyError as e:
            raise DatabaseUnavailable("Error al cargar items del menú.") from e
