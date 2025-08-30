from app.langgraph.state import GenerationState
from app.utils.azure_openai import azure_client
from app.database import SessionLocal
from app.models.notes import Subtopic
from sqlalchemy.sql import func
import logging
logger = logging.getLogger(__name__)

class GenerationNodes:
    
    @staticmethod
    async def generate_content_node(state: GenerationState) -> GenerationState:
        """Generate content for current subtopic"""
        try:
            logger.info(f"[GENERATE] Starting generation for subtopic: {state.subtopic_titles[state.current_subtopic_index]}")
            current_index = state.current_subtopic_index
            subtopic_title = state.subtopic_titles[current_index]
            
            # Get context from previous subtopics
            previous_concepts = []
            if current_index > 0:
                for i in range(current_index):
                    if i in state.generated_content:
                        # Extract key concepts from previous content (simplified)
                        content_words = state.generated_content[i].split()[:50]  # First 50 words as concepts
                        previous_concepts.extend([word.strip('.,!?') for word in content_words if len(word) > 4])
                previous_concepts = list(set(previous_concepts))[:10]  # Top 10 unique concepts
            
            # Get upcoming concepts
            upcoming_concepts = state.subtopic_titles[current_index + 1:current_index + 3] if current_index < len(state.subtopic_titles) - 1 else []
            
            content = await azure_client.generate_subtopic_content(
                topic_title=state.topic_title,
                subtopic_title=subtopic_title,
                level=state.level,
                previous_concepts=previous_concepts,
                upcoming_concepts=upcoming_concepts
            )
            
            # Create new state instead of modifying existing
            updated_state = state.dict()
            updated_state['current_content'] = content
            updated_state['generated_content'] = state.generated_content.copy()
            updated_state['generated_content'][current_index] = content
            updated_state['error_message'] = None
            
            # CRITICAL: Set action to None to end workflow after generation
            updated_state['action'] = None  # This prevents infinite loops
            
            logger.info(f"[GENERATE] Content generated successfully, action set to None")
            return GenerationState(**updated_state)
            
        except Exception as e:
            logger.error(f"[GENERATE] Content generation failed: {str(e)}")
            updated_state = state.dict()
            updated_state['error_message'] = f"Generation failed: {str(e)}"
            updated_state['action'] = None  # End workflow on error
            return GenerationState(**updated_state)
    
    @staticmethod
    async def edit_content_node(state: GenerationState) -> GenerationState:
        """Handle manual content editing"""
        try:
            logger.info(f"[EDIT] Processing edit request")
            updated_state = state.dict()
            
            if state.edit_data and "content" in state.edit_data:
                current_index = state.current_subtopic_index
                updated_state['current_content'] = state.edit_data["content"]
                
                # Update generated content
                updated_state['generated_content'] = state.generated_content.copy()
                updated_state['generated_content'][current_index] = state.edit_data["content"]
                
                # Update subtopic title if provided
                if "title" in state.edit_data:
                    updated_state['subtopic_titles'] = state.subtopic_titles.copy()
                    updated_state['subtopic_titles'][current_index] = state.edit_data["title"]
                
                updated_state['error_message'] = None
                logger.info(f"[EDIT] Content edited successfully")
            else:
                updated_state['error_message'] = "No edit data provided"
                logger.warning(f"[EDIT] No edit data provided")
            
            # CRITICAL: Clear action to end workflow
            updated_state['action'] = None
            return GenerationState(**updated_state)
                
        except Exception as e:
            logger.error(f"[EDIT] Edit failed: {str(e)}")
            updated_state = state.dict()
            updated_state['error_message'] = f"Edit failed: {str(e)}"
            updated_state['action'] = None
            return GenerationState(**updated_state)
    
    @staticmethod
    async def consult_ai_node(state: GenerationState) -> GenerationState:
        """Get AI suggestions for improvements"""
        try:
            print("🤖 NODE CALLED: consult_ai_node is executing!")

            logger.info(f"[CONSULT] Processing AI consultation request")
            updated_state = state.dict()
            
            if state.consult_request and state.current_content:
                suggestions = await azure_client.suggest_improvements(
                    content=state.current_content,
                    improvement_request=state.consult_request
                )
                updated_state['ai_suggestions'] = suggestions
                updated_state['error_message'] = None
                logger.info(f"[CONSULT] Consultation request: '{state.consult_request}'")
                logger.info(f"[CONSULT] Current content length: {len(state.current_content) if state.current_content else 0}")
            else:
                updated_state['error_message'] = "No consultation request or content provided"
                logger.warning(f"[CONSULT] Missing consultation request or content")
            
            # CRITICAL: Clear action to end workflow
            updated_state['action'] = None
            return GenerationState(**updated_state)
                
        except Exception as e:
            logger.error(f"[CONSULT] AI consultation failed: {str(e)}")
            updated_state = state.dict()
            updated_state['error_message'] = f"AI consultation failed: {str(e)}"
            updated_state['action'] = None
            return GenerationState(**updated_state)
    
    @staticmethod
    async def publish_subtopic_node(state: GenerationState) -> GenerationState:
        """Publish current subtopic to database"""
        try:
            logger.info(f"[PUBLISH] Publishing subtopic {state.current_subtopic_index + 1}")
            db = SessionLocal()
            current_index = state.current_subtopic_index
            
            # Find or create subtopic record
            subtopic = db.query(Subtopic).filter(
                Subtopic.topic_id == state.topic_id,
                Subtopic.order == current_index + 1
            ).first()
            
            if not subtopic:
                subtopic = Subtopic(
                    topic_id=state.topic_id,
                    order=current_index + 1,
                    title=state.subtopic_titles[current_index],
                    content=state.current_content,
                    is_published=True,
                    published_at=func.now()
                )
                db.add(subtopic)
            else:
                subtopic.title = state.subtopic_titles[current_index]
                subtopic.content = state.current_content
                subtopic.is_published = True
                subtopic.published_at = func.now()
            
            db.commit()
            db.close()
            
            # Update state
            updated_state = state.dict()
            updated_state['published_subtopics'] = state.published_subtopics.copy()
            updated_state['published_subtopics'].append(current_index)
            updated_state['error_message'] = None
            
            # CRITICAL: Clear action to end workflow
            updated_state['action'] = None
            logger.info(f"[PUBLISH] Subtopic published successfully")
            return GenerationState(**updated_state)
            
        except Exception as e:
            logger.error(f"[PUBLISH] Publishing failed: {str(e)}")
            updated_state = state.dict()
            updated_state['error_message'] = f"Publishing failed: {str(e)}"
            updated_state['action'] = None
            return GenerationState(**updated_state)
    
    @staticmethod
    async def next_subtopic_node(state: GenerationState) -> GenerationState:
        """Move to next subtopic - FIXED VERSION"""
        try:
            logger.info(f"[NEXT] Moving from subtopic {state.current_subtopic_index + 1} to next")
            
            # Create updated state
            updated_state = state.dict()
            
            # Check if we can move to next subtopic
            if state.current_subtopic_index < state.total_subtopics - 1:
                # Move to next subtopic
                updated_state['current_subtopic_index'] = state.current_subtopic_index + 1
                updated_state['current_content'] = None
                updated_state['ai_suggestions'] = None
                updated_state['consult_request'] = None
                updated_state['edit_data'] = None
                updated_state['error_message'] = None
                
                # CRITICAL FIX: Set action to 'generate' to generate next subtopic content
                updated_state['action'] = 'generate'
                logger.info(f"[NEXT] Moved to subtopic {updated_state['current_subtopic_index'] + 1}, action set to 'generate'")
                
            else:
                # All subtopics completed
                updated_state['action'] = None  # End workflow
                logger.info(f"[NEXT] All subtopics completed, ending workflow")
            
            return GenerationState(**updated_state)
            
        except Exception as e:
            logger.error(f"[NEXT] Failed to move to next subtopic: {str(e)}")
            updated_state = state.dict()
            updated_state['error_message'] = f"Next subtopic failed: {str(e)}"
            updated_state['action'] = None
            return GenerationState(**updated_state)