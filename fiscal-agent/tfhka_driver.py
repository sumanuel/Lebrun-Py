from __future__ import annotations

import os
from pathlib import Path


class TfhkaError(RuntimeError):
    pass


def _load_tfhka(dll_path: str):
    """Carga TfhkaNet.dll usando pythonnet.

    Se importa de forma lazy para que el agente pueda correr en modo stub
    incluso si pythonnet no está instalado.
    """

    try:
        import clr  # type: ignore
    except Exception as e:  # pragma: no cover
        raise TfhkaError(
            "No se pudo importar pythonnet (clr). Instale dependencias del fiscal-agent."
        ) from e

    dll = Path(dll_path)
    if not dll.exists():
        raise TfhkaError(f"No existe TfhkaNet.dll en: {dll}")

    try:
        clr.AddReference(str(dll))
    except Exception as e:
        raise TfhkaError(f"No se pudo cargar el assembly: {dll}") from e

    try:
        from TfhkaNet.IF.VE import Tfhka  # type: ignore
    except Exception as e:
        raise TfhkaError(
            "No se pudo importar TfhkaNet.IF.VE.Tfhka desde el DLL. Verifique versión/arquitectura."
        ) from e

    return Tfhka


def print_report_xz(*, report: str, com_port: str, dll_path: str) -> None:
    report = (report or "").strip().upper()
    if report not in {"X", "Z"}:
        raise TfhkaError(f"Reporte inválido: {report}")

    com_port = (com_port or "").strip()
    if not com_port:
        raise TfhkaError("Falta configurar LEBRUN_FISCAL_COM_PORT (ej: COM3)")

    dll_path = (dll_path or "").strip()
    if not dll_path:
        raise TfhkaError(
            "Falta configurar LEBRUN_TFHKA_DLL_PATH (ruta a TfhkaNet.dll en la PC fiscal)"
        )

    Tfhka = _load_tfhka(dll_path)

    impresora = Tfhka()
    opened = False

    try:
        ok = bool(impresora.OpenFpCtrl(com_port))
        opened = ok
        if not ok:
            raise TfhkaError(f"No se pudo abrir el puerto {com_port} (OpenFpCtrl=false)")

        ok = bool(impresora.CheckFPrinter())
        if not ok:
            raise TfhkaError("Impresora no responde / CheckFPrinter=false")

        if report == "X":
            impresora.PrintXReport()
        else:
            impresora.PrintZReport()

    except TfhkaError:
        raise
    except Exception as e:
        raise TfhkaError(str(e)) from e
    finally:
        if opened:
            try:
                impresora.CloseFpCtrl()
            except Exception:
                pass
