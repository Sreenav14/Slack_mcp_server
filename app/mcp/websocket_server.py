from typing import Optional, Any, Dict, List, AsyncGenerator
from fastapi import WebSocket, WebSocketDisconnect, APIRouter

from app.auth import get_user_id_from_session_token
from app.db import SessionLocal
from app.models import SlackConnection
from app.slack.client import SlackClient

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
            
            elif method == "tools.call":
                tool_name = params.get("name")
                args = params.get("arguments") or {}
                
                # 1. Handle list_channels tool
                if tool_name == "list_channels":
                    
                    # create db session
                    db = SessionLocal()
                    
                    # look up slack connection for this user
                    conn = db.query(SlackConnection).filter(SlackConnection.user_id==user_id).first()
                    
                    if not conn:
                        await websocket.send_json({
                            "jsonrpc" : "2.0",
                            "id" : msg_id,
                            "error" : {
                                "code" : -32000,
                                "message" : "No slack connection found for this user",
                            },
                        })
                        continue
                    
                    client = SlackClient(conn.bot_access_token)
                    
                    # Read arguments
                    limit = args.get("limit", 20)
                    include_private = args.get("include_private", False)
                    
                    # Slack API Call
                    slack_response = client.list_channels(
                        limit=limit,
                        include_private = include_private
                    )
                    
                    channels = slack_response.get("channels", [])
                    next_cursor = slack_response.get("response_metadata", {}).get("next_cursor")
                    
                    # Transform results
                    transformed = {
                        "channels" :[
                            {
                                "id" : ch.get("id"),
                                "name" : ch.get("name"),
                                "is_private" : ch.get("is_private", False),
                                "members_count" : ch.get("num_members", None)
                            }
                            for ch in channels
                        ],
                        "next_cursor" : next_cursor,
                    }
                    # Send Response
                    
                    await websocket.send_json(
                        {
                            "jsonrpc" : "2.0",
                            "id" : msg_id,
                            "result" : transformed,
                        }
                    )
            
                elif tool_name == "send_message":
                    
                    # Read and validate arguments
                    
                    channel_id = args.get("channel_id")
                    text = args.get("text")
                    thread_ts = args.get("thread_ts")
                    reply_broadcast = args.get("reply_broadcast")
                    
                    # Open database session
                    db = SessionLocal()
                    try:
                        conn = (db.query(SlackConnection).filter(SlackConnection.user_id==user_id).first())
                        
                        if not conn:
                            await websocket.send_json({
                                "jsonrpc" : "2.0",
                                "id" : msg_id,
                                "error" : {
                                    "code" : -32000,
                                    "message" : "No slack connection found for this user",
                                }
                            })
                            continue
                        
                        # 3. Build Slack Cilent
                        client = SlackClient(conn.bot_access_token)
                        
                        # 4. call slack chat.postMessage via our client
                        try:
                            slack_resp = client.send_message(
                                channel_id = channel_id,
                                text = text,
                                thread_ts = thread_ts,
                                reply_broadcast = reply_broadcast,
                            )
                        except Exception as e:
                            await websocket.send_json({
                                "jsonrpc" : "2.0",
                                "id" : msg_id,
                                "error" : {
                                    "code" : -32000,
                                    "message" : f"Error sending message: {str(e)}",
                                }
                            })
                            continue
                        
                        # extract useful fields from slack response
                        
                        channel_out = slack_resp.get("channel")
                        message_ts = slack_resp.get("ts")
                        
                        
                        # thread_ts can be in two places depending on context
                        thread_ts_out = None
                        if "message" in slack_resp and isinstance(slack_resp["message"], dict):
                            thread_ts_out = slack_resp["message"].get("thread_ts")
                        if not thread_ts_out: 
                            thread_ts_out = slack_resp.get(thread_ts)
                            
                        result_payload = {
                            "ok" : True,
                            "channel" : channel_out,
                            "message_ts" : message_ts,
                            "thread_ts" : thread_ts_out,
                        }
                        
                        await websocket.send_json({
                            "jsonrpc" : "2.0",
                            "id" : msg_id,
                            "result" : result_payload,
                        })
                        
                    finally:
                        db.close()
            
            else:
                
                error_payload = {
                    "jsonrpc" : "2.0",
                    "id" : msg_id,
                    "error" : {
                        "code" : -32603,
                        "message" : f"Method {method} not implemented ",
                    },
                }
                await websocket.send_json(error_payload)
                
            
            
    except WebSocketDisconnect:
        print(f"[WebSocket] User {user_id} disconnected")
        
    finally:
        # Remove active connections
        active_connections.pop(websocket, None)

    