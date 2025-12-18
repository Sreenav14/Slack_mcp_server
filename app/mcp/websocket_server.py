from typing import Any, Dict, List, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.auth.jwt import get_user_id_from_session_token
from app.db import SessionLocal
from app.models import SlackConnection
from app.slack.client import SlackClient


router = APIRouter()

# maps: WebSocket -> User ID
active_connections: Dict[WebSocket, int] = {}


def _connect_url_for_user(session_token: str) -> str:
    return f"https://slack-mcp-server-6809.onrender.com/oauth/slack/start?session_token={session_token}"


# Tool definitions for MCP
TOOLS = [
    {
        "name": "list_channels",
        "description": "List all Slack channels in the connected workspace",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "number",
                    "description": "Maximum number of channels to return (default: 20)"
                },
                "include_private": {
                    "type": "boolean",
                    "description": "Include private channels (default: false)"
                },
            },
        },
    },
    {
        "name": "send_message",
        "description": "Send a message to a Slack channel",
        "inputSchema": {
            "type": "object",
            "properties": {
                "channel_id": {
                    "type": "string",
                    "description": "The Slack channel ID (e.g., C0A1RJ2D0TV)"
                },
                "text": {
                    "type": "string",
                    "description": "The message text to send"
                },
                "thread_ts": {
                    "type": "string",
                    "description": "Thread timestamp to reply to (optional)"
                },
            },
            "required": ["channel_id", "text"],
        },
    },
]


