from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


def _env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None:
        raise RuntimeError(f"Missing env var: {name}")
    return value


@dataclass(frozen=True)
class Settings:
    db_host: str = _env("LEBRUN_DB_HOST", "localhost")
    db_port: int = int(_env("LEBRUN_DB_PORT", "3306"))
    db_user: str = _env("LEBRUN_DB_USER", "root")
    db_password: str = _env("LEBRUN_DB_PASSWORD", "")

    db_sysadm: str = _env("LEBRUN_DB_SYSADM", "sisadm")
    db_sysconf: str = _env("LEBRUN_DB_SYSCONF", "sysconf")
    db_sysconta_prefix: str = _env("LEBRUN_DB_SYSCONTA_PREFIX", "sysconta")

    secret_key: str = _env("SECRET_KEY", "change-me")

    fiscal_agent_token: str = _env("LEBRUN_FISCAL_AGENT_TOKEN", "")
    fiscal_jobs_path: Path = Path(_env("LEBRUN_FISCAL_JOBS_PATH", str(PROJECT_ROOT / "data" / "fiscal_jobs.json")))

    # Facturación (guardado/impresión)
    invoices_path: Path = Path(_env("LEBRUN_INVOICES_PATH", str(PROJECT_ROOT / "data" / "invoices")))
    invoice_print_enabled: bool = _env("LEBRUN_INVOICE_PRINT_ENABLED", "0").strip() in {"1", "true", "True", "yes", "YES"}

    templates_dir: Path = PROJECT_ROOT / "app" / "web" / "templates"


settings = Settings()
