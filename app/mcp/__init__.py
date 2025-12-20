# app/mcp/__init__.py
"""MCP Server module for Slack integration."""

from .server import server, set_current_user, get_current_user

__all__ = ["server", "set_current_user", "get_current_user"]