@router.websocket("/mcp/slack")
async def slack_mcp_websocket(websocket: WebSocket):
    """
    WebSocket MCP endpoint for Slack - follows MCP protocol specification.
    """
    session_token = websocket.query_params.get("session_token")
    user_id = get_user_id_from_session_token(session_token)

    if user_id is None:
        await websocket.close(code=1008, reason="Invalid session token")
        return

    await websocket.accept()
    active_connections[websocket] = user_id
    print(f"[MCP] User {user_id} connected")

    try:
        while True:
            message = await websocket.receive_json()
            print(f"[MCP] Received from user {user_id}: {message}")

            msg_id = message.get("id")
            method = message.get("method")
            params = message.get("params", {})

            # ============================================
            # MCP Protocol: initialize
            # ============================================
            if method == "initialize":
                await websocket.send_json({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {
                            "tools": {},
                        },
                        "serverInfo": {
                            "name": "slack-mcp",
                            "version": "1.0.0"
                        }
                    }
                })
                continue

            # ============================================
            # MCP Protocol: notifications/initialized
            # ============================================
            if method == "notifications/initialized" or method == "initialized":
                # This is a notification, no response needed
                continue

            # ============================================
            # MCP Protocol: tools/list
            # ============================================
            if method == "tools/list":
                await websocket.send_json({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "tools": TOOLS
                    }
                })
                continue

            # ============================================
            # MCP Protocol: tools/call
            # ============================================
            if method == "tools/call":
                tool_name = params.get("name")
                args = params.get("arguments") or {}

                db = SessionLocal()
                try:
                    conn = (
                        db.query(SlackConnection)
                        .filter(
                            SlackConnection.user_id == user_id,
                            SlackConnection.status == "active",
                        )
                        .order_by(SlackConnection.installed_at.desc())
                        .first()
                    )

                    if not conn or not conn.bot_access_token:
                        await websocket.send_json({
                            "jsonrpc": "2.0",
                            "id": msg_id,
                            "result": {
                                "content": [
                                    {
                                        "type": "text",
                                        "text": f"Slack not connected. Please connect Slack first: {_connect_url_for_user(session_token or '')}"
                                    }
                                ],
                                "isError": True
                            }
                        })
                        continue

                    client = SlackClient(conn.bot_access_token)

                    # Tool: list_channels
                    if tool_name == "list_channels":
                        limit = args.get("limit", 20)
                        include_private = args.get("include_private", False)

                        try:
                            slack_response = client.list_channels(
                                limit=limit,
                                include_private=include_private,
                            )

                            channels = slack_response.get("channels", [])
                            
                            # Format response as text for MCP
                            channel_list = "\n".join([
                                f"• #{ch.get('name')} (ID: {ch.get('id')})"
                                for ch in channels
                            ])
                            
                            result_text = f"Found {len(channels)} channels:\n{channel_list}"
                            
                            await websocket.send_json({
                                "jsonrpc": "2.0",
                                "id": msg_id,
                                "result": {
                                    "content": [
                                        {
                                            "type": "text",
                                            "text": result_text
                                        }
                                    ]
                                }
                            })
                        except Exception as e:
                            await websocket.send_json({
                                "jsonrpc": "2.0",
                                "id": msg_id,
                                "result": {
                                    "content": [
                                        {
                                            "type": "text",
                                            "text": f"Error listing channels: {str(e)}"
                                        }
                                    ],
                                    "isError": True
                                }
                            })
                        continue

                    # Tool: send_message
                    if tool_name == "send_message":
                        channel_id = args.get("channel_id")
                        text = args.get("text")
                        thread_ts = args.get("thread_ts")

                        if not channel_id or not text:
                            await websocket.send_json({
                                "jsonrpc": "2.0",
                                "id": msg_id,
                                "result": {
                                    "content": [
                                        {
                                            "type": "text",
                                            "text": "Error: Missing required fields 'channel_id' and 'text'"
                                        }
                                    ],
                                    "isError": True
                                }
                            })
                            continue

                        try:
                            slack_response = client.send_message(
                                channel_id=channel_id,
                                text=text,
                                thread_ts=thread_ts,
                            )

                            await websocket.send_json({
                                "jsonrpc": "2.0",
                                "id": msg_id,
                                "result": {
                                    "content": [
                                        {
                                            "type": "text",
                                            "text": f"Message sent successfully to channel {channel_id}"
                                        }
                                    ]
                                }
                            })
                        except Exception as e:
                            await websocket.send_json({
                                "jsonrpc": "2.0",
                                "id": msg_id,
                                "result": {
                                    "content": [
                                        {
                                            "type": "text",
                                            "text": f"Error sending message: {str(e)}"
                                        }
                                    ],
                                    "isError": True
                                }
                            })
                        continue

                    # Unknown tool
                    await websocket.send_json({
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": f"Unknown tool: {tool_name}"
                                }
                            ],
                            "isError": True
                        }
                    })

                finally:
                    db.close()

                continue

            # ============================================
            # Legacy support: tools.list (dot notation)
            # ============================================
            if method == "tools.list":
                await websocket.send_json({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "tools": TOOLS
                    }
                })
                continue

            # ============================================
            # Legacy support: tools.call (dot notation)
            # ============================================
            if method == "tools.call":
                # Redirect to tools/call handler
                tool_name = params.get("name")
                args = params.get("arguments") or {}

                db = SessionLocal()
                try:
                    conn = (
                        db.query(SlackConnection)
                        .filter(
                            SlackConnection.user_id == user_id,
                            SlackConnection.status == "active",
                        )
                        .order_by(SlackConnection.installed_at.desc())
                        .first()
                    )

                    if not conn or not conn.bot_access_token:
                        await websocket.send_json({
                            "jsonrpc": "2.0",
                            "id": msg_id,
                            "error": {
                                "code": -32000,
                                "message": "Slack not connected.",
                            }
                        })
                        continue

                    client = SlackClient(conn.bot_access_token)

                    if tool_name == "list_channels":
                        slack_response = client.list_channels(
                            limit=args.get("limit", 20),
                            include_private=args.get("include_private", False),
                        )
                        channels = slack_response.get("channels", [])
                        await websocket.send_json({
                            "jsonrpc": "2.0",
                            "id": msg_id,
                            "result": {
                                "channels": [
                                    {
                                        "id": ch.get("id"),
                                        "name": ch.get("name"),
                                        "is_private": ch.get("is_private"),
                                        "member_count": ch.get("num_members"),
                                    }
                                    for ch in channels
                                ],
                                "next_cursor": slack_response.get("response_metadata", {}).get("next_cursor")
                            }
                        })
                        continue

                    if tool_name == "send_message":
                        slack_response = client.send_message(
                            channel_id=args.get("channel_id"),
                            text=args.get("text"),
                            thread_ts=args.get("thread_ts"),
                        )
                        await websocket.send_json({
                            "jsonrpc": "2.0",
                            "id": msg_id,
                            "result": {
                                "ok": True,
                                "channel": slack_response.get("channel"),
                                "message_ts": slack_response.get("ts"),
                            }
                        })
                        continue

                finally:
                    db.close()

                continue

            # ============================================
            # Unknown method
            # ============================================
            await websocket.send_json({
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": -32601,
                    "message": f"Unknown method: {method}",
                },
            })

    except WebSocketDisconnect:
        print(f"[MCP] User {user_id} disconnected")

    finally:
        active_connections.pop(websocket, None)
