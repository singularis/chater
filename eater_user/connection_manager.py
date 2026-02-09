import json

from fastapi import WebSocket
from starlette.websockets import WebSocketState


async def safe_send_websocket_message(websocket: WebSocket, message: dict) -> bool:
    try:
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.send_text(json.dumps(message))
            return True
        return False
    except Exception:
        return False


class ConnectionManager:
    def __init__(self):
        self.active_connections = []
        self.user_connections = {}

    async def connect(self, websocket: WebSocket, user_email: str):
        self.active_connections.append(websocket)
        self.user_connections[user_email] = websocket

    def disconnect(self, websocket: WebSocket, user_email: str):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        if user_email in self.user_connections:
            del self.user_connections[user_email]


manager = ConnectionManager()

