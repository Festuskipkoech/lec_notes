from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.dependencies.dependencies import get_current_user
from app.schemas.notes import TopicResponse, TopicListResponse
from app.services.notes_service import notes_service
from app.websocket.notifications import notification_service
from app.models.user import User

router = APIRouter(prefix="/notes", tags=["notes"])

@router.get("", response_model=List[TopicListResponse])
async def get_notes_list(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get list of available notes based on user role"""
    return notes_service.get_topics_for_user(db, current_user)

@router.get("/{topic_id}", response_model=TopicResponse)
async def get_topic_details(
    topic_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get detailed topic with subtopics"""
    topic = notes_service.get_topic_details(db, topic_id, current_user)
    
    if not topic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Topic not found"
        )
    
    return topic

# Admin-only endpoints
@router.put("/admin/{topic_id}")
async def update_topic(
    topic_id: int,
    title: str = None,
    description: str = None,
    db: Session = Depends(get_db)
):
    """Update topic metadata (admin only)"""
    success = notes_service.update_topic(db, topic_id, title, description)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Topic not found"
        )
    
    # Get updated topic title for notification
    from app.models.notes import Topic
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if topic:
        await notification_service.notify_topic_updated(topic.title)
    
    return {"message": "Topic updated successfully"}


@router.delete("/admin/{topic_id}")
async def delete_topic(
    topic_id: int,
    db: Session = Depends(get_db)
):
    """Delete topic and all subtopics (admin only)"""
    success = notes_service.delete_topic(db, topic_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Topic not found"
        )
    
    return {"message": "Topic deleted successfully"}
