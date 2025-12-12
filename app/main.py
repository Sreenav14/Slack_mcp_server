from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import Base, engine, SessionLocal
from app.models import User
from app.oauth.slack import router as slack_oauth_router
from app.mcp.websocket_server import router as mcp_websocket_router

app = FastAPI()

app.include_router(slack_oauth_router)
app.include_router(mcp_websocket_router)

@app.on_event("startup")
def on_startup():
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    # Ensure a dev user exists
    db : Session = SessionLocal()
    try:
        user = db.query(User).filter(User.id==1).first()
        if not user:
            dev_user = User(id=1, email="dev@example.com", name="Dev User")
            db.add(dev_user)
            db.commit()
            db.refresh(dev_user)
            print(f"[startup] Created dev User with id=1")
        else:
            print(f"[startup] Dev User already exists with id=1")
    finally:
        db.close()
        
@app.get("/health")
def health_check():
    return {"status": "ok"}