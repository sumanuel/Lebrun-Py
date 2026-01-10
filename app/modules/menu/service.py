from __future__ import annotations

from collections import defaultdict
from urllib.parse import quote_plus

from app.core.config import settings
from app.modules.forms.mapping import resolve_path
from app.modules.menu.repository import MenuRepository


class MenuService:
    def __init__(self) -> None:
        self.repo = MenuRepository()

    def build_menu(self, menu_map: str) -> list[dict]:
        """Devuelve un menú jerárquico para renderizar en la vista.

        Estructura:
        [
          {
            "module": "BANCOS",
            "groups": [
              {"name": "CATALOGOS", "items": [{"label":..., "route":...}, ...]},
              ...
            ]
          },
          ...
        ]
        """
        modules = self.repo.list_modules_for_map(settings.db_sysconf, menu_map)
        result: list[dict] = []

        for module_name in modules:
            items = self.repo.load_module_menu(settings.db_sysconf, module_name, menu_map)
            grouped: dict[str, list[dict]] = defaultdict(list)

            for row in items:
                group_name = str(row.get("subpadre") or "General")
                route = str(row.get("mmn_formulario") or "")
                href = None
                if route:
                    mapped = resolve_path(route)
                    if mapped:
                        href = mapped
                    else:
                        # En WinForms el "formulario" es una clase/identificador.
                        # En web lo mapeamos a una pantalla placeholder; luego se enruta a vistas reales.
                        href = f"/open?form={quote_plus(route)}"
                grouped[group_name].append(
                    {
                        "label": str(row.get("menu_nombre") or row.get("hijo") or "(sin nombre)"),
                        "route": route,
                        "href": href,
                    }
                )

            groups = [
                {"name": name, "items": grouped[name]}
                for name in sorted(grouped.keys(), key=lambda x: (x != "General", x))
            ]

            result.append({"module": module_name, "groups": groups})

        return result
