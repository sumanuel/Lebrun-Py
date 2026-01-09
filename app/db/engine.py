from __future__ import annotations

from functools import lru_cache
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.engine import URL

from app.core.config import settings


def _mysql_url(database: str) -> str:
    return str(
        URL.create(
            drivername="mysql+pymysql",
            username=settings.db_user,
            password=(settings.db_password or None),
            host=settings.db_host,
            port=settings.db_port,
            database=database,
        )
    )


def sysconta_db_name(company_code: str | None) -> str:
    if not company_code or company_code == "01":
        return settings.db_sysconta_prefix
    return f"{settings.db_sysconta_prefix}_{company_code}"


@lru_cache(maxsize=16)
def get_engine(db_name: str) -> Engine:
    return create_engine(_mysql_url(db_name), pool_pre_ping=True)
