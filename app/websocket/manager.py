from typing import Dict
from fastapi import WebSocket
import json
import logging

logger = logging.getLogger(__name__)

class WebSocketManager:
    def __init__(self):
        # store active connections: user_id -> websocket
        self.active_connections: Dict[int, WebSocket] = {}
        
    async def connect(self, websocket: WebSocket, user_id: int):
        # Accept WebSocket connection and store using mapping
        await websocket.accept()
        self.active_connections[user_id] = websocket
        logger.info(f"Websocket connected for {user_id}")
    
    async def disconnect(self, user_id: int):
        # Remove user connections
        if user_id in self.active_connections:
            del self.active_connections[user_id]
            logger.info(f"Websocket disconnected for user {user_id}")
            
    async def send_to_user(self, user_id: int, message: dict):
        # Send message to specific user
        if user_id in self.active_connections:
            try:
                await  self.active_connections[user_id].send_text(json.dumps(message))
                logger.info(f"Message sent to user: {user_id}, {message} ")
            except Exception as e:
                logger.error(f"Failed to send message to user: {user_id}, error: {str(e)}")
                self.disconnect(user_id)
    
    async def broadcast_to_all_students(self, message: dict):
        # Send message to all connected students
        disconnected_users= []
        
        for user_id, websocket in self.active_connections.items():
            try:
                await websocket.send_text(json.dumps(message))
            except Exception as e:
                logger.error(f"failed to broadcast messages {str(e)}")
            disconnected_users.append(user_id)
        
        for user_id in disconnected_users:
            self.disconnect(user_id)
        logger.info (f"Broadcast sent to {len(self.active_connections)} users: {message['type']}")
                
websocket_manager = WebSocketManager()