import os
from contextlib import contextmanager
from datetime import datetime
from typing import Iterable, List, Optional

from sqlalchemy import Column, DateTime, Integer, String, Text, ForeignKey, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from sqlalchemy.orm import relationship


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///teacher_assistant.db")

# Настройка движка: для SQLite добавляем специальные опции
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)

Base = declarative_base()


class LessonPlan(Base):
    __tablename__ = "lesson_plans"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    subject = Column(String(100), nullable=True)
    grade = Column(String(50), nullable=True)
    topic = Column(String(255), nullable=True)
    tags = Column(String(255), nullable=True)  # простая строка с тегами через запятую
    content = Column(Text, nullable=False)  # текст плана урока (Markdown / обычный текст)
    model_name = Column(String(100), nullable=True)
    model_version = Column(String(100), nullable=True)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    visibility = Column(String(20), nullable=False, default="public")  # public/private/pending
    status = Column(String(20), nullable=False, default="published")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    author = relationship("User", back_populates="plans")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(200), unique=True, nullable=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(50), nullable=True, default="user")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    plans = relationship("LessonPlan", back_populates="author")


def init_db() -> None:
    """Создаёт таблицы, если их ещё нет.

    Для небольшого проекта этого достаточно; при переходе на Postgres можно
    оставить тот же код, просто поменяв DATABASE_URL.
    """

    Base.metadata.create_all(bind=engine)


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


def create_lesson_plan(
    *,
    title: str,
    subject: Optional[str] = None,
    grade: Optional[str] = None,
    topic: Optional[str] = None,
    tags: Optional[str] = None,
    content: str,
    model_name: Optional[str] = None,
    model_version: Optional[str] = None,
    author_id: Optional[int] = None,
    visibility: str = "public",
    status: str = "published",
) -> LessonPlan:
    """Создаёт и сохраняет план урока в базе."""

    with get_session() as session:
        plan = LessonPlan(
            title=title,
            subject=subject,
            grade=grade,
            topic=topic,
            tags=tags,
            content=content,
            model_name=model_name,
            model_version=model_version,
            author_id=author_id,
            visibility=visibility,
            status=status,
        )
        session.add(plan)
        session.flush()  # чтобы получить id до commit
        session.refresh(plan)
        return plan


def list_lesson_plans(
    *,
    limit: int = 50,
    search_query: Optional[str] = None,
    subject: Optional[str] = None,
    grade: Optional[str] = None,
) -> List[LessonPlan]:
    """Возвращает список последних планов уроков с простыми фильтрами."""

    with get_session() as session:
        query = session.query(LessonPlan).order_by(LessonPlan.created_at.desc())

        if search_query:
            like = f"%{search_query}%"
            query = query.filter(
                (LessonPlan.title.ilike(like))
                | (LessonPlan.topic.ilike(like))
                | (LessonPlan.content.ilike(like))
            )

        if subject:
            query = query.filter(LessonPlan.subject == subject)

        if grade:
            query = query.filter(LessonPlan.grade == grade)

        return query.limit(limit).all()


def get_lesson_plan(plan_id: int) -> Optional[LessonPlan]:
    """Возвращает один план урока по id или None."""

    with get_session() as session:
        return session.get(LessonPlan, plan_id)


def create_user(*, username: str, email: Optional[str], password_hash: str, role: Optional[str] = "user") -> User:
    with get_session() as session:
        user = User(username=username, email=email, password_hash=password_hash, role=role)
        session.add(user)
        session.flush()
        session.refresh(user)
        return user


def get_user_by_username(username: str) -> Optional[User]:
    with get_session() as session:
        return session.query(User).filter(User.username == username).one_or_none()


def get_user_by_email(email: str) -> Optional[User]:
    with get_session() as session:
        return session.query(User).filter(User.email == email).one_or_none()
