"""Pydantic schemas for API."""
from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime


# --- Chat / NL Input ---
class ChatMessage(BaseModel):
    message: str
    url: Optional[str] = None
    case_id: Optional[int] = None


class ChatResponse(BaseModel):
    reply: str
    case_id: Optional[int] = None
    steps: Optional[list[dict]] = None
    log: Optional[list[dict]] = None


# --- Test Case ---
class TestCaseCreate(BaseModel):
    name: str
    description: Optional[str] = None
    target_url: str
    natural_input: str


class TestCaseOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    target_url: str
    natural_input: str
    status: str
    created_at: datetime
    updated_at: datetime
    steps: list["TestStepOut"] = []

    class Config:
        from_attributes = True


# --- Test Step ---
class TestStepOut(BaseModel):
    id: int
    case_id: int
    step_order: int
    action: str
    target: str
    value: Optional[str]
    locator_strategy: Optional[str]
    locator_value: Optional[str]
    iframe_hint: Optional[str]
    timeout_ms: int
    raw_text: Optional[str]
    status: str

    class Config:
        from_attributes = True


# --- Test Run ---
class RunRequest(BaseModel):
    case_id: int


class TestRunOut(BaseModel):
    id: int
    case_id: int
    status: str
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    duration_ms: Optional[int]
    error_message: Optional[str]
    step_results: list["StepResultOut"] = []

    class Config:
        from_attributes = True


class StepResultOut(BaseModel):
    id: int
    step_order: int
    status: str
    duration_ms: Optional[int]
    error_message: Optional[str]
    screenshot_path: Optional[str]
    iframe_path: Optional[list]
    element_info: Optional[dict]

    class Config:
        from_attributes = True


# --- Skill ---
class SkillCreate(BaseModel):
    name: str
    description: Optional[str] = None
    category: str
    url_pattern: Optional[str] = None
    rules: dict
    priority: int = 0


class SkillOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    category: str
    url_pattern: Optional[str]
    rules: dict
    priority: int
    enabled: int
    created_at: datetime

    class Config:
        from_attributes = True


# --- WebSocket Log ---
class LogEntry(BaseModel):
    timestamp: str
    level: str  # info, warn, error, debug, iframe, locator, action
    message: str
    detail: Optional[Any] = None
    step_order: Optional[int] = None
