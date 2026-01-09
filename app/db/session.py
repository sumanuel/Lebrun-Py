from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy.orm import Session

from app.db.engine import get_engine


@contextmanager
def session_for(db_name: str) -> Iterator[Session]:
    engine = get_engine(db_name)
    session = Session(bind=engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
