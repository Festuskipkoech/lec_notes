from typing import List, Dict, Any, Optional
from pydantic import BaseModel

class GenerationState(BaseModel):
    # Core session info
    session_id: int
    topic_id: int
    topic_title: str
    topic_description: str
    level: str
    
    # Subtopic management
    subtopic_titles: List[str]
    current_subtopic_index: int
    total_subtopics: int
    
    # Content tracking
    generated_content: Dict[int, str] = {}  # subtopic_index -> content
    published_subtopics: List[int] = []
    
    # Context for AI
    previous_concepts: List[str] = []
    upcoming_concepts: List[str] = []
    
    # Workflow control
    action: Optional[str] = None  # "generate", "edit", "consult", "publish", "next"
    edit_data: Optional[Dict[str, Any]] = None
    consult_request: Optional[str] = None
    
    # Results
    current_content: Optional[str] = None
    ai_suggestions: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None