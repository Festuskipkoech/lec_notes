from app.langgraph.state import GenerationState
from app.database import SessionLocal
from app.models.notes import Subtopic
from sqlalchemy.sql import func
from app.utils.azure_openai import azure_client
import logging
logger = logging.getLogger(__name__)

class GenerationNodes:


    @staticmethod
    async def generate_content_node(state: GenerationState) -> GenerationState:
        """Generate content for current subtopic with coherence enforcement"""
        try:
            logger.info(f"[GENERATE] Starting coherence-aware generation for subtopic: {state.subtopic_titles[state.current_subtopic_index]}")
            current_index = state.current_subtopic_index
            subtopic_title = state.subtopic_titles[current_index]
            
            # Get previous subtopics content for coherence
            previous_contents = getattr(state, 'previous_subtopics_content', [])
            upcoming_concepts = getattr(state, 'upcoming_concepts', [])
            
            content = await azure_client.generate_subtopic_content(
                topic_title=state.topic_title,
                subtopic_title=subtopic_title,
                level=state.level,
                previous_subtopics_content=previous_contents,
                upcoming_concepts=upcoming_concepts
            )
            
            # Create updated state
            updated_state = state.dict()
            updated_state['current_content'] = content
            updated_state['generated_content'] = state.generated_content.copy()
            updated_state['generated_content'][current_index] = content
            updated_state['error_message'] = None
            updated_state['action'] = None  # End workflow after generation
            
            logger.info(f"[GENERATE] Content generated with coherence enforcement")
            return GenerationState(**updated_state)
            
        except Exception as e:
            logger.error(f"[GENERATE] Content generation failed: {str(e)}")
            updated_state = state.dict()
            updated_state['error_message'] = f"Generation failed: {str(e)}"
            updated_state['action'] = None
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
        """AI consultation - handled by service layer with conversation context"""
        try:
            logger.info(f"[CONSULT] AI consultation handled by service layer")
            updated_state = state.dict()
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
            
            # FIXED: Get content from the right source
            content_to_publish = None
            
            # Try current_content first
            if state.current_content:
                content_to_publish = state.current_content
            # Try generated_content as backup
            elif current_index in state.generated_content:
                content_to_publish = state.generated_content[current_index]
            else:
                logger.error(f"[PUBLISH] No content found for subtopic {current_index}")
                raise ValueError(f"No content available to publish for subtopic {current_index + 1}")
            
            logger.info(f"[PUBLISH] Content length: {len(content_to_publish) if content_to_publish else 0}")
            
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
                    content=content_to_publish,  # FIXED: Use the content we found
                    is_published=True,
                    published_at=func.now()
                )
                db.add(subtopic)
            else:
                subtopic.title = state.subtopic_titles[current_index]
                subtopic.content = content_to_publish  # FIXED: Use the content we found
                subtopic.is_published = True
                subtopic.published_at = func.now()
            
            db.commit()
            db.close()
            
            # Update state
            updated_state = state.dict()
            updated_state['current_content'] = content_to_publish  # Ensure current_content is set
            updated_state['published_subtopics'] = state.published_subtopics.copy()
            updated_state['published_subtopics'].append(current_index)
            updated_state['error_message'] = None
            
            # CRITICAL: Clear action to end workflow
            updated_state['action'] = None
            logger.info(f"[PUBLISH] Subtopic published successfully with content length: {len(content_to_publish)}")
            return GenerationState(**updated_state)
            
        except Exception as e:
            logger.error(f"[PUBLISH] Publishing failed: {str(e)}")
            updated_state = state.dict()
            updated_state['error_message'] = f"Publishing failed: {str(e)}"
            updated_state['action'] = None
            return GenerationState(**updated_state)
    

    @staticmethod
    async def next_subtopic_node(state: GenerationState) -> GenerationState:
        """Move to next subtopic and generate with full context awareness"""
        try:
            logger.info(f"[NEXT] Moving from subtopic {state.current_subtopic_index + 1} to next with coherence")
            
            updated_state = state.dict()
            
            # Check if we can move to next subtopic
            if state.current_subtopic_index < state.total_subtopics - 1:
                new_index = state.current_subtopic_index + 1
                updated_state['current_subtopic_index'] = new_index
                subtopic_title = state.subtopic_titles[new_index]
                
                # Get enhanced context
                previous_contents = getattr(state, 'previous_subtopics_content', [])
                upcoming_concepts = getattr(state, 'upcoming_concepts', [])
                
                # Generate content with full coherence context
                content = await azure_client.generate_subtopic_content(
                    topic_title=state.topic_title,
                    subtopic_title=subtopic_title,
                    level=state.level,
                    previous_subtopics_content=previous_contents,
                    upcoming_concepts=upcoming_concepts
                )
                
                # Update state with generated content
                updated_state['current_content'] = content
                updated_state['generated_content'] = state.generated_content.copy()
                updated_state['generated_content'][new_index] = content
                updated_state['ai_suggestions'] = None
                updated_state['consult_request'] = None
                updated_state['edit_data'] = None
                updated_state['error_message'] = None
                
                logger.info(f"[NEXT] Moved to subtopic {new_index + 1} with coherence-aware generation")
            else:
                logger.info(f"[NEXT] All subtopics completed")
            
            updated_state['action'] = None
            return GenerationState(**updated_state)
            
        except Exception as e:
            logger.error(f"[NEXT] Failed to move to next subtopic: {str(e)}")
            updated_state = state.dict()
            updated_state['error_message'] = f"Next subtopic failed: {str(e)}"
            updated_state['action'] = None
            return GenerationState(**updated_state)