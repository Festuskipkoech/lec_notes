from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class GenerationStart(BaseModel):
    topic_description: str
    level: str
    num_subtopics: Optional[int] = None  # If None, let AI decide

class GenerationSession(BaseModel):
    id: int
    topic_id: int
    thread_id: str
    current_subtopic: int
    total_subtopics: int
    status: str
    subtopic_titles: Optional[List[str]] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

class AIConsultRequest(BaseModel):
    section_text: str
    improvement_request: str

class AIConsultResponse(BaseModel):
    suggestions: str
    recommended_changes: List[str]

class EditSubtopicRequest(BaseModel):
    """For workflow-based editing (existing functionality)"""
    title: str
    content: str

class EditContentRequest(BaseModel):
    """For direct content replacement editing (new functionality)"""
    title: str
    content: str