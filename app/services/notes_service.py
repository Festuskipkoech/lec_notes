from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.models.notes import Topic, Subtopic
from app.models.user import User, UserRole
from app.models.generation import GenerationSession
from app.schemas.notes import TopicResponse, TopicListResponse, SubtopicResponse

class NotesService:
    
    @staticmethod
    def get_topics_for_user(db: Session, user: User) -> List[TopicListResponse]:
        """Get topics based on user role"""
        if user.role == UserRole.admin:
            # Admins see all topics
            topics = db.query(Topic).order_by(desc(Topic.created_at)).all()
        else:
            # Students only see topics with published content
            topics = db.query(Topic).filter(
                Topic.subtopics.any(Subtopic.is_published == True)
            ).order_by(desc(Topic.created_at)).all()
        
        result = []
        for topic in topics:
            published_count = db.query(Subtopic).filter(
                Subtopic.topic_id == topic.id,
                Subtopic.is_published == True
            ).count()
            
            result.append(TopicListResponse(
                id=topic.id,
                title=topic.title,
                level=topic.level,
                total_subtopics=topic.total_subtopics,
                published_subtopics=published_count,
                created_at=topic.created_at
            ))
        
        return result
    
    @staticmethod
    def get_topic_details(db: Session, topic_id: int, user: User) -> Optional[TopicResponse]:
        """Get detailed topic with subtopics"""
        topic = db.query(Topic).filter(Topic.id == topic_id).first()
        if not topic:
            return None
        
        if user.role == UserRole.admin:
            # Admins see all subtopics
            subtopics = db.query(Subtopic).filter(
                Subtopic.topic_id == topic_id
            ).order_by(Subtopic.order).all()
        else:
            # Students only see published subtopics
            subtopics = db.query(Subtopic).filter(
                Subtopic.topic_id == topic_id,
                Subtopic.is_published == True
            ).order_by(Subtopic.order).all()
        
        subtopic_responses = [
            SubtopicResponse(
                id=st.id,
                order=st.order,
                title=st.title,
                content=st.content if user.role == UserRole.admin or st.is_published else None,
                is_published=st.is_published,
                published_at=st.published_at
            ) for st in subtopics
        ]
        
        return TopicResponse(
            id=topic.id,
            title=topic.title,
            description=topic.description,
            level=topic.level,
            total_subtopics=topic.total_subtopics,
            subtopics=subtopic_responses,
            created_at=topic.created_at
        )
    
    @staticmethod
    def update_topic(db: Session, topic_id: int, title: str = None, description: str = None) -> bool:
        """Update topic details (admin only)"""
        topic = db.query(Topic).filter(Topic.id == topic_id).first()
        if not topic:
            return False
        
        if title:
            topic.title = title
        if description:
            topic.description = description
        
        db.commit()
        return True
        
    @staticmethod
    def delete_topic(db: Session, topic_id: int) -> bool:
        """Delete topic and all subtopics (admin only)"""
        try:
            # First, delete all generation sessions for this topic
            db.query(GenerationSession).filter(
                GenerationSession.topic_id == topic_id
            ).delete()
            
            # Then delete the topic (subtopics will be deleted by cascade)
            topic = db.query(Topic).filter(Topic.id == topic_id).first()
            if not topic:
                return False
            
            db.delete(topic)
            db.commit()
            return True
        except Exception as e:
            db.rollback()
            raise e

notes_service = NotesService()