from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime

class AssignmentRequest(BaseModel):
    description: str
    based_on_topics: Optional[List[int]] = None
    total_marks: int = 100

class AssignmentCreate(BaseModel):
    title: str
    description: Optional[str] = None
    questions: List[Dict[str, Any]]
    due_date: Optional[datetime] = None

class AssignmentSubmission(BaseModel):
    answers: List[str]

class AssignmentGrade(BaseModel):
    awarded_marks: int
    feedback: Optional[str] = None

# Practice Quiz Schemas
class PracticeQuizRequest(BaseModel):
    topic_description: str
    num_questions: int = 10

class PracticeQuizResponse(BaseModel):
    id: int
    questions: List[Dict[str, Any]]
    score_percentage: Optional[float] = None

class GenerationResponse(BaseModel):
    content: str
    subtopic_title: str
    current_subtopic: int
    total_subtopics: int
    quiz_questions: List[Dict[str, Any]]
    error: Optional[str] = None

class EditContentRequest(BaseModel):
    """For editing both content and quiz questions"""
    title: str
    content: str
    quiz_questions: Optional[List[Dict[str, Any]]] = None  