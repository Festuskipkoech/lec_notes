from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from app.models.generation import GenerationSession, GenerationStatus
from app.models.notes import Topic
from app.langgraph.workflow import notes_workflow
from app.langgraph.state import GenerationState
from app.utils.azure_openai import azure_client
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
        
        try:
            result = await notes_workflow.run_workflow(state, session.thread_id)
        except Exception as workflow_error:
            logger.error(f"Workflow error: {workflow_error}")
            raise Exception(f"Workflow execution failed: {str(workflow_error)}")
        
        logger.info(f"Generation result: {result}")        
        
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
        """Generate next subtopic content - FIXED VERSION"""
        session = db.query(GenerationSession).filter(GenerationSession.id == session_id).first()
        if not session:
            raise ValueError("Generation session not found")
        
        # Get current state from workflow
        topic = db.query(Topic).filter(Topic.id == session.topic_id).first()
        
        # FIXED: Single workflow call with "next" action that should handle both 
        # moving to next subtopic AND generating content
        state = GenerationState(
            session_id=session.id,
            topic_id=topic.id,
            topic_title=topic.title,
            topic_description=topic.description,
            level=topic.level,
            subtopic_titles=session.subtopic_titles,
            current_subtopic_index=session.current_subtopic - 1,  # Current index (0-based)
            total_subtopics=session.total_subtopics,
            action="next"  # This should move to next AND generate
        )
        
        try:
            # FIXED: Single call instead of two calls
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
            "subtopic_title": result.subtopic_titles[result.current_subtopic_index] if result.subtopic_titles else "Unknown",
            "error": result.error_message
        }
    

    @staticmethod
    async def consult_ai(
        db: Session, 
        session_id: int, 
        improvement_request: str
    ) -> Dict[str, Any]:
        """Get AI suggestions for current subtopic"""
        print(f"🔍 DEBUG: consult_ai called with session_id={session_id}, request='{improvement_request}'")
        
        session = db.query(GenerationSession).filter(GenerationSession.id == session_id).first()
        if not session:
            print(f"❌ DEBUG: Session {session_id} not found")
            raise ValueError("Generation session not found")
        
        print(f"✅ DEBUG: Session found - current_subtopic={session.current_subtopic}, status={session.status}")
        
        topic = db.query(Topic).filter(Topic.id == session.topic_id).first()
        print(f"✅ DEBUG: Topic found - title='{topic.title}', level='{topic.level}'")
        
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
        
        print(f"🚀 DEBUG: About to run workflow with action='consult'")
        print(f"📝 DEBUG: State details - current_subtopic_index={state.current_subtopic_index}, consult_request='{state.consult_request}'")
        
        result = await notes_workflow.run_workflow(state, session.thread_id)
        
        print(f"🎯 DEBUG: Workflow returned - ai_suggestions type: {type(result.ai_suggestions)}")
        print(f"🎯 DEBUG: ai_suggestions value: {result.ai_suggestions}")
        print(f"🎯 DEBUG: error_message: {result.error_message}")
        
        return {
            "suggestions": result.ai_suggestions,
            "error": result.error_message
        }

    @staticmethod
    async def consult_ai_node(state: GenerationState) -> GenerationState:
        """Get AI suggestions for improvements"""
        try:
            print(f"🤖 DEBUG: [CONSULT] Starting AI consultation")
            print(f"🤖 DEBUG: [CONSULT] Consult request: '{state.consult_request}'")
            print(f"🤖 DEBUG: [CONSULT] Current content exists: {state.current_content is not None}")
            print(f"🤖 DEBUG: [CONSULT] Current content length: {len(state.current_content) if state.current_content else 0}")
            
            updated_state = state.dict()
            
            if state.consult_request and state.current_content:
                print(f"🤖 DEBUG: [CONSULT] Calling azure_client.suggest_improvements")
                
                suggestions = await azure_client.suggest_improvements(
                    content=state.current_content,
                    improvement_request=state.consult_request
                )
                
                print(f"🤖 DEBUG: [CONSULT] Azure client returned: {suggestions}")
                print(f"🤖 DEBUG: [CONSULT] Suggestions type: {type(suggestions)}")
                
                updated_state['ai_suggestions'] = suggestions
                updated_state['error_message'] = None
                print(f"🤖 DEBUG: [CONSULT] AI suggestions set successfully")
            else:
                error_msg = "No consultation request or content provided"
                print(f"❌ DEBUG: [CONSULT] {error_msg}")
                print(f"❌ DEBUG: [CONSULT] consult_request exists: {bool(state.consult_request)}")
                print(f"❌ DEBUG: [CONSULT] current_content exists: {bool(state.current_content)}")
                updated_state['error_message'] = error_msg
            
            # CRITICAL: Clear action to end workflow
            updated_state['action'] = None
            print(f"🤖 DEBUG: [CONSULT] Workflow ending, action set to None")
            return GenerationState(**updated_state)
                
        except Exception as e:
            print(f"💥 DEBUG: [CONSULT] Exception occurred: {str(e)}")
            print(f"💥 DEBUG: [CONSULT] Exception type: {type(e)}")
            import traceback
            print(f"💥 DEBUG: [CONSULT] Traceback: {traceback.format_exc()}")
            
            updated_state = state.dict()
            updated_state['error_message'] = f"AI consultation failed: {str(e)}"
            updated_state['action'] = None
            return GenerationState(**updated_state)
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