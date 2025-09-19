from datetime import datetime, timezone
from app.websocket.manager import websocket_manager
import logging

logger = logging.getLogger(__name__)

class NotificationService:
    
    @staticmethod
    async def notify_new_assignment(assignment_title: str):
        """Notify all students about new assignment"""
        message = {
            "type": "new_assignment",
            "title": "New Assignment Available",
            "message": f"Assignment '{assignment_title}' has been published",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await websocket_manager.broadcast_to_all_students(message)
    
    @staticmethod
    async def notify_grade_available(user_id: int, assignment_title: str):
        """Notify specific student about graded assignment"""
        message = {
            "type": "grade_available", 
            "title": "Assignment Graded",
            "message": f"Your assignment '{assignment_title}' has been graded",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await websocket_manager.send_to_user(user_id, message)
    
    @staticmethod
    async def notify_new_content(topic_title: str, subtopic_title: str):
        """Notify all students about new published content"""
        message = {
            "type": "new_content",
            "title": "New Content Available", 
            "message": f"New content '{subtopic_title}' published in {topic_title}",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await websocket_manager.broadcast_to_all_students(message)
    
    @staticmethod
    async def notify_topic_updated(topic_title: str):
        """Notify all students about topic updates"""
        message = {
            "type": "topic_updated",
            "title": "Topic Updated",
            "message": f"Topic '{topic_title}' has been updated",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await websocket_manager.broadcast_to_all_students(message)

# Service instance
notification_service = NotificationService()