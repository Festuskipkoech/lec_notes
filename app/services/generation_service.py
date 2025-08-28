from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from app.models.generation import GenerationSession, GenerationStatus
from app.models.notes import Topic
from app.langgraph.workflow import notes_workflow
from app.langgraph.state import GenerationState
from app.utils.azure_openai import azure_client
import uuid

class GenerationService:
    
    @staticmethod
    async def start_generation(
        db: Session, 
        topic_description: str, 
        level: str, 
        num_subtopics: Optional[int],
        creator_id: int
    ) -> Dict[str, Any]:
        """Start a new generation session"""
        
        # Generate subtopic plan
        subtopics = await azure_client.generate_subtopic_plan(
            topic_description, level, num_subtopics
        )
        
        # Create topic record
        topic = Topic(
            title=topic_description[:100],  # Truncate for title
            description=topic_description,
            level=level,
            total_subtopics=len(subtopics),
            creator_id=creator_id
        )
        db.add(topic)
        db.commit()
        db.refresh(topic)
        
        # Create generation session
        thread_id = f"gen_{topic.id}_{uuid.uuid4().hex[:8]}"
        session = GenerationSession(
            topic_id=topic.id,
            thread_id=thread_id,
            total_subtopics=len(subtopics),
            subtopic_titles=subtopics,
            status=GenerationStatus.planning
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        
        return {
            "session_id": session.id,
            "topic_id": topic.id,
            "subtopic_titles": subtopics,
            "total_subtopics": len(subtopics)
        }
    
    @staticmethod
    async def begin_generation(db: Session, session_id: int) -> Dict[str, Any]:
        """Begin actual content generation"""
        session = db.query(GenerationSession).filter(GenerationSession.id == session_id).first()
        if not session:
            raise ValueError("Generation session not found")
        
        topic = db.query(Topic).filter(Topic.id == session.topic_id).first()
        
        # Initialize workflow state
        state = GenerationState(
            session_id=session.id,
            topic_id=topic.id,
            topic_title=topic.title,
            topic_description=topic.description,
            level=topic.level,
            subtopic_titles=session.subtopic_titles,
            current_subtopic_index=0,
            total_subtopics=session.total_subtopics,
            action="generate"
        )
        
        # Run workflow
        result = await notes_workflow.run_workflow(state, session.thread_id)
        
        # Update session status
        session.status = GenerationStatus.generating
        session.current_subtopic = 1
        db.commit()
        
        return {
            "content": result.current_content,
            "subtopic_title": result.subtopic_titles[0],
            "current_subtopic": 1,
            "total_subtopics": result.total_subtopics,
            "error": result.error_message
        }
    
    @staticmethod
    async def generate_next_subtopic(db: Session, session_id: int) -> Dict[str, Any]:
        """Generate next subtopic content"""
        session = db.query(GenerationSession).filter(GenerationSession.id == session_id).first()
        if not session:
            raise ValueError("Generation session not found")
        
        # Get current state from workflow
        topic = db.query(Topic).filter(Topic.id == session.topic_id).first()
        
        state = GenerationState(
            session_id=session.id,
            topic_id=topic.id,
            topic_title=topic.title,
            topic_description=topic.description,
            level=topic.level,
            subtopic_titles=session.subtopic_titles,
            current_subtopic_index=session.current_subtopic,
            total_subtopics=session.total_subtopics,
            action="next"
        )
        
        # Move to next and generate
        result = await notes_workflow.run_workflow(state, session.thread_id)
        result.action = "generate"
        result = await notes_workflow.run_workflow(result, session.thread_id)
        
        # Update session
        session.current_subtopic = result.current_subtopic_index + 1
        db.commit()
        
        return {
            "content": result.current_content,
            "subtopic_title": result.subtopic_titles[result.current_subtopic_index],
            "current_subtopic": result.current_subtopic_index + 1,
            "total_subtopics": result.total_subtopics,
            "error": result.error_message
        }
    
    @staticmethod
    async def edit_subtopic(
        db: Session, 
        session_id: int, 
        title: str, 
        content: str
    ) -> Dict[str, Any]:
        """Edit current subtopic"""
        session = db.query(GenerationSession).filter(GenerationSession.id == session_id).first()
        if not session:
            raise ValueError("Generation session not found")
        
        topic = db.query(Topic).filter(Topic.id == session.topic_id).first()
        
        state = GenerationState(
            session_id=session.id,
            topic_id=topic.id,
            topic_title=topic.title,
            topic_description=topic.description,
            level=topic.level,
            subtopic_titles=session.subtopic_titles,
            current_subtopic_index=session.current_subtopic - 1,
            total_subtopics=session.total_subtopics,
            action="edit",
            edit_data={"title": title, "content": content}
        )
        
        result = await notes_workflow.run_workflow(state, session.thread_id)
        
        return {
            "content": result.current_content,
            "subtopic_title": result.subtopic_titles[result.current_subtopic_index],
            "error": result.error_message
        }
    
    @staticmethod
    async def consult_ai(
        db: Session, 
        session_id: int, 
        improvement_request: str
    ) -> Dict[str, Any]:
        """Get AI suggestions for current subtopic"""
        session = db.query(GenerationSession).filter(GenerationSession.id == session_id).first()
        if not session:
            raise ValueError("Generation session not found")
        
        topic = db.query(Topic).filter(Topic.id == session.topic_id).first()
        
        state = GenerationState(
            session_id=session.id,
            topic_id=topic.id,
            topic_title=topic.title,
            topic_description=topic.description,
            level=topic.level,
            subtopic_titles=session.subtopic_titles,
            current_subtopic_index=session.current_subtopic - 1,
            total_subtopics=session.total_subtopics,
            action="consult",
            consult_request=improvement_request
        )
        
        result = await notes_workflow.run_workflow(state, session.thread_id)
        
        return {
            "suggestions": result.ai_suggestions,
            "error": result.error_message
        }
    
    @staticmethod
    async def publish_subtopic(db: Session, session_id: int) -> Dict[str, Any]:
        """Publish current subtopic"""
        session = db.query(GenerationSession).filter(GenerationSession.id == session_id).first()
        if not session:
            raise ValueError("Generation session not found")
        
        topic = db.query(Topic).filter(Topic.id == session.topic_id).first()
        
        state = GenerationState(
            session_id=session.id,
            topic_id=topic.id,
            topic_title=topic.title,
            topic_description=topic.description,
            level=topic.level,
            subtopic_titles=session.subtopic_titles,
            current_subtopic_index=session.current_subtopic - 1,
            total_subtopics=session.total_subtopics,
            action="publish"
        )
        
        result = await notes_workflow.run_workflow(state, session.thread_id)
        
        # Check if this was the last subtopic
        if session.current_subtopic >= session.total_subtopics:
            session.status = GenerationStatus.completed
        
        db.commit()
        
        return {
            "published": True,
            "current_subtopic": session.current_subtopic,
            "total_subtopics": session.total_subtopics,
            "completed": session.current_subtopic >= session.total_subtopics,
            "error": result.error_message
        }

generation_service = GenerationService()