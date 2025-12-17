import secrets
from typing import Optional
from datetime import datetime, timedelta
from urllib.parse import urlencode
import httpx
from fastapi import HTTPException, status, Depends, Request, APIRouter, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import SlackConnection, OAuthState
from app.auth.jwt import get_user_id_from_session_token

router = APIRouter(prefix="/oauth/slack", tags=["Slack OAuth"])



@router.get("/start")
def slack_oauth_start(request: Request, db: Session = Depends(get_db)):
    """ 
    Start the Slack OAuth flow for the current user.
    
    Steps:
        - Read session_token
        - Decode it -> user_id
        - create a random OAuthState and store it in the database
        - Redirect user to slack OAuth URL
    
    """
    session_token = request.query_params.get("session_token")
    user_id = get_user_id_from_session_token(session_token)
    
    if not user_id:
        raise HTTPException(status_code = 401, detail = "Unauthorized")
    
    
    # Create a DB-Backed OAuth State 
    state = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(minutes=10)   
    
    db_State = OAuthState(
        provider = "slack",
        state = state,
        user_id = user_id,
        expires_at = expires_at,
        used = False,
    )
    db.add(db_State)
    db.commit()
     
    # Slack OAuth authorize url
    base_authorize_url = "https://slack.com/oauth/v2/authorize"
    
    # Scope
    scopes = [
        "chat:write",
        "channels:history",
        "channels:read",
        "groups:read",
        "users:read",
    ]
    scope_str = ",".join(scopes)
    
    # Build redirect URL to Slack
    params = {
        "client_id": settings.SLACK_CLIENT_ID,
        "scope": scope_str,
        "redirect_uri": settings.SLACK_REDIRECT_URI,
        "state": state,
    }
    
    url = f"{base_authorize_url}?{urlencode(params)}"
    return RedirectResponse(url)

@router.get("/callback")
def slack_oauth_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """ 
    Slack redirects here after the user approves or denies.
    
    Steps:
        - Validate the State from DB (exists, not used, not expired)
        - If error or missing code, fail
        - Exchange code for access token
        - Store/update SlackConnection for the used_id
        - Mark state as used
    """
    
    # 1. Validate State
    if not state:
        raise HTTPException(status_code = 400, detail = "Invalid or missing state")
    
    
    # 1. Fetch state record From DB
    st = (
        db.query(OAuthState).filter(
        OAuthState.provider == "slack", OAuthState.state == state).first()
        )
    
    if not st:
        raise HTTPException(status_code = 400, detail = "Invalid or expired state")
    
    if st.used:
        raise HTTPException(status_code = 400, detail = "State already used")
    
    if datetime.utcnow() > st.expires_at:
        raise HTTPException(status_code = 400, detail = "State expired")
    
    user_id = st.user_id
    
    # 2. Handle user denial or error
    if error:
        st.used = True
        db.commit()
        raise HTTPException(status_code = 400, detail= f"OAuth error: {error}")
    
    if not code:
        raise HTTPException(status_code = 400, detail = "Missing code from Slack")
    
    #  Exchange code for token
    token_url = "https://slack.com/api/oauth.v2.access"
    
    data = {
        "client_id":settings.SLACK_CLIENT_ID,
        "client_secret": settings.SLACK_CLIENT_SECRET,
        "code": code,
        "redirect_uri": settings.SLACK_REDIRECT_URI,
    }
    
    with httpx.Client(timeout=20) as client:
        resp = client.post(token_url, data=data)
        resp_data = resp.json()
        
    if not resp_data.get("ok"):
        details = resp_data.get("error", "unknown_error")
        raise HTTPException(
            status_code = 400,
            detail = f"Slack OAuth token exchange failed: {details}",
        )
        
    # 4. Extract relevant fields from slack response
    
    access_token = resp_data.get("access_token")
    scope = resp_data.get("scope","")
    team = resp_data.get("team",{}) or {}
    team_id = team.get("id")
    team_name = team.get("name")
    
    authed_user = resp_data.get("authed_user",{}) or {}
    authed_user_id = authed_user.get("id")
    
    if not access_token or not team_id:
        raise HTTPException(
            status_code = 400,
            details = "Missing required fields from Slack response",
        )
        
    # 5. Store or update SlackConnection now
    
    existing = (
        db.query(SlackConnection).filter(
            SlackConnection.user_id == user_id,
            SlackConnection.slack_team_id == team_id,
        ).first()
    )
    
    if existing:
        existing.bot_access_token = access_token
        existing.scope = scope
        existing.authed_user_id = authed_user_id
        existing.status = "active"
        existing.slack_team_name = team_name
    else:
        conn = SlackConnection(
            user_id = user_id,
            slack_team_id = team_id,
            slack_team_name= team_name,
            bot_access_token = access_token,
            scope=scope,
            authed_user_id = authed_user_id,
            status = "active",
        )
        db.add(conn)
        
    
    # Mark OAuth State as used
    st.used = True
    
    db.commit()

    # 6. Redirect user back to same page in app
    # redirected to frontend UI
    return {"success": True, "message": "Slack connected successfully"}