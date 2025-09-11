from app.langgraph.state import GenerationState
from app.database import SessionLocal
from app.models.notes import Subtopic
from app.models.content_chunks import ContentChunk
from app.services.vector_service import vector_service
from app.services.chunking_service import chunking_service
from app.utils.azure_openai import azure_client
from sqlalchemy.sql import func
import logging

logger = logging.getLogger(__name__)

class GenerationNodes:

    @staticmethod
    async def generate_content_node(state: GenerationState) -> GenerationState:
        """
        Generate content AND quiz questions using vector-enhanced context retrieval.
        """
        try:
            db = SessionLocal()
            current_index = state.current_subtopic_index
            subtopic_title = state.subtopic_titles[current_index]
            
            logger.info(f"[GENERATE] Starting content+quiz generation for subtopic {current_index + 1}: {subtopic_title}")
            
            # Build query for finding relevant context
            query_text = f"{state.topic_title} {subtopic_title}"
            
            # Get semantically relevant chunks from previous subtopics
            relevant_chunks = await vector_service.find_relevant_context(
                db, state.topic_id, query_text, current_index, limit=7
            )
            
            # Get previous subtopic for natural flow continuity
            previous_content = await vector_service.get_previous_subtopic_content(
                db, state.topic_id, current_index
            )
            
            # Format context for generation prompt
            formatted_context = vector_service.format_context_for_generation(
                relevant_chunks, previous_content
            )
            
            # Get upcoming concepts for forward-looking content
            upcoming_concepts = state.subtopic_titles[current_index + 1:current_index + 3]
            
            # CHANGED: Single call generates BOTH content and quiz
            result = await azure_client.generate_subtopic_with_vector_context(
                topic_title=state.topic_title,
                subtopic_title=subtopic_title,
                level=state.level,
                formatted_context=formatted_context,
                upcoming_concepts=upcoming_concepts
            )
            
            content = result["content"]
            quiz_questions = result["quiz_questions"]
            
            # Store content in database
            subtopic_record = await GenerationNodes._store_generated_content(
                db, state.topic_id, current_index, subtopic_title, content
            )
            
            # Store quiz questions
            from app.services.assessments import assessment_service
            assessment_service.store_subtopic_quiz(db, subtopic_record.id, quiz_questions)
            
            # Chunk the content and store with embeddings for future context retrieval
            chunks = chunking_service.chunk_content(content, subtopic_title)
            await vector_service.store_content_chunks(db, subtopic_record.id, chunks)
            
            db.close()
            logger.info(f"[GENERATE] Successfully generated subtopic {current_index + 1} with {len(chunks)} chunks and {len(quiz_questions)} quiz questions")
            
            # Return clean state
            updated_state = state.dict()
            updated_state['error_message'] = None
            updated_state['action'] = None
            return GenerationState(**updated_state)
            
        except Exception as e:
            logger.error(f"[GENERATE] Content+Quiz generation failed: {str(e)}")
            updated_state = state.dict()
            updated_state['error_message'] = f"Generation failed: {str(e)}"
            updated_state['action'] = None
            return GenerationState(**updated_state)

    
    @staticmethod
    async def _store_generated_content(db, topic_id: int, subtopic_index: int, 
                                     subtopic_title: str, content: str) -> Subtopic:
        """Store generated content in database and return the record."""
        
        # Check if subtopic already exists
        existing_subtopic = db.query(Subtopic).filter(
            Subtopic.topic_id == topic_id,
            Subtopic.order == subtopic_index + 1  # Convert 0-based to 1-based
        ).first()
        
        if existing_subtopic:
            # Update existing
            existing_subtopic.title = subtopic_title
            existing_subtopic.content = content
            existing_subtopic.updated_at = func.now()
            subtopic_record = existing_subtopic
        else:
            # Create new
            subtopic_record = Subtopic(
                topic_id=topic_id,
                order=subtopic_index + 1,
                title=subtopic_title,
                content=content,
                is_published=False
            )
            db.add(subtopic_record)
        
        db.commit()
        db.refresh(subtopic_record)
        return subtopic_record


    @staticmethod
    async def edit_content_node(state: GenerationState) -> GenerationState:
        """
        Handle manual content editing - update database and re-embed + update quiz if provided
        """
        try:
            db = SessionLocal()
            current_index = state.current_subtopic_index
            
            if state.edit_data and "content" in state.edit_data:
                # Find the subtopic record
                subtopic = db.query(Subtopic).filter(
                    Subtopic.topic_id == state.topic_id,
                    Subtopic.order == current_index + 1
                ).first()
                
                if subtopic:
                    # Update content
                    subtopic.content = state.edit_data["content"]
                    if "title" in state.edit_data:
                        subtopic.title = state.edit_data["title"]
                    subtopic.updated_at = func.now()
                    
                    # Re-chunk and re-embed the edited content
                    chunks = chunking_service.chunk_content(
                        subtopic.content, subtopic.title
                    )
                    
                    # Delete old chunks and create new ones
                    db.query(ContentChunk).filter(
                        ContentChunk.subtopic_id == subtopic.id
                    ).delete()
                    
                    await vector_service.store_content_chunks(db, subtopic.id, chunks)
                    
                    # ADDED: Update quiz questions if provided
                    if "quiz_questions" in state.edit_data:
                        from app.services.assessments import assessment_service
                        assessment_service.store_subtopic_quiz(
                            db, subtopic.id, state.edit_data["quiz_questions"]
                        )
                    
                    db.commit()
                    logger.info(f"[EDIT] Content edited and re-embedded with {len(chunks)} new chunks")
                else:
                    raise ValueError("Subtopic not found for editing")
            else:
                raise ValueError("No edit data provided")
            
            db.close()
            updated_state = state.dict()
            updated_state['error_message'] = None
            updated_state['edit_data'] = None
            updated_state['action'] = None
            return GenerationState(**updated_state)
                
        except Exception as e:
            logger.error(f"[EDIT] Edit failed: {str(e)}")
            updated_state = state.dict()
            updated_state['error_message'] = f"Edit failed: {str(e)}"
            updated_state['action'] = None
            return GenerationState(**updated_state)

    @staticmethod
    async def publish_subtopic_node(state: GenerationState) -> GenerationState:
        """Publish current subtopic - simple database flag update"""
        try:
            db = SessionLocal()
            current_index = state.current_subtopic_index
            
            subtopic = db.query(Subtopic).filter(
                Subtopic.topic_id == state.topic_id,
                Subtopic.order == current_index + 1
            ).first()
            
            if not subtopic:
                raise ValueError("No subtopic found to publish")
            
            if not subtopic.content:
                raise ValueError("Cannot publish subtopic without content")
            
            # Simple publish operation
            subtopic.is_published = True
            subtopic.published_at = func.now()
            db.commit()
            db.close()
            
            logger.info(f"[PUBLISH] Subtopic {current_index + 1} published successfully")
            
            updated_state = state.dict()
            updated_state['error_message'] = None
            updated_state['action'] = None
            return GenerationState(**updated_state)
            
        except Exception as e:
            logger.error(f"[PUBLISH] Publishing failed: {str(e)}")
            updated_state = state.dict()
            updated_state['error_message'] = f"Publishing failed: {str(e)}"
            updated_state['action'] = None
            return GenerationState(**updated_state)
    
    @staticmethod
    async def next_subtopic_node(state: GenerationState) -> GenerationState:
        """Move to next subtopic - ONLY increment index, don't generate content"""
        try:
            current_index = state.current_subtopic_index
            
            if current_index >= state.total_subtopics - 1:
                logger.info("[NEXT] All subtopics completed")
                updated_state = state.dict()
                updated_state['action'] = None
                return GenerationState(**updated_state)
            
            # ONLY move to next subtopic - don't generate content here
            new_index = current_index + 1
            logger.info(f"[NEXT] Moving from subtopic {current_index + 1} to {new_index + 1}")
            
            # Update state with new position ONLY
            updated_state = state.dict()
            updated_state['current_subtopic_index'] = new_index
            updated_state['error_message'] = None
            updated_state['edit_data'] = None
            updated_state['action'] = None  # End workflow here
            
            return GenerationState(**updated_state)
            
        except Exception as e:
            logger.error(f"[NEXT] Error moving to next subtopic: {str(e)}")
            updated_state = state.dict()
            updated_state['error_message'] = f"Failed to move to next subtopic: {str(e)}"
            updated_state['action'] = None
            return GenerationState(**updated_state)

    @staticmethod
    async def consult_ai_node(state: GenerationState) -> GenerationState:
        """AI consultation for content improvement"""
        try:
            # This integrates with the consultation service through the API layer
            # The actual consultation logic is handled in generation_service
            logger.info("[CONSULT] AI consultation completed")
            updated_state = state.dict()
            updated_state['action'] = None
            return GenerationState(**updated_state)
            
        except Exception as e:
            logger.error(f"[CONSULT] AI consultation failed: {str(e)}")
            updated_state = state.dict()
            updated_state['error_message'] = f"AI consultation failed: {str(e)}"
            updated_state['action'] = None
            return GenerationState(**updated_state)