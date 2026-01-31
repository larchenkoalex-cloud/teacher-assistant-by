from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterable

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from .base import Base


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///teacher_assistant.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, future=True)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    future=True,
    expire_on_commit=False,
)


def init_db() -> None:
    """Создаёт таблицы, если их ещё нет.

    Для небольшого проекта этого достаточно; при переходе на Postgres можно
    оставить тот же код, просто поменяв DATABASE_URL.
    """

    # Важно: импортируем модели, чтобы они зарегистрировались в Base.metadata
    from . import models as _models  # noqa: F401

    Base.metadata.create_all(bind=engine)

    # Простая миграция: если добавлено новое поле `class_level`, добавляем колонку в существующую таблицу
    try:
        with engine.connect() as conn:
            try:
                res = conn.execute(text("PRAGMA table_info('lesson_plans')"))
                cols = [r[1] for r in res.fetchall()]
            except Exception:
                cols = []

            if "class_level" not in cols:
                try:
                    conn.execute(text("ALTER TABLE lesson_plans ADD COLUMN class_level VARCHAR(50)"))
                except Exception:
                    pass
    except Exception:
        pass


@contextmanager
def get_session() -> Iterable[Session]:
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
