from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.auth.jwt import create_session_token
from app.auth.passwords import hash_password, verify_password
from app.auth.jwt import get_user_id_from_session_token

router = APIRouter(prefix="/auth", tags=["auth"])

class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str | None = None

class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    
class AuthResponse(BaseModel):
    user_id : int
    session_token : str

@router.post("/signup", response_model=AuthResponse)
def signup(payload: SignupRequest, db: Session = Depends(get_db)):
    if not payload.email:
        raise HTTPException(status_code = 400, detail = "Email is required")
    
    existing = db.query(User).filter(User.email==payload.email).first()
    
    if existing:
        raise HTTPException(status_code = 400, detail = "User already exists")

    user = User(
        email = payload.email,
        name = payload.name,
        password_hash = hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    return AuthResponse(user_id=user.id, session_token=create_session_token(user.id))

@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email==payload.email).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    return AuthResponse(user_id=user.id, session_token=create_session_token(user.id))


@router.get("/me")
def me(request: Request, db: Session = Depends(get_db)):
    session_token = request.query_params.get("session_token")
    user_id = get_user_id_from_session_token(session_token)
    
    if not user_id:
        raise HTTPException(status_code=401, detail="unauthorized")
    
    user = db.query(User).filter(User.id==user_id).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "user_id": user.id,
        "email": user.email,
        "name": user.name,
    }
    
    