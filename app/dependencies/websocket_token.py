from typing import Optional
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.services import auth_service
import logging

logger = logging.getLogger(__name__)

async def get_user_from_websocket_token(token: str) -> Optional[User]:
    """Authenticate user from WebSocket token parameter"""
    try:
        # Verify the JWT token
        payload = auth_service.verify_access_token(token)
        if not payload:
            return None
        
        user_id = payload.get("sub")
        if not user_id:
            return None
        
        # Get user from database
        db: Session = next(get_db())
        try:
            user = db.query(User).filter(User.id == int(user_id)).first()
            return user
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"WebSocket token verification failed: {e}")
        return None