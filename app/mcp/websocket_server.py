from typing import Optional, Any, Dict, List, AsyncGenerator
from fastapi import WebSocket, WebSocketDisconnect, APIRouter
from app.auth import get_user_id_from_session_token

router = APIRouter()

# keeping track of connections
# maps: WebSocket -> user_id
active_connections: Dict[WebSocket, int] = {}

@router.websocket("/mcp/slack")
async def slack_mcp_websocket(websocket: WebSocket):
    """ 
    Basic WebSocket endpoint for slack MCP.
    
    step 1 (MVP):
        - Read `Session_token` from query params.
        - Map it to `user_id`.
        - If invalid, close connection.
        - If valid, accept the connection and send a welcome message.
        - Then echo any messages recieved (for testing).

    """ 
    
    #  Read session_token from query params
    session_token:Optional[str] = websocket.query_params.get("session_token")
    
    # 2. Map Session_token -> user_id using our oauth helper
    user_id = get_user_id_from_session_token(session_token)
    
    if user_id is None:
        # invalid or missing session token
        # 1008 = "policy voilation"
        await websocket.close(code=1008)
        return
    
    # 3. Accept connection and track user
    await websocket.accept()
    
    # 4. Register this connection in our in-memory map
    active_connections[websocket] = user_id
    print(f"[WebSocket] User {user_id} connected")
    
    try:
        # Send a simple welcome message so we know it's working
        
        await websocket.send_json({
            "type": "welcome",
            "message": "Welcome to the Slack MCP! You are now connected.",
            "user_id": user_id,
        })
        
        
        
        while True:
            # we expect a json message from client
            message = await websocket.receive_json()
            print (f"[websocket] recieved from user {user_id}: {message}")
            
            # Basic shape: {"jsonrpc":"2.0", "id":"...", "method":"...","params":{...}}
            msg_id = message.get("id")
            method = message.get("method")
            params = message.get("params", {})
            
            if method == "tools.list":
                # Return a list of tools
                tools_payload = {
                    "jsonrpc" : "2.0",
                    "id" : msg_id,
                    "result" : {
                        "tools" : [
                            {
                                "name" : "list_channels",
                                "description" : "List slack channels for the connected user's workspace",
                                "inputSchema" : {
                                    "type" : "object",
                                    "properties" :{
                                    "query" : {"typer":"string"},
                                    "limit" : {"type":"number"},
                                    "include_private" : {"type":"boolean"}
                                },
                            },
                            },
                            {
                                "name" : "send_message",
                                "description" : "send a message to a slack channel",
                                "inputSchema" : {
                                    "type" : "object",
                                    "properties" : {
                                        "channel_id" : {"type":"string"},
                                        "text" : {"type":"string"},
                                        "thread_ts" : {"type":"string"}, 
                                        "reply_broadcast" : {"type":"boolean"}
                                    },
                                    "required" : ["channel_id", "text"],
                                },
                            },
                        ]
                    },
                }
                await websocket.send_json(tools_payload)
            else:
                
                error_payload = {
                    "jsonrpc" : "2.0",
                    "id" : msg_id,
                    "error" : {
                        "code" : -32603,
                        "message" : f"Method {method} not implemented yet",
                    },
                }
                await websocket.send_json(error_payload)
                
            
            
    except WebSocketDisconnect:
        print(f"[WebSocket] User {user_id} disconnected")
        
    finally:
        # Remove active connections
        active_connections.pop(websocket, None)

    