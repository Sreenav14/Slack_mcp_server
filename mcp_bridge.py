#!/usr/bin/env python3
"""
Slack MCP Bridge - Connects local MCP clients to remote Slack MCP server.

This bridge translates between stdio (local) and HTTP (remote) transports,
allowing MCP clients like Cursor and Claude Desktop to connect to your
remote Slack MCP server.

Configuration:
    Set these environment variables or create a .env file:
    - SLACK_MCP_TOKEN: Your session token from the Slack MCP server
    - SLACK_MCP_URL: (Optional) Base URL of your MCP server

Usage:
    1. Create a .env file with your SLACK_MCP_TOKEN
    2. Run: python mcp_bridge.py
    3. Configure your MCP client to use this as the command
"""

import sys
import json
import asyncio
import os
from typing import Optional, Any

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import httpx
except ImportError:
    print(json.dumps({
        "jsonrpc": "2.0",
        "id": 0,
        "error": {"code": -32000, "message": "httpx not installed. Run: pip install httpx"}
    }), flush=True)
    sys.exit(1)

# Configuration from environment
SESSION_TOKEN = os.getenv("SLACK_MCP_TOKEN", "")
MCP_SERVER_URL = os.getenv("SLACK_MCP_URL", "https://slack-mcp-server-6809.onrender.com")


def log(message: str):
    """Log to stderr (stdout is reserved for JSON-RPC)."""
    print(f"[Bridge] {message}", file=sys.stderr, flush=True)


def make_response(msg_id: Any, result: dict) -> dict:
    """Create a properly formatted JSON-RPC response."""
    return {
        "jsonrpc": "2.0",
        "id": msg_id if msg_id is not None else 0,
        "result": result
    }


def make_error(msg_id: Any, code: int, message: str) -> dict:
    """Create a properly formatted JSON-RPC error response."""
    return {
        "jsonrpc": "2.0",
        "id": msg_id if msg_id is not None else 0,
        "error": {"code": code, "message": message}
    }


class HTTPBridge:
    """Bridge between stdio and HTTP MCP transports."""

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.client = httpx.AsyncClient(timeout=30.0)

    async def send_request(self, request: dict) -> dict:
        """Send a request to the MCP server via POST."""
        url = f"{self.base_url}/mcp/http?session_token={self.token}"
        msg_id = request.get("id", 0)

        try:
            log(f"Sending to: {url}")
            response = await self.client.post(
                url,
                json=request,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 404:
                log("Server returned 404 - endpoint not found")
                return make_error(msg_id, -32000, "MCP endpoint not found. Server may not be deployed yet.")
            
            response.raise_for_status()
            result = response.json()
            log(f"Got response: {json.dumps(result)[:200]}")
            
            # Ensure the response has a valid id
            if result.get("id") is None:
                result["id"] = msg_id
            
            return result
            
        except httpx.HTTPStatusError as e:
            log(f"HTTP Error: {e.response.status_code} - {e.response.text[:200]}")
            return make_error(msg_id, -32000, f"HTTP Error: {e.response.status_code}")
        except httpx.ConnectError as e:
            log(f"Connection error: {e}")
            return make_error(msg_id, -32000, "Cannot connect to MCP server")
        except Exception as e:
            log(f"Request error: {e}")
            return make_error(msg_id, -32000, str(e))

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()


async def read_stdin_line() -> Optional[str]:
    """Read a line from stdin asynchronously."""
    loop = asyncio.get_event_loop()
    try:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if line:
            return line.strip()
        return ""  # Empty string means EOF
    except Exception:
        return ""


async def main():
    """Main bridge loop."""
    # Validate configuration
    if not SESSION_TOKEN:
        error = make_error(0, -32000, "SLACK_MCP_TOKEN not set. Create a .env file with your session token.")
        print(json.dumps(error), flush=True)
        sys.exit(1)

    log("Starting Slack MCP Bridge...")
    log(f"Server: {MCP_SERVER_URL}")

    bridge = HTTPBridge(MCP_SERVER_URL, SESSION_TOKEN)

    try:
        while True:
            line = await read_stdin_line()

            # EOF detection
            if line == "":
                log("EOF received, shutting down")
                break

            # Skip empty lines (just whitespace)
            if not line:
                continue

            try:
                request = json.loads(line)
            except json.JSONDecodeError as e:
                log(f"Invalid JSON: {e}")
                continue

            method = request.get("method", "")
            msg_id = request.get("id", 0)

            log(f"Request: {method} (id={msg_id})")

            # Handle notifications (no response needed)
            if method.startswith("notifications/") or method == "initialized":
                log(f"Notification: {method}")
                continue

            # Handle initialize locally for faster response
            if method == "initialize":
                response = make_response(msg_id, {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "slack-mcp-bridge",
                        "version": "1.0.0"
                    }
                })
                print(json.dumps(response), flush=True)
                log("Initialized locally")
                continue

            # Forward all other requests to remote server
            response = await bridge.send_request(request)
            print(json.dumps(response), flush=True)
            log(f"Response sent for: {method}")

    except KeyboardInterrupt:
        log("Interrupted")
    except Exception as e:
        log(f"Error: {e}")
        error = make_error(0, -32000, str(e))
        print(json.dumps(error), flush=True)
    finally:
        await bridge.close()
        log("Bridge stopped")


if __name__ == "__main__":
    asyncio.run(main())
