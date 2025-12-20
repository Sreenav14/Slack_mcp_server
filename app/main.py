"""
Slack MCP Server - FastAPI Application

A Model Context Protocol (MCP) server for Slack integration.
Uses SSE (Server-Sent Events) transport for remote MCP connections.
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from mcp.server.sse import SseServerTransport

from app.db import Base, engine
from app.oauth.slack import router as slack_oauth_router
from app.auth.routes import router as auth_router
from app.auth.jwt import get_user_id_from_session_token
from app.mcp.server import server as mcp_server, set_current_user, list_tools, call_tool

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


@app.post("/mcp/http")
async def mcp_http_endpoint(request: Request, session_token: str = None):
    """
    HTTP-based MCP endpoint for bridge clients.
    
    This is a simpler endpoint that doesn't require SSE.
    Connect using: POST /mcp/http?session_token=<your_token>
    """
    if not session_token:
        return JSONResponse(
            status_code=401,
            content={
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32001, "message": "session_token is required"}
            }
        )

    user_id = get_user_id_from_session_token(session_token)
    if not user_id:
        return JSONResponse(
            status_code=401,
            content={
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32001, "message": "Invalid or expired session token"}
            }
        )

    # Set user context for this request
    set_current_user(user_id)

    try:
        body = await request.json()
    except Exception as e:
        return JSONResponse(
            content={
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {str(e)}"}
            }
        )

    method = body.get("method", "")
    msg_id = body.get("id")
    params = body.get("params", {})

    # Handle different MCP methods
    if method == "initialize":
        return JSONResponse(content={
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "slack-mcp-server",
                    "version": "1.0.0"
                }
            }
        })

    elif method == "tools/list":
        tools = await list_tools()
        return JSONResponse(content={
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "tools": [
                    {
                        "name": t.name,
                        "description": t.description,
                        "inputSchema": t.inputSchema
                    }
                    for t in tools
                ]
            }
        })

    elif method == "tools/call":
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {})

        result = await call_tool(tool_name, tool_args)

        return JSONResponse(content={
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "content": [
                    {"type": r.type, "text": r.text}
                    for r in result
                ]
            }
        })

    else:
        return JSONResponse(content={
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"}
        })


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
