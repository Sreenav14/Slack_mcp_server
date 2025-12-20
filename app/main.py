"""
Slack MCP Server - FastAPI Application

A Model Context Protocol (MCP) server for Slack integration.
Uses SSE (Server-Sent Events) transport for remote MCP connections.
"""

from fastapi import FastAPI, HTTPException, Request
from mcp.server.sse import SseServerTransport

from app.db import Base, engine
from app.oauth.slack import router as slack_oauth_router
from app.auth.routes import router as auth_router
from app.auth.jwt import get_user_id_from_session_token
from app.mcp.server import server as mcp_server, set_current_user

app = FastAPI(
    title="Slack MCP Server",
    description="Model Context Protocol server for Slack integration",
    version="1.0.0"
)

# Include routers
app.include_router(auth_router)
app.include_router(slack_oauth_router)

# SSE Transport for MCP connections
sse_transport = SseServerTransport("/mcp/messages")


@app.get("/mcp/sse")
async def mcp_sse_endpoint(request: Request, session_token: str = None):
    """
    SSE-based MCP endpoint for AI clients.
    
    Connect using: GET /mcp/sse?session_token=<your_token>
    """
    if not session_token:
        raise HTTPException(status_code=401, detail="session_token is required")

    user_id = get_user_id_from_session_token(session_token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired session token")

    # Set user context for this connection
    set_current_user(user_id)

    async with sse_transport.connect_sse(
        request.scope, request.receive, request._send
    ) as (read_stream, write_stream):
        await mcp_server.run(
            read_stream,
            write_stream,
            mcp_server.create_initialization_options()
        )


@app.post("/mcp/messages")
async def mcp_messages_endpoint(request: Request):
    """Handle POST messages for SSE transport."""
    return await sse_transport.handle_post_message(
        request.scope, request.receive, request._send
    )


@app.on_event("startup")
def on_startup():
    """Initialize database tables on startup."""
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/")
def root():
    """Root endpoint with API info."""
    return {
        "name": "Slack MCP Server",
        "version": "1.0.0",
        "mcp_endpoint": "/mcp/sse?session_token=<token>",
        "docs": "/docs"
    }
