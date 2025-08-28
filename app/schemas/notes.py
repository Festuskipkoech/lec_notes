from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class SubtopicResponse(BaseModel):
    id: int
    order: int
    title: str
    content: Optional[str] = None
    is_published: bool
    published_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class TopicResponse(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    level: str
    total_subtopics: int
    subtopics: List[SubtopicResponse]
    created_at: datetime
    
    class Config:
        from_attributes = True

class TopicListResponse(BaseModel):
    id: int
    title: str
    level: str
    total_subtopics: int
    published_subtopics: int
    created_at: datetime
    
    class Config:
        from_attributes = True
