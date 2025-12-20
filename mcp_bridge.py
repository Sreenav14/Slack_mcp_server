#!/usr/bin/env python3
"""
Slack MCP Bridge - Connects local MCP clients to remote Slack MCP server.

This bridge translates between stdio (local) and SSE (remote) transports,
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
from typing import Optional

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
        "id": None,
        "error": {"code": -32000, "message": "httpx not installed. Run: pip install httpx"}
    }), flush=True)
    sys.exit(1)

# Configuration from environment
SESSION_TOKEN = os.getenv("SLACK_MCP_TOKEN", "")
MCP_SERVER_URL = os.getenv("SLACK_MCP_URL", "https://slack-mcp-server-6809.onrender.com")


def log(message: str):
    """Log to stderr (stdout is reserved for JSON-RPC)."""
    print(f"[Bridge] {message}", file=sys.stderr, flush=True)


class SSEBridge:
    """Bridge between stdio and SSE MCP transports."""

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.client = httpx.AsyncClient(timeout=30.0)
        self.initialized = False

    async def send_request(self, request: dict) -> dict:
        """Send a request to the MCP server via POST."""
        url = f"{self.base_url}/mcp/messages?session_token={self.token}"
        
        try:
            response = await self.client.post(
                url,
                json=request,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            return {
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "error": {"code": -32000, "message": f"HTTP Error: {e.response.status_code}"}
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "error": {"code": -32000, "message": str(e)}
            }

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()


async def read_stdin_line() -> Optional[str]:
    """Read a line from stdin asynchronously."""
    loop = asyncio.get_event_loop()
    try:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        return line.strip() if line else None
    except Exception:
        return None


async def main():
    """Main bridge loop."""
    # Validate configuration
    if not SESSION_TOKEN:
        error = {
            "jsonrpc": "2.0",
            "id": None,
            "error": {
                "code": -32000,
                "message": "SLACK_MCP_TOKEN not set. Create a .env file with your session token."
            }
        }
        print(json.dumps(error), flush=True)
        sys.exit(1)

    log("Starting Slack MCP Bridge...")
    log(f"Server: {MCP_SERVER_URL}")

    bridge = SSEBridge(MCP_SERVER_URL, SESSION_TOKEN)

    try:
        while True:
            line = await read_stdin_line()

            if not line:
                log("EOF received, shutting down")
                break

            try:
                request = json.loads(line)
            except json.JSONDecodeError as e:
                log(f"Invalid JSON: {e}")
                continue

            method = request.get("method", "")
            msg_id = request.get("id")

            log(f"Request: {method}")

            # Handle initialize locally (MCP handshake)
            if method == "initialize":
                response = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {
                            "name": "slack-mcp-bridge",
                            "version": "1.0.0"
                        }
                    }
                }
                print(json.dumps(response), flush=True)
                log("Initialized")
                continue

            # Handle notifications (no response needed)
            if method.startswith("notifications/") or method == "initialized":
                continue

            # Forward all other requests to remote server
            response = await bridge.send_request(request)
            print(json.dumps(response), flush=True)
            log(f"Response: {method}")

    except KeyboardInterrupt:
        log("Interrupted")
    except Exception as e:
        log(f"Error: {e}")
        error = {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32000, "message": str(e)}
        }
        print(json.dumps(error), flush=True)
    finally:
        await bridge.close()
        log("Bridge stopped")


if __name__ == "__main__":
    asyncio.run(main())
