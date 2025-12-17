# App Module

This is the main application module for the Slack MCP Server.

## Structure

```
app/
├── main.py              # FastAPI app initialization & startup
├── config.py            # Environment variable configuration
├── db.py                # SQLAlchemy database setup
├── models.py            # Database models (User, SlackConnection, OAuthState)
├── auth/
│   ├── __init__.py      # Module exports (get_user_id_from_session_token)
│   ├── jwt.py           # JWT token creation & validation
│   ├── passwords.py     # Bcrypt password hashing & verification
│   └── routes.py        # Authentication endpoints (/auth/signup, /auth/login)
├── oauth/
│   └── slack.py         # Slack OAuth 2.0 flow
├── slack/
│   └── client.py        # Slack Web API wrapper
└── mcp/
    ├── websocket_server.py  # MCP WebSocket handler
    └── tools/               # MCP tool implementations
        ├── slack_fetch_history.py
        ├── slack_list_channels.py
        └── slack_send_message.py
```

## Key Components

- **main.py** - Entry point, includes routers and startup logic
- **config.py** - Loads environment variables using python-dotenv
- **db.py** - SQLAlchemy engine and session configuration
- **models.py** - User, SlackConnection, and OAuthState ORM models
- **auth/** - Authentication module with JWT tokens and password hashing
- **oauth/slack.py** - Handles Slack OAuth authorization flow
- **slack/client.py** - Wrapper for Slack API calls
- **mcp/websocket_server.py** - WebSocket endpoint for MCP protocol

See the main [README.md](../README.md) for full documentation.
