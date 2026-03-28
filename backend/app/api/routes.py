"""API routes."""
import asyncio
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from typing import Optional

from app.core.database import get_db
from app.models.models import TestCase, TestStep, TestRun, Skill
from app.schemas.schemas import (
    ChatMessage, ChatResponse, TestCaseCreate, TestCaseOut,
    TestRunOut, SkillCreate, SkillOut,
)
from app.services.chat_service import ChatService
from app.services.skill_manager import SkillManager
from app.services.test_executor import TestExecutor
from app.services.report_generator import ReportGenerator

router = APIRouter()


# ========== Chat ==========

@router.post("/chat", response_model=ChatResponse)
async def chat(msg: ChatMessage, db: Session = Depends(get_db)):
    service = ChatService(db)
    result = await service.handle_message(msg.message, msg.url or "", msg.case_id)
    return ChatResponse(**result)


# ========== Test Cases ==========

@router.get("/cases", response_model=list[TestCaseOut])
def list_cases(skip: int = 0, limit: int = 20, db: Session = Depends(get_db)):
    return db.query(TestCase).order_by(TestCase.id.desc()).offset(skip).limit(limit).all()


@router.get("/cases/{case_id}", response_model=TestCaseOut)
def get_case(case_id: int, db: Session = Depends(get_db)):
    case = db.query(TestCase).get(case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    return case


@router.post("/cases", response_model=TestCaseOut)
def create_case(data: TestCaseCreate, db: Session = Depends(get_db)):
    case = TestCase(**data.model_dump(), status="draft")
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


@router.delete("/cases/{case_id}")
def delete_case(case_id: int, db: Session = Depends(get_db)):
    case = db.query(TestCase).get(case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    db.delete(case)
    db.commit()
    return {"ok": True}


# ========== Test Runs ==========

@router.post("/runs")
async def start_run(case_id: int, db: Session = Depends(get_db)):
    case = db.query(TestCase).get(case_id)
    if not case:
        raise HTTPException(404, "Case not found")

    run = TestRun(case_id=case_id, status="queued")
    db.add(run)
    db.flush()

    logs = []
    executor = TestExecutor(db)
    result_run = await executor.run_test(case_id, run.id, logs)

    return {
        "run_id": run.id,
        "status": result_run.status,
        "duration_ms": result_run.duration_ms,
        "log": [l.model_dump() for l in logs],
    }


@router.get("/runs", response_model=list[TestRunOut])
def list_runs(case_id: Optional[int] = None, limit: int = 20, db: Session = Depends(get_db)):
    q = db.query(TestRun).order_by(TestRun.id.desc())
    if case_id:
        q = q.filter(TestRun.case_id == case_id)
    return q.limit(limit).all()


@router.get("/runs/{run_id}", response_model=TestRunOut)
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = db.query(TestRun).get(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return run


# ========== Reports ==========

@router.get("/reports/{run_id}")
def get_report(run_id: int, db: Session = Depends(get_db)):
    gen = ReportGenerator(db)
    html = gen.generate(run_id)
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html)


@router.get("/reports/{run_id}/save")
def save_report(run_id: int, db: Session = Depends(get_db)):
    gen = ReportGenerator(db)
    path = gen.save_report(run_id)
    return {"path": path}


# ========== Skills ==========

@router.get("/skills", response_model=list[SkillOut])
def list_skills(db: Session = Depends(get_db)):
    return db.query(Skill).order_by(Skill.priority.desc()).all()


@router.post("/skills", response_model=SkillOut)
def create_skill(data: SkillCreate, db: Session = Depends(get_db)):
    skill = Skill(**data.model_dump())
    db.add(skill)
    db.commit()
    db.refresh(skill)
    return skill


@router.put("/skills/{skill_id}", response_model=SkillOut)
def update_skill(skill_id: int, data: SkillCreate, db: Session = Depends(get_db)):
    skill = db.query(Skill).get(skill_id)
    if not skill:
        raise HTTPException(404, "Skill not found")
    for k, v in data.model_dump().items():
        setattr(skill, k, v)
    db.commit()
    db.refresh(skill)
    return skill


@router.delete("/skills/{skill_id}")
def delete_skill(skill_id: int, db: Session = Depends(get_db)):
    skill = db.query(Skill).get(skill_id)
    if not skill:
        raise HTTPException(404, "Skill not found")
    db.delete(skill)
    db.commit()
    return {"ok": True}


@router.post("/skills/seed")
def seed_skills(db: Session = Depends(get_db)):
    mgr = SkillManager(db)
    mgr.seed_default_skills()
    return {"ok": True}


# ========== WebSocket for real-time logs ==========

class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        self.active.remove(ws)

    async def broadcast(self, data: dict):
        for ws in self.active:
            try:
                await ws.send_json(data)
            except Exception:
                pass


ws_manager = ConnectionManager()


@router.websocket("/ws/logs")
async def websocket_logs(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)
