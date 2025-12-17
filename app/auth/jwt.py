from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
import jwt

from app.config import settings

def create_session_token(user_id: int) -> str:
    """ 
    Create a signed JWT session token for a given user_id.
    
    """
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=settings.JWT_EXP_MINUTES)
    
    payload = {
        "sub" : str(user_id),
        "iat" : now.timestamp(),
        "exp" : exp.timestamp(),
    }
    token = jwt.encode(payload, settings.APP_SECRET_KEY, algorithm="HS256")
    return token


def get_user_id_from_session_token(token: Optional[str]) -> Optional[int]:
    """ 
    Decode JWT and return user_id if valid, else None.
    """
    if not token:
        return None
    
    try:
        payload = jwt.decode(token, settings.APP_SECRET_KEY, algorithms=["HS256"])
        sub = payload.get("sub")
        if not sub:
            return None
        return int(sub)
    
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
    
    
    
    