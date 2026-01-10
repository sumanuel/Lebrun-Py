from __future__ import annotations

from dataclasses import dataclass
import re


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").strip().lower())


@dataclass(frozen=True)
class FormMapping:
    key: str
    title: str
    path: str
    description: str
    aliases: tuple[str, ...] = ()


# 5 formularios iniciales (alias múltiples porque en BD puede venir con namespace completo o solo el nombre).
MAPPINGS: tuple[FormMapping, ...] = (
    FormMapping(
        key="lebrun.formularios.complementos.frmConsultaArticulos",
        title="Visor de Precios",
        path="/ventas/visor-precios",
        description="Consulta rápida de artículos/precios (versión web inicial).",
        aliases=("frmConsultaArticulos", "Visor"),
    ),
    FormMapping(
        key="lebrun.formularios.complementos.frmPagare",
        title="Pagaré",
        path="/ventas/pagare",
        description="Registro/consulta de pagarés (versión web inicial).",
        aliases=("frmPagare",),
    ),
    FormMapping(
        key="lebrun.parametrosContables",
        title="Parámetros Contables",
        path="/administracion/parametros-contables",
        description="Parámetros base de contabilidad (versión web inicial).",
        aliases=("parametrosContables",),
    ),
    FormMapping(
        key="lebrun.formularios.contabilidad.frmPlanCuentas",
        title="Plan de Cuentas",
        path="/contabilidad/plan-cuentas",
        description="Consulta del plan de cuentas (versión web inicial).",
        aliases=("frmPlanCuentas", "lbxPlanCuentas"),
    ),
    FormMapping(
        key="lebrun.formularios.contabilidad.frmComprobanteCierre",
        title="Comprobante de Cierre",
        path="/contabilidad/comprobante-cierre",
        description="Consulta/gestión de comprobantes de cierre (versión web inicial).",
        aliases=("frmComprobanteCierre", "comprobanteCierre"),
    ),
)


def resolve_mapping(form_id: str) -> FormMapping | None:
    normalized = _norm(form_id)
    if not normalized:
        return None

    for mapping in MAPPINGS:
        candidates = (mapping.key,) + mapping.aliases
        for c in candidates:
            c_norm = _norm(c)
            if not c_norm:
                continue
            if normalized == c_norm or normalized.endswith(c_norm):
                return mapping

    return None


def resolve_path(form_id: str) -> str | None:
    mapping = resolve_mapping(form_id)
    return mapping.path if mapping else None
