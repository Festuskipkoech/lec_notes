from typing import Optional, Dict, Any, List
from sqlalchemy import desc
from sqlalchemy.orm import Session
from app.models.generation import GenerationSession, GenerationStatus
from app.models.notes import Topic, Subtopic
from app.langgraph.workflow import notes_workflow
from app.langgraph.state import GenerationState
from app.utils.azure_openai import azure_client
from app.services.vector_service import vector_service
import uuid
import logging

logger = logging.getLogger(__name__)

class GenerationService:
    
    @staticmethod
    async def start_generation(
        db: Session, 
        topic_description: str, 
        level: str, 
        num_subtopics: Optional[int],
        creator_id: int
    ) -> Dict[str, Any]:
        """Start a new generation session with vector-enhanced architecture"""
        
        # Generate subtopic plan using Azure OpenAI
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
        
        logger.info(f"[START] Created topic {topic.id} with {len(subtopics)} planned subtopics")
        
        return {
            "session_id": session.id,
            "topic_id": topic.id,
            "subtopic_titles": subtopics,
            "total_subtopics": len(subtopics)
        }

    @staticmethod
    async def begin_generation(db: Session, session_id: int) -> Dict[str, Any]:
        """Begin content generation with vector-enhanced workflow"""
        session = db.query(GenerationSession).filter(GenerationSession.id == session_id).first()
        if not session:
            raise ValueError("Generation session not found")
        
        topic = db.query(Topic).filter(Topic.id == session.topic_id).first()
        
        # Initialize simplified workflow state
        state = GenerationState(
            session_id=session.id,
            topic_id=topic.id,
            topic_title=topic.title,
            level=topic.level,
            subtopic_titles=session.subtopic_titles,
            current_subtopic_index=0,
            total_subtopics=session.total_subtopics,
            action="generate"
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
        
        # Get generated content from database
        generated_subtopic = db.query(Subtopic).filter(
            Subtopic.topic_id == topic.id,
            Subtopic.order == 1
        ).first()
        
        logger.info(f"[BEGIN] First subtopic generated for session {session_id}")
        
        return {
            "content": generated_subtopic.content if generated_subtopic else "Content generation in progress...",
            "subtopic_title": session.subtopic_titles[0] if session.subtopic_titles else "Unknown",
            "current_subtopic": 1,
            "total_subtopics": result.total_subtopics,
            "error": result.error_message
        }

    @staticmethod
    async def generate_next_subtopic(db: Session, session_id: int) -> Dict[str, Any]:
        """Generate next subtopic with vector-enhanced context"""
        session = db.query(GenerationSession).filter(GenerationSession.id == session_id).first()
        if not session:
            raise ValueError("Generation session not found")
        
        topic = db.query(Topic).filter(Topic.id == session.topic_id).first()
        current_index = session.current_subtopic - 1  # Convert to 0-based
        next_index = current_index + 1
        
        logger.info(f"[NEXT] Session {session_id}: current_subtopic={session.current_subtopic}, moving from index {current_index} to {next_index}")
        
        if next_index >= session.total_subtopics:
            raise ValueError("All subtopics have been generated")
        
        # Create state for next subtopic with proper topic info
        state = GenerationState(
            session_id=session.id,
            topic_id=session.topic_id,
            topic_title=topic.title,
            level=topic.level,
            subtopic_titles=session.subtopic_titles,
            current_subtopic_index=next_index,
            total_subtopics=session.total_subtopics,
            action="next"
        )
        
        try:
            result = await notes_workflow.run_workflow(state, session.thread_id)
            
            # Update session
            session.current_subtopic = result.current_subtopic_index + 1
            db.commit()
            
            # Get generated content from database
            generated_subtopic = db.query(Subtopic).filter(
                Subtopic.topic_id == session.topic_id,
                Subtopic.order == result.current_subtopic_index + 1
            ).first()
            
            logger.info(f"[NEXT] Generated subtopic {result.current_subtopic_index + 1} for session {session_id}")
            
            return {
                "content": generated_subtopic.content if generated_subtopic else "Content generation in progress...",
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
        """Edit current subtopic with vector re-embedding"""
        session = db.query(GenerationSession).filter(GenerationSession.id == session_id).first()
        if not session:
            raise ValueError("Generation session not found")
        
        topic = db.query(Topic).filter(Topic.id == session.topic_id).first()
        current_index = session.current_subtopic - 1
        
        state = GenerationState(
            session_id=session.id,
            topic_id=session.topic_id,
            topic_title=topic.title,
            level=topic.level,
            subtopic_titles=session.subtopic_titles,
            current_subtopic_index=current_index,
            total_subtopics=session.total_subtopics,
            action="edit",
            edit_data={"title": title, "content": content}
        )
        
        result = await notes_workflow.run_workflow(state, session.thread_id)
        
        # Get updated content from database
        updated_subtopic = db.query(Subtopic).filter(
            Subtopic.topic_id == session.topic_id,
            Subtopic.order == current_index + 1
        ).first()
        
        logger.info(f"[EDIT] Subtopic {current_index + 1} edited and re-embedded for session {session_id}")
        
        return {
            "content": updated_subtopic.content if updated_subtopic else content,
            "subtopic_title": updated_subtopic.title if updated_subtopic else title,
            "error": result.error_message
        }

    @staticmethod
    async def consult_ai(
        db: Session, 
        session_id: int, 
        improvement_request: str
    ) -> Dict[str, Any]:
        """Get AI suggestions for current subtopic content"""
        session = db.query(GenerationSession).filter(GenerationSession.id == session_id).first()
        if not session:
            raise ValueError("Generation session not found")
        
        # Get current subtopic content from database
        current_subtopic = db.query(Subtopic).filter(
            Subtopic.topic_id == session.topic_id,
            Subtopic.order == session.current_subtopic
        ).first()
        
        if not current_subtopic:
            raise ValueError("No current subtopic content found")
        
        try:
            # Build conversation context with current content
            conversation_history = [
                {"role": "assistant", "content": current_subtopic.content}
            ]
            
            suggestions = await azure_client.consult_in_conversation(
                conversation_history, 
                improvement_request
            )
            
            logger.info(f"[CONSULT] AI consultation completed for session {session_id}")
            
            return {
                "suggestions": suggestions,
                "error": None
            }
            
        except Exception as e:
            logger.error(f"Error in consult_ai: {e}")
            return {
                "suggestions": None,
                "error": f"Failed to consult AI: {str(e)}"
            }
    
    @staticmethod
    async def publish_subtopic(db: Session, session_id: int) -> Dict[str, Any]:
        """Publish current subtopic using vector-enhanced workflow"""
        session = db.query(GenerationSession).filter(GenerationSession.id == session_id).first()
        if not session:
            raise ValueError("Generation session not found")
        
        topic = db.query(Topic).filter(Topic.id == session.topic_id).first()
        
        state = GenerationState(
            session_id=session.id,
            topic_id=session.topic_id,
            topic_title=topic.title,
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
        
        logger.info(f"[PUBLISH] Subtopic {session.current_subtopic} published for session {session_id}")
        
        return {
            "published": True,
            "current_subtopic": session.current_subtopic,
            "total_subtopics": session.total_subtopics,
            "completed": session.current_subtopic >= session.total_subtopics,
            "error": result.error_message
        }

    @staticmethod
    async def get_content_analytics(db: Session, topic_id: int) -> Dict[str, Any]:
        """Get analytics about content quality and vector coverage"""
        try:
            # Get concept coverage analysis using vector service
            coverage = await vector_service.get_concept_coverage_analysis(db, topic_id)
            
            # Get subtopic completion status
            subtopics = db.query(Subtopic).filter(Subtopic.topic_id == topic_id).all()
            
            total_subtopics = len(subtopics)
            published_subtopics = len([s for s in subtopics if s.is_published])
            draft_subtopics = len([s for s in subtopics if s.content and not s.is_published])
            
            # Calculate average content length
            content_lengths = [len(s.content) for s in subtopics if s.content]
            avg_content_length = sum(content_lengths) / len(content_lengths) if content_lengths else 0
            
            logger.info(f"[ANALYTICS] Generated analytics for topic {topic_id}")
            
            return {
                "subtopic_stats": {
                    "total": total_subtopics,
                    "published": published_subtopics,
                    "drafted": draft_subtopics,
                    "completion_rate": published_subtopics / total_subtopics if total_subtopics > 0 else 0,
                    "avg_content_length": round(avg_content_length)
                },
                "concept_coverage": coverage,
                "quality_metrics": {
                    "content_balance": coverage.get('balance_score', 0),
                    "total_concepts": coverage.get('total_chunks', 0),
                    "concept_types": len(coverage.get('coverage_by_type', {})),
                    "vector_density": coverage.get('total_chunks', 0) / total_subtopics if total_subtopics > 0 else 0
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting content analytics: {e}")
            return {
                "error": f"Failed to get analytics: {str(e)}"
            }

    @staticmethod
    async def get_session_content(db: Session, session_id: int) -> Dict[str, Any]:
        """Get all content for a session with vector context information"""
        session = db.query(GenerationSession).filter(GenerationSession.id == session_id).first()
        if not session:
            raise ValueError("Generation session not found")
        
        # Get all subtopics for this session
        subtopics = db.query(Subtopic).filter(
            Subtopic.topic_id == session.topic_id
        ).order_by(Subtopic.order).all()
        
        # Build response with content and vector info
        subtopic_data = []
        for subtopic in subtopics:
            # Get chunk count for this subtopic
            chunk_count = db.query(ContentChunk).filter(
                ContentChunk.subtopic_id == subtopic.id
            ).count() if hasattr(subtopic, 'content_chunks') else 0
            
            subtopic_data.append({
                "order": subtopic.order,
                "title": subtopic.title,
                "content": subtopic.content,
                "is_published": subtopic.is_published,
                "published_at": subtopic.published_at,
                "chunk_count": chunk_count,
                "content_length": len(subtopic.content) if subtopic.content else 0
            })
        
        return {
            "session_id": session_id,
            "topic_id": session.topic_id,
            "current_subtopic": session.current_subtopic,
            "total_subtopics": session.total_subtopics,
            "status": session.status,
            "subtopics": subtopic_data
        }

generation_service = GenerationService()