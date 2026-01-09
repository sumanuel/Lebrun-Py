from __future__ import annotations


class DatabaseUnavailable(RuntimeError):
    """Error controlado para fallas de conexión/credenciales a la BD."""

