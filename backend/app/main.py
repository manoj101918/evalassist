from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import exams, export, questions, review, scripts, session, users

app = FastAPI(title="EvalAssist API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

for r in (session, users, exams, questions, scripts, review, export):
    app.include_router(r.router)


@app.get("/health")
def health():
    return {"ok": True}
