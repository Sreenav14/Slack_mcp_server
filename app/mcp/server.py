"""
MCP Server implementation using official MCP SDK.
Provides Slack integration tools for MCP clients.
"""

from mcp.server import Server
from mcp.types import Tool, TextContent
from typing import Any, Optional
import contextvars

from app.db import SessionLocal
from app.models import SlackConnection
from app.slack.client import SlackClient

# Create MCP server instance
server = Server("slack-mcp")

# Context variable to store user_id per request (thread-safe)
_current_user_id: contextvars.ContextVar[Optional[int]] = contextvars.ContextVar(
    "current_user_id", default=None
)


def set_current_user(user_id: int) -> None:
    """Set the current user ID for this request context."""
    _current_user_id.set(user_id)


def get_current_user() -> Optional[int]:
    """Get the current user ID from request context."""
    return _current_user_id.get()


@server.list_tools()
async def list_tools() -> list[Tool]:
    """Return list of available Slack tools."""
    return [
        Tool(
            name="list_channels",
            description="List all Slack channels in the connected workspace",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "number",
                        "description": "Maximum number of channels to return (default: 20)"
                    },
                    "include_private": {
                        "type": "boolean",
                        "description": "Include private channels (default: false)"
                    }
                }
            }
        ),
        Tool(
            name="send_message",
            description="Send a message to a Slack channel",
            inputSchema={
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
                    }
                },
                "required": ["channel_id", "text"]
            }
        ),
        Tool(
            name="fetch_history",
            description="Fetch message history from a Slack channel",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel_id": {
                        "type": "string",
                        "description": "The Slack channel ID"
                    },
                    "limit": {
                        "type": "number",
                        "description": "Number of messages to fetch (default: 10, max: 100)"
                    }
                },
                "required": ["channel_id"]
            }
        )
    ]


def get_slack_client_for_user(user_id: int) -> Optional[SlackClient]:
    """Get Slack client for the specified user."""
    db = SessionLocal()
    try:
        conn = (
            db.query(SlackConnection)
            .filter(
                SlackConnection.user_id == user_id,
                SlackConnection.status == "active"
            )
            .order_by(SlackConnection.installed_at.desc())
            .first()
        )
        if conn and conn.bot_access_token:
            return SlackClient(conn.bot_access_token)
        return None
    finally:
        db.close()


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls from MCP clients."""
    user_id = get_current_user()

    if not user_id:
        return [TextContent(type="text", text="Error: No user context available. Please reconnect.")]

    client = get_slack_client_for_user(user_id)
    if not client:
        return [TextContent(
            type="text",
            text="Slack not connected. Please connect your Slack workspace first."
        )]

    try:
        if name == "list_channels":
            return await handle_list_channels(client, arguments)
        elif name == "send_message":
            return await handle_send_message(client, arguments)
        elif name == "fetch_history":
            return await handle_fetch_history(client, arguments)
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        return [TextContent(type="text", text=f"Error executing {name}: {str(e)}")]


async def handle_list_channels(client: SlackClient, arguments: dict) -> list[TextContent]:
    """Handle list_channels tool."""
    limit = arguments.get("limit", 20)
    include_private = arguments.get("include_private", False)

    response = client.list_channels(limit=limit, include_private=include_private)
    channels = response.get("channels", [])

    if not channels:
        return [TextContent(type="text", text="No channels found in the workspace.")]

    channel_list = "\n".join([
        f"• #{ch.get('name')} (ID: {ch.get('id')}) - {ch.get('num_members', 0)} members"
        for ch in channels
    ])

    return [TextContent(
        type="text",
        text=f"Found {len(channels)} channels:\n\n{channel_list}"
    )]


async def handle_send_message(client: SlackClient, arguments: dict) -> list[TextContent]:
    """Handle send_message tool."""
    channel_id = arguments.get("channel_id")
    text = arguments.get("text")
    thread_ts = arguments.get("thread_ts")

    if not channel_id or not text:
        return [TextContent(type="text", text="Error: channel_id and text are required")]

    response = client.send_message(
        channel_id=channel_id,
        text=text,
        thread_ts=thread_ts
    )

    return [TextContent(
        type="text",
        text=f"✓ Message sent successfully to channel {channel_id}"
    )]


async def handle_fetch_history(client: SlackClient, arguments: dict) -> list[TextContent]:
    """Handle fetch_history tool."""
    channel_id = arguments.get("channel_id")
    limit = min(arguments.get("limit", 10), 100)  # Cap at 100

    if not channel_id:
        return [TextContent(type="text", text="Error: channel_id is required")]

    response = client.fetch_history(channel_id=channel_id, limit=limit)
    messages = response.get("messages", [])

    if not messages:
        return [TextContent(type="text", text=f"No messages found in channel {channel_id}")]

    formatted_messages = []
    for msg in messages:
        user = msg.get("user", "Unknown")
        text = msg.get("text", "")
        ts = msg.get("ts", "")
        formatted_messages.append(f"[{user}]: {text}")

    message_text = "\n\n".join(formatted_messages)

    return [TextContent(
        type="text",
        text=f"Last {len(messages)} messages from {channel_id}:\n\n{message_text}"
    )]
