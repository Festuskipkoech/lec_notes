from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.websocket.manager import websocket_manager
from app.dependencies.websocket_token import get_user_from_websocket_token
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix = "/ws", tags=["websocket"])

@router.websocket("/notifications")
async def websocket_notifications(
    websocket: WebSocket,
    token: str,
):
    # websocket endpoint for real-time notifications
    user = await get_user_from_websocket_token(token)
    if not user:
        await websocket.close(code =4001, reason="Invalid token")
        return

    await websocket_manager.connect(websocket, user.id)
    
    try:
        while True:
            data = await websocket.receive_text()
            
            if data == 'ping':
                await websocket.send_text('pong')
    except WebSocketDisconnect:
        websocket_manager.disconnect(user.id)
        logger.info(f"Websocket disconnected for user id: {user.id}")
    except Exception as e:
        logger.error(f"websocket error for user {user.id}: {str(e)}")
        websocket_manager.disconnect(user.id)