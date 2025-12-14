# App Module

This is the main application module for the Slack MCP Server.

## Structure

```
app/
├── main.py              # FastAPI app initialization & startup
├── config.py            # Environment variable configuration
├── db.py                # SQLAlchemy database setup
├── models.py            # Database models (User, SlackConnection)
├── auth.py              # Authentication helpers
├── oauth/
│   └── slack.py         # Slack OAuth 2.0 flow
├── slack/
│   └── client.py        # Slack Web API wrapper
└── mcp/
    └── websocket_server.py  # MCP WebSocket handler
```

## Key Components

- **main.py** - Entry point, includes routers and startup logic
- **config.py** - Loads environment variables using python-dotenv
- **db.py** - SQLAlchemy engine and session configuration
- **models.py** - User and SlackConnection ORM models
- **oauth/slack.py** - Handles Slack OAuth authorization flow
- **slack/client.py** - Wrapper for Slack API calls
- **mcp/websocket_server.py** - WebSocket endpoint for MCP protocol

See the main [README.md](../README.md) for full documentation.

