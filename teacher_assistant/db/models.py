from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from .base import Base


class LessonPlan(Base):
    __tablename__ = "lesson_plans"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    subject = Column(String(100), nullable=True)
    grade = Column(String(50), nullable=True)
    topic = Column(String(255), nullable=True)
    class_level = Column(String(50), nullable=True)
    tags = Column(String(255), nullable=True)
    content = Column(Text, nullable=False)
    model_name = Column(String(100), nullable=True)
    model_version = Column(String(100), nullable=True)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    visibility = Column(String(20), nullable=False, default="public")
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


class Material(Base):
    __tablename__ = "materials"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(300), nullable=False)
    uploader_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    topics = Column(String(1000), nullable=True)
    path = Column(String(1000), nullable=True)
    subject = Column(String(100), nullable=True)
    grade = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    uploader = relationship("User")
