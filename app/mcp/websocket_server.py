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
    return f"http://127.0.0.1:8000/oauth/start?session_token={session_token}"


@router.websocket("/mcp/slack")
async def slack_mcp_websocket(websocket: WebSocket):
    """
    WebSocket MCP endpoint for slack.
    """
    session_token = websocket.query_params.get("session_token")
    user_id = get_user_id_from_session_token(session_token)

    if user_id is None:
        await websocket.close(code=1008, reason="Invalid session token")
        return

    await websocket.accept()
    active_connections[websocket] = user_id
    print(f"[WebSocket] User {user_id} connected")

    try:
        await websocket.send_json({
            "type": "welcome",
            "message": "Welcome to the Slack MCP! You are now connected.",
            "user_id": user_id,
        })

        while True:
            message = await websocket.receive_json()
            print(f"[WebSocket] Received from user {user_id}: {message}")

            msg_id = message.get("id")
            method = message.get("method")
            params = message.get("params", {})

            # Handle tools.list
            if method == "tools.list":
                await websocket.send_json({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "tools": [
                            {
                                "name": "list_channels",
                                "description": "List all channels in the workspace",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "query": {"type": "string"},
                                        "limit": {"type": "number"},
                                        "include_private": {"type": "boolean"},
                                    },
                                },
                            },
                            {
                                "name": "send_message",
                                "description": "Send a message to a channel",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "channel_id": {"type": "string"},
                                        "text": {"type": "string"},
                                        "thread_ts": {"type": "string"},
                                        "reply_broadcast": {"type": "boolean"},
                                    },
                                    "required": ["channel_id", "text"],
                                },
                            },
                        ]
                    }
                })
                continue

            # Handle tools.call
            if method == "tools.call":
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
                                "message": "Slack not connected. Connect Slack and try again.",
                                "data": {
                                    "connect_url": _connect_url_for_user(session_token or ""),
                                },
                            },
                        })
                        continue

                    client = SlackClient(conn.bot_access_token)

                    # Tool: list_channels
                    if tool_name == "list_channels":
                        limit = args.get("limit", 20)
                        include_private = args.get("include_private", False)

                        slack_response = client.list_channels(
                            limit=limit,
                            include_private=include_private,
                        )

                        channels = slack_response.get("channels", [])
                        next_cursor = slack_response.get("response_metadata", {}).get("next_cursor")

                        transformed = {
                            "channels": [
                                {
                                    "id": ch.get("id"),
                                    "name": ch.get("name"),
                                    "is_private": ch.get("is_private"),
                                    "member_count": ch.get("num_members"),
                                }
                                for ch in channels
                            ],
                            "next_cursor": next_cursor,
                        }
                        await websocket.send_json({
                            "jsonrpc": "2.0",
                            "id": msg_id,
                            "result": transformed,
                        })
                        continue

                    # Tool: send_message
                    if tool_name == "send_message":
                        channel_id = args.get("channel_id")
                        text = args.get("text")
                        thread_ts = args.get("thread_ts")
                        reply_broadcast = args.get("reply_broadcast", False)

                        if not channel_id or not text:
                            await websocket.send_json({
                                "jsonrpc": "2.0",
                                "id": msg_id,
                                "error": {
                                    "code": -32602,
                                    "message": "Missing required fields: channel_id and text",
                                }
                            })
                            continue

                        try:
                            slack_response = client.send_message(
                                channel_id=channel_id,
                                text=text,
                                thread_ts=thread_ts,
                                reply_broadcast=reply_broadcast,
                            )
                        except Exception as e:
                            await websocket.send_json({
                                "jsonrpc": "2.0",
                                "id": msg_id,
                                "error": {
                                    "code": -32000,
                                    "message": f"Failed to send message: {str(e)}",
                                }
                            })
                            continue

                        channel_out = slack_response.get("channel")
                        message_ts = slack_response.get("ts")

                        thread_ts_out = None
                        if isinstance(slack_response.get("message"), dict):
                            thread_ts_out = slack_response["message"].get("thread_ts")
                        if not thread_ts_out:
                            thread_ts_out = slack_response.get("thread_ts")

                        await websocket.send_json({
                            "jsonrpc": "2.0",
                            "id": msg_id,
                            "result": {
                                "ok": True,
                                "channel": channel_out,
                                "message_ts": message_ts,
                                "thread_ts": thread_ts_out,
                            }
                        })
                        continue

                    # Unknown tool
                    await websocket.send_json({
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "error": {
                            "code": -32601,
                            "message": f"Unknown tool: {tool_name}",
                        }
                    })

                finally:
                    db.close()

                continue

            # Unknown method
            await websocket.send_json({
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": -32601,
                    "message": f"Unknown method: {method}",
                },
            })

    except WebSocketDisconnect:
        print(f"[WebSocket] User {user_id} disconnected")

    finally:
        active_connections.pop(websocket, None)
