"""Compatibility facade.

`streamlit_app.py` and scripts historically imported DB models and CRUD helpers
from `storage.py`. For scalability and clearer layering, the implementation has
moved to `teacher_assistant.db.*`, while this module re-exports the same public
API to avoid breaking imports.
"""

from teacher_assistant.db.base import Base
from teacher_assistant.db.database import DATABASE_URL, SessionLocal, engine, get_session, init_db
from teacher_assistant.db.models import LessonPlan, Material, User
from teacher_assistant.db.repositories import (
    create_lesson_plan,
    create_material,
    create_user,
    delete_material,
    get_lesson_plan,
    get_user_by_email,
    get_user_by_username,
    list_lesson_plans,
    list_materials,
)

__all__ = [
    "Base",
    "DATABASE_URL",
    "engine",
    "SessionLocal",
    "get_session",
    "init_db",
    "LessonPlan",
    "User",
    "Material",
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
