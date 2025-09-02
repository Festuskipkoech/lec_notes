from typing import Optional, Dict, Any, List
from sqlalchemy import desc
from sqlalchemy.orm import Session
from app.models.generation import GenerationSession, GenerationStatus
from app.services.conversation_service import conversation_service
from app.models.notes import Topic,Subtopic
from app.langgraph.workflow import notes_workflow
from app.langgraph.state import GenerationState
from app.utils.azure_openai import azure_client
import uuid
import logging
logger = logging.getLogger(__name__)

class GenerationService:
    
    @staticmethod
    def get_previous_subtopics_content(db: Session, topic_id: int, current_index: int) -> List[str]:
        """Get content from previous subtopics for coherence"""
        if current_index == 0:
            return []
        
        # Get published subtopics before current index
        previous_subtopics = db.query(Subtopic).filter(
            Subtopic.topic_id == topic_id,
            Subtopic.order <= current_index,  # Include current and before
            Subtopic.is_published == True
        ).order_by(Subtopic.order).all()
        
        # Return content from most recent ones (limit to avoid token issues)
        contents = [subtopic.content for subtopic in previous_subtopics[-3:] if subtopic.content]
        return contents
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
        """Begin actual content generation with coherence tracking"""
        session = db.query(GenerationSession).filter(GenerationSession.id == session_id).first()
        if not session:
            raise ValueError("Generation session not found")
        
        topic = db.query(Topic).filter(Topic.id == session.topic_id).first()
        
        # Get previous content (empty for first subtopic)
        previous_contents = GenerationService.get_previous_subtopics_content(
            db, topic.id, 0
        )
        
        # Get upcoming concepts from next 2 subtopics
        upcoming_concepts = session.subtopic_titles[1:3] if len(session.subtopic_titles) > 1 else []
        
        # Initialize workflow state with enhanced context
        state = GenerationState(
            session_id=session.id,
            topic_id=topic.id,
            topic_title=topic.title,
            topic_description=topic.description,
            level=topic.level,
            subtopic_titles=session.subtopic_titles,
            current_subtopic_index=0,
            total_subtopics=session.total_subtopics,
            action="generate",
            previous_subtopics_content=previous_contents,  # ADD this
            upcoming_concepts=upcoming_concepts  # ADD this
        )
        
        try:
            result = await notes_workflow.run_workflow(state, session.thread_id)
        except Exception as workflow_error:
            logger.error(f"Workflow error: {workflow_error}")
            raise Exception(f"Workflow execution failed: {str(workflow_error)}")
        
        # Update session status
        session.status = GenerationStatus.generating
        session.current_subtopic = 1
        db.commit()
        
        return {
            "content": result.current_content,
            "subtopic_title": result.subtopic_titles[0] if result.subtopic_titles else "Unknown",
            "current_subtopic": 1,
            "total_subtopics": result.total_subtopics,
            "error": result.error_message
        }



    @staticmethod
    async def generate_next_subtopic(db: Session, session_id: int) -> Dict[str, Any]:
        """Generate next subtopic with previous content context"""
        session = db.query(GenerationSession).filter(GenerationSession.id == session_id).first()
        if not session:
            raise ValueError("Generation session not found")
        
        topic = db.query(Topic).filter(Topic.id == session.topic_id).first()
        current_index = session.current_subtopic - 1  # 0-based
        next_index = current_index + 1
        
        if next_index >= session.total_subtopics:
            raise ValueError("All subtopics have been generated")
        
        # Get previous subtopics content for coherence
        previous_contents = GenerationService.get_previous_subtopics_content(
            db, topic.id, next_index
        )
        
        # Get upcoming concepts
        upcoming_concepts = session.subtopic_titles[next_index + 1:next_index + 3] if next_index < len(session.subtopic_titles) - 1 else []
        
        # Create state with enhanced context
        state = GenerationState(
            session_id=session.id,
            topic_id=topic.id,
            topic_title=topic.title,
            topic_description=topic.description,
            level=topic.level,
            subtopic_titles=session.subtopic_titles,
            current_subtopic_index=next_index,
            total_subtopics=session.total_subtopics,
            action="next",
            previous_subtopics_content=previous_contents,  # ADD this
            upcoming_concepts=upcoming_concepts  # ADD this
        )
        
        try:
            result = await notes_workflow.run_workflow(state, session.thread_id)
            
            # Update session
            session.current_subtopic = result.current_subtopic_index + 1
            db.commit()
            
            return {
                "content": result.current_content,
                "subtopic_title": result.subtopic_titles[result.current_subtopic_index] if result.subtopic_titles else "Unknown",
                "current_subtopic": result.current_subtopic_index + 1,
                "total_subtopics": result.total_subtopics,
                "error": result.error_message
            }
            
        except Exception as e:
            logger.error(f"Error in generate_next_subtopic: {e}")
            raise Exception(f"Failed to generate next subtopic: {str(e)}")
  
    @staticmethod
    async def edit_subtopic(
        db: Session, 
        session_id: int, 
        title: str, 
        content: str
    ) -> Dict[str, Any]:
        """Edit current subtopic while maintaining coherence"""
        session = db.query(GenerationSession).filter(GenerationSession.id == session_id).first()
        if not session:
            raise ValueError("Generation session not found")
        
        topic = db.query(Topic).filter(Topic.id == session.topic_id).first()
        current_index = session.current_subtopic - 1
        
        # Get previous content for context validation
        previous_contents = GenerationService.get_previous_subtopics_content(
            db, topic.id, current_index
        )
        
        state = GenerationState(
            session_id=session.id,
            topic_id=topic.id,
            topic_title=topic.title,
            topic_description=topic.description,
            level=topic.level,
            subtopic_titles=session.subtopic_titles,
            current_subtopic_index=current_index,
            total_subtopics=session.total_subtopics,
            action="edit",
            edit_data={"title": title, "content": content},
            previous_subtopics_content=previous_contents  # ADD this
        )
        
        result = await notes_workflow.run_workflow(state, session.thread_id)
        
        return {
            "content": result.current_content,
            "subtopic_title": result.subtopic_titles[result.current_subtopic_index] if result.subtopic_titles else "Unknown",
            "error": result.error_message
        }

    @staticmethod
    async def consult_ai(
        db: Session, 
        session_id: int, 
        improvement_request: str
    ) -> Dict[str, Any]:
        """Get AI suggestions within conversation context"""
        session = db.query(GenerationSession).filter(GenerationSession.id == session_id).first()
        if not session:
            raise ValueError("Generation session not found")
        
        # Get conversation history
        conversation_history = conversation_service.get_conversation_history(db, session_id)
        
        try:
            suggestions = await azure_client.consult_in_conversation(
                conversation_history, 
                improvement_request
            )
            
            # Store the consultation exchange in conversation
            user_message = f"Consultation request: {improvement_request}"
            conversation_service.add_message(db, session_id, "user", user_message)
            
            assistant_message = f"Consultation response: {suggestions}"
            conversation_service.add_message(db, session_id, "assistant", str(assistant_message))
            
            return {
                "suggestions": suggestions,
                "error": None
            }
            
        except Exception as e:
            logger.error(f"Error in consult_ai: {e}")
            raise Exception(f"Failed to consult AI: {str(e)}")
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