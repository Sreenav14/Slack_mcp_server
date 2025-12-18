from fastapi import APIRouter, Request, HTTPException
from app.auth.jwt import get_user_id_from_session_token

router = APIRouter(prefix="/connect", tags=["connect"])

@router.get("/start")
def get_slack_connect_link(request: Request):
    session_token = request.query_params.get("session_token")
    user_id = get_user_id_from_session_token(session_token)
    
    if not user_id:
        raise HTTPException(status_code=401, detail="unauthorized")
    
    
    # Return the URL the user should open in browser
    connect_url = f"http://127.0.0.1:8000/oauth/slack/start?session_token={session_token}"
    
    return {
        "user_id": user_id,
        "connect_url": connect_url}