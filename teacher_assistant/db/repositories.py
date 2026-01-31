from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from .database import get_session
from .models import LessonPlan, Material, User


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
    class_level: Optional[str] = None,
) -> LessonPlan:
    with get_session() as session:
        plan = LessonPlan(
            title=title,
            subject=subject,
            grade=grade,
            class_level=class_level,
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
        session.flush()
        session.refresh(plan)
        return plan


def list_lesson_plans(
    *,
    limit: int = 50,
    search_query: Optional[str] = None,
    subject: Optional[str] = None,
    grade: Optional[str] = None,
) -> List[LessonPlan]:
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
    with get_session() as session:
        return session.get(LessonPlan, plan_id)


def create_material(
    *,
    filename: str,
    uploader_id: Optional[int],
    topics: Optional[str],
    path: Optional[str],
    subject: Optional[str] = None,
    grade: Optional[str] = None,
) -> Material:
    with get_session() as session:
        m = Material(
            filename=filename,
            uploader_id=uploader_id,
            topics=topics,
            path=path,
            subject=subject,
            grade=grade,
        )
        session.add(m)
        session.flush()
        session.refresh(m)
        return m


def list_materials(limit: int = 50) -> List[Material]:
    with get_session() as session:
        return session.query(Material).order_by(Material.created_at.desc()).limit(limit).all()


def delete_material(material_id: int) -> bool:
    with get_session() as session:
        material = session.get(Material, material_id)
        if not material:
            return False
        session.delete(material)
        return True


def create_user(
    *,
    username: str,
    email: Optional[str],
    password_hash: str,
    role: Optional[str] = "user",
) -> User:
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
