import secrets
from typing import Optional

from urllib.parse import urlencode
import httpx
from fastapi import HTTPException, status, Depends, Request, APIRouter
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import SlackConnection
from app.auth import DEV_USER_ID

router = APIRouter(prefix="/oauth/slack", tags=["Slack OAuth"])

# In-memory store for OAuth state for mvp (per-process only)
oauth_state_store : dict[str,int] = {}
# maps: state -> user_id

@router.get("/start")
def slack_oauth_start(db: Session = Depends(get_db)):
    """ 
    Start the Slack OAuth flow for the current user.
    
    for MVP:
        - we assume dev user with id=DEV_USER_ID is logged in.
        - we generate a random `state`.
        - we store `state -> user_id` in a simple in-memory store.
        - we direct to Slack's OAuth authorization URL.
    
    """
    user_id = DEV_USER_ID
    
    # Generate random state token to protect against CSRF 
    state = secrets.token_urlsafe(32)
    oauth_state_store[state] = user_id
    
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
    We:
        - Validate state.
        - Exchange code for access token.
        - Store/update SlackConnection for the user.
    """
    
    # 1. Validate State
    if not state or state not in oauth_state_store:
        raise HTTPException(status_code = 400, details = "Invalid or missing state")
    
    user_id = oauth_state_store.pop(state) # consume state
    
    # 2. Handle user denial or error
    if error:
        # You can redirect to UI with an error message instead.
        raise HTTPException(status_code = 400, details = f"OAuth error: {error}")
    
    if not code:
        raise HTTPException(status_code = 400, details = "Missing code from Slack")
    
    #  Exchange code for token
    token_url = "https://slack.com/api/oauth.v2.access"
    
    data = {
        "client_id":settings.SLACK_CLIENT_ID,
        "client_secret": settings.SLACK_CLIENT_SECRET,
        "code": code,
        "redirect_uri": settings.SLACK_REDIRECT_URI,
    }
    
    with httpx.Client() as client:
        resp = client.post(token_url, data=data)
        resp_data = resp.json()
        
    if not resp_data.get("ok"):
        details = resp_data.get("error", "unknown_error")
        raise HTTPException(
            status_code = 400,
            details = f"Slack OAuth token exchange failed: {details}",
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
            SlackConnection.team_id == team_id,
        ).first()
    )
    
    if existing:
        existing.bot_access_token = access_token
        existing.scope = scope
        existing.authed_user_id = authed_user_id
        existing.status = "active"
    else:
        conn = SlackConnection(
            user_id = user_id,
            team_id = team_id,
            slack_team_name= team_name,
            bot_access_token = access_token,
            scope=scope,
            authed_user_id = authed_user_id,
            status = "active",
        )
        db.add(conn)
        
    db.commit()
    
    # 6. Redirect user back to same page in app
    # redirected to frontend UI
    return {"success": True, "message": "Slack connected successfully"}