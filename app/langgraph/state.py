from typing import Optional
from pydantic import BaseModel

class GenerationState(BaseModel):
    """
    Simplified state that only tracks workflow position and actions.
    All content is stored in database, all context comes from vector retrieval.
    """
    # Core session info
    session_id: int
    topic_id: int
    topic_title: str
    level: str
    
    # Subtopic management - just position tracking
    subtopic_titles: list[str]
    current_subtopic_index: int
    total_subtopics: int
    
    # Workflow control
    action: Optional[str] = None
    error_message: Optional[str] = None
    
    # Edit data (only when editing)
    edit_data: Optional[dict] = None