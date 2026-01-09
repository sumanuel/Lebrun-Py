from __future__ import annotations

from collections import defaultdict

from app.core.config import settings
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
                grouped[group_name].append(
                    {
                        "label": str(row.get("menu_nombre") or row.get("hijo") or "(sin nombre)"),
                        "route": str(row.get("mmn_formulario") or ""),
                    }
                )

            groups = [
                {"name": name, "items": grouped[name]}
                for name in sorted(grouped.keys(), key=lambda x: (x != "General", x))
            ]

            result.append({"module": module_name, "groups": groups})

        return result
