from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import Base, engine, SessionLocal
from app.models import User
from app.oauth.slack import router as slack_oauth_router
from app.mcp.websocket_server import router as mcp_websocket_router
from app.auth.routes import router as auth_router
from app.connect.routes import router as connect_router

app = FastAPI()

app.include_router(slack_oauth_router)
app.include_router(mcp_websocket_router)
app.include_router(auth_router)
app.include_router(connect_router)


@app.on_event("startup")
def on_startup():
   pass


@app.get("/health")
def health_check():
    return {"status": "ok"}