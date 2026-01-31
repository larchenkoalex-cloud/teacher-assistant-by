"""Service layer: thin wrappers around DB repositories and simple business logic.

Keep Streamlit UI thin by calling functions from here instead of directly using
DB repositories. This file re-exports model classes and CRUD functions with
stable names used by the existing UI.
"""
from typing import Optional, List

from teacher_assistant.db import (
    LessonPlan,
    Material,
    User,
    init_db,
    create_lesson_plan as _create_lesson_plan,
    list_lesson_plans as _list_lesson_plans,
    get_lesson_plan as _get_lesson_plan,
    create_material as _create_material,
    list_materials as _list_materials,
    delete_material as _delete_material,
    create_user as _create_user,
    get_user_by_username as _get_user_by_username,
    get_user_by_email as _get_user_by_email,
)


def create_lesson_plan(*, title: str, subject: Optional[str] = None, grade: Optional[str] = None,
                       topic: Optional[str] = None, tags: Optional[str] = None, content: str = "",
                       model_name: Optional[str] = None, model_version: Optional[str] = None,
                       author_id: Optional[int] = None, visibility: str = "public",
                       status: str = "published", class_level: Optional[str] = None) -> LessonPlan:
    # Placeholder for business logic (validation, sanitization) before save
    return _create_lesson_plan(
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
        class_level=class_level,
    )


def list_lesson_plans(*, limit: int = 50, search_query: Optional[str] = None,
                      subject: Optional[str] = None, grade: Optional[str] = None) -> List[LessonPlan]:
    return _list_lesson_plans(limit=limit, search_query=search_query, subject=subject, grade=grade)


def get_lesson_plan(plan_id: int) -> Optional[LessonPlan]:
    return _get_lesson_plan(plan_id)


def create_material(*, filename: str, uploader_id: Optional[int], topics: Optional[str], path: Optional[str],
                    subject: Optional[str] = None, grade: Optional[str] = None) -> Material:
    return _create_material(filename=filename, uploader_id=uploader_id, topics=topics, path=path, subject=subject, grade=grade)


def list_materials(limit: int = 50) -> List[Material]:
    return _list_materials(limit=limit)


def delete_material(material_id: int) -> bool:
    return _delete_material(material_id)


def create_user(*, username: str, email: Optional[str], password_hash: str, role: Optional[str] = "user") -> User:
    return _create_user(username=username, email=email, password_hash=password_hash, role=role)


def get_user_by_username(username: str) -> Optional[User]:
    return _get_user_by_username(username)


def get_user_by_email(email: str) -> Optional[User]:
    return _get_user_by_email(email)


__all__ = [
    "LessonPlan",
    "Material",
    "User",
    "init_db",
    "create_lesson_plan",
    "list_lesson_plans",
    "get_lesson_plan",
    "create_material",
    "list_materials",
    "delete_material",
    "create_user",
    "get_user_by_username",
    "get_user_by_email",
]
