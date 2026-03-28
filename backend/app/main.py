"""FastAPI main application."""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.database import engine, Base, SessionLocal
from app.api.routes import router
from app.services.skill_manager import SkillManager


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create tables and seed default skills
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        mgr = SkillManager(db)
        mgr.seed_default_skills()
    finally:
        db.close()

    # Ensure screenshot dirs exist
    os.makedirs(os.path.join(settings.SCREENSHOT_DIR, "reports"), exist_ok=True)

    yield


app = FastAPI(
    title=settings.APP_TITLE,
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(router, prefix="/api")

# Serve screenshots
if os.path.isdir(settings.SCREENSHOT_DIR):
    app.mount("/screenshots", StaticFiles(directory=settings.SCREENSHOT_DIR), name="screenshots")


@app.get("/health")
def health():
    return {"status": "ok", "service": "nl-test-framework"}
