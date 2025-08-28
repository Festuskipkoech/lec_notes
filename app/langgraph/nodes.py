
from app.langgraph.state import GenerationState
from app.utils.azure_openai import azure_client
from app.database import SessionLocal
from app.models.notes import Subtopic
from sqlalchemy.sql import func

class GenerationNodes:
    
    @staticmethod
    async def generate_content_node(state: GenerationState) -> GenerationState:
        """Generate content for current subtopic"""
        try:
            print(f"Generating content for subtopic: {state.subtopic_titles[state.current_subtopic_index]}")
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
            
            state.current_content = content
            state.generated_content[current_index] = content
            state.error_message = None
            
        except Exception as e:
            import traceback
            print(f"Content generation failed: {traceback.format_exc()}")
            state.error_message = f"Generation failed: {str(e)}"
        
        return state
    
    @staticmethod
    async def edit_content_node(state: GenerationState) -> GenerationState:
        """Handle manual content editing"""
        try:
            if state.edit_data and "content" in state.edit_data:
                current_index = state.current_subtopic_index
                state.current_content = state.edit_data["content"]
                state.generated_content[current_index] = state.edit_data["content"]
                
                # Update subtopic title if provided
                if "title" in state.edit_data:
                    state.subtopic_titles[current_index] = state.edit_data["title"]
                
                state.error_message = None
            else:
                state.error_message = "No edit data provided"
                
        except Exception as e:
            state.error_message = f"Edit failed: {str(e)}"
        
        return state
    
    @staticmethod
    async def consult_ai_node(state: GenerationState) -> GenerationState:
        """Get AI suggestions for improvements"""
        try:
            if state.consult_request and state.current_content:
                suggestions = await azure_client.suggest_improvements(
                    content=state.current_content,
                    improvement_request=state.consult_request
                )
                state.ai_suggestions = suggestions
                state.error_message = None
            else:
                state.error_message = "No consultation request or content provided"
                
        except Exception as e:
            state.error_message = f"AI consultation failed: {str(e)}"
        
        return state
    
    @staticmethod
    async def publish_subtopic_node(state: GenerationState) -> GenerationState:
        """Publish current subtopic to database"""
        try:
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
            
            state.published_subtopics.append(current_index)
            state.error_message = None
            
        except Exception as e:
            state.error_message = f"Publishing failed: {str(e)}"
        
        return state
    
    @staticmethod
    async def next_subtopic_node(state: GenerationState) -> GenerationState:
        """Move to next subtopic"""
        if state.current_subtopic_index < state.total_subtopics - 1:
            state.current_subtopic_index += 1
            state.current_content = None
            state.ai_suggestions = None
            state.consult_request = None
            state.edit_data = None
        
        return state