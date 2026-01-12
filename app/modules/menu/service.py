from __future__ import annotations

from collections import defaultdict
from urllib.parse import quote_plus

from app.core.config import settings
from app.modules.forms.mapping import resolve_path
from app.modules.menu.repository import MenuRepository


class MenuService:
    def __init__(self) -> None:
        self.repo = MenuRepository()

    def build_menu(self, menu_map: str, *, user: dict | None = None) -> list[dict]:
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

        # Comportamiento similar al WinForms (caja): el menú visible es más compacto.
        # En el original (Principal.cs) incluso se construyen solo algunos módulos y
        # se filtran opciones específicas en Ventas.
        caja = None
        if user:
            caja = user.get("caja")

        if caja:
            allowed_modules = {"Inventario", "Ventas"}
            modules = [m for m in modules if str(m) in allowed_modules]

        result: list[dict] = []

        for module_name in modules:
            items = self.repo.load_module_menu(settings.db_sysconf, module_name, menu_map)

            # En el WinForms, para Ventas se filtran solo opciones de Transacciones/Procesos.
            if caja and str(module_name) == "Ventas":
                allowed_groups = {"Transacciones", "Procesos"}
                allowed_hijos = {
                    "Factura de Venta",
                    "Devolucion de Venta",
                    "Nota de Debito",
                    "Reporte X",
                    "Reporte Z",
                }
                filtered = []
                for row in items:
                    subpadre = str(row.get("subpadre") or "")
                    hijo = str(row.get("hijo") or "")
                    if subpadre in allowed_groups and hijo in allowed_hijos:
                        filtered.append(row)
                items = filtered
            grouped: dict[str, list[dict]] = defaultdict(list)

            for row in items:
                group_name = str(row.get("subpadre") or "General")
                route = str(row.get("mmn_formulario") or "")
                label = str(row.get("menu_nombre") or row.get("hijo") or "(sin nombre)")
                href = None
                if route:
                    mapped = resolve_path(route)
                    if mapped:
                        href = mapped

                        # Comportamiento WinForms: mismos formularios, distinto tipo de documento según el nombre del menú.
                        label_norm = (label or "").strip().lower()

                        # Ventas → Transacciones: Factura/Devolución/Nota de Débito abren lbxFacturas filtrado.
                        if mapped == "/facturacion/facturas":
                            if "factura" in label_norm and "venta" in label_norm:
                                href = f"{mapped}?tipdoc=FAV"
                            elif "devolucion" in label_norm and "venta" in label_norm:
                                href = f"{mapped}?tipdoc=DEV"
                            elif "debito" in label_norm:
                                href = f"{mapped}?tipdoc=NDE"

                        # Ventas → Transacciones: Reporte X / Reporte Z ejecutan acción directa.
                        if mapped == "/facturacion/reportes/zx":
                            if "reporte x" in label_norm:
                                href = "/facturacion/reportes/zx/run?action=X"
                            elif "reporte z" in label_norm:
                                href = "/facturacion/reportes/zx/run?action=Z"
                    else:
                        # En WinForms el "formulario" es una clase/identificador.
                        # En web lo mapeamos a una pantalla placeholder; luego se enruta a vistas reales.
                        href = f"/open?form={quote_plus(route)}"
                if href:
                    grouped[group_name].append(
                        {
                            "label": label,
                            "route": route,
                            "href": href,
                        }
                    )

            groups = []
            for name in sorted(grouped.keys(), key=lambda x: (x != "General", x)):
                if grouped[name]:
                    groups.append({"name": name, "items": grouped[name]})

            if groups:
                result.append({"module": module_name, "groups": groups})

        return result
