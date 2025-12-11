from typing import Optional

from app.config import settings

# For MVP purpose

DEV_SESSION_TOKEN = "dev-user-1-token"
DEV_USER_ID = 1

def get_user_id_from_session_token(session_token: str) -> Optional[int]:
    """
    Very Simple dev-only mapping from a session token to a user_id.
    
    for now:
    - If the token matches the DEV_SESSION_TOKEN, return DEV_USER_ID.
    - otherwise return none (invalid/unknown session)
    
    Later, you can:
    - Parse a JWT using settings.APP_SECRET_KEY
    - Or look up the token in a 'sessions' table.
    
    """
    
    if not session_token:
        return None
    
    if session_token == DEV_SESSION_TOKEN:
        return DEV_USER_ID
    
    return None
    