from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from typing import Optional
import os

app = FastAPI(title="Deepseek Mock API")

class SearchRequest(BaseModel):
    query: str

class LessonPlanRequest(BaseModel):
    subject: Optional[str] = None
    grade: Optional[str] = None
    topic: Optional[str] = None
    notes: Optional[str] = None

def check_auth(authorization: Optional[str]):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid Authorization scheme")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Empty token")
    # optional: validate against env var if set
    env = os.getenv("DEEPSEEK_API_KEY")
    if env and token != env:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return token

@app.post("/search")
async def search(body: SearchRequest, authorization: Optional[str] = Header(None)):
    check_auth(authorization)
    q = body.query or ""
    # return a small mock result set
    results = [
        {"title": f"Результат по '{q}' — пример 1", "snippet": f"Короткое описание для запроса '{q}' (файл: example1.pdf)"},
        {"title": f"Результат по '{q}' — пример 2", "snippet": f"Короткое описание для запроса '{q}' (файл: example2.docx)"},
    ]
    return {"results": results}

@app.post("/lesson-plan")
async def lesson_plan(body: LessonPlanRequest, authorization: Optional[str] = Header(None)):
    check_auth(authorization)
    subject = body.subject or "Предмет"
    grade = body.grade or "Класс"
    topic = body.topic or "Тема"
    notes = body.notes or ""
    plan = f"План урока (mock)\nПредмет: {subject}\nКласс: {grade}\nТема: {topic}\n\nОсновная часть:\n- Введение\n- Основной материал\n- Закрепление\n\nПримечания: {notes}\n"
    return {"plan": plan, "model_name": "deepseek-mock", "model_version": "0.0.1"}
