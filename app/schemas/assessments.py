from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime

# Quiz Schemas
class QuizAttemptRequest(BaseModel):
    subtopic_id: int
    answers: List[int]  # Selected option indices

class QuizAttemptResponse(BaseModel):
    score_percentage: float
    correct_answers: int
    total_questions: int
    results: List[Dict[str, Any]]
    passed: bool

# Assignment Schemas
class AssignmentRequest(BaseModel):
    description: str
    based_on_topics: Optional[List[int]] = None
    total_marks: int = 100

class QuestionSchema(BaseModel):
    question: str
    marks: int
    guidance: Optional[str] = None
    marking_criteria: Optional[str] = None

class StudentQuestionResult(BaseModel):
    question_text: str
    max_marks: int
    student_answer: str
    awarded_marks: int  # Final marks (admin or AI)
    ai_explanation: str
    correct_answer: str
    admin_notes: Optional[str] = None

class StudentAssignmentResult(BaseModel):
    assignment_id: int
    assignment_title: str
    total_marks: int
    awarded_marks: int
    percentage: float
    status: str
    submitted_at: datetime
    graded_at: Optional[datetime]
    question_results: List[StudentQuestionResult]
class AssignmentCreate(BaseModel):
    title: str
    description: Optional[str] = None
    questions: List[QuestionSchema]
    due_date: Optional[datetime] = Field(None, description="Due date in UTC")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }

class AssignmentSubmission(BaseModel):
    answers: List[str]

class AssignmentGrade(BaseModel):
    awarded_marks: int
    feedback: Optional[str] = None

class QuestionGrade(BaseModel):
    question_index: int
    ai_awarded_marks: int
    max_marks: int
    ai_explanation: str
    admin_awarded_marks: Optional[int] = None  # Admin can override
    admin_notes: Optional[str] = None

class AIGradingResult(BaseModel):
    total_ai_marks: int
    total_max_marks: int
    question_grades: List[QuestionGrade]

class AdminGradeReview(BaseModel):
    question_grades: List[QuestionGrade]  # Admin's final grades per question

# Practice Quiz Schemas
class PracticeQuizRequest(BaseModel):
    topic_description: str
    num_questions: int = 10

class PracticeQuizResponse(BaseModel):
    id: int
    questions: List[Dict[str, Any]]
    score_percentage: Optional[float] = None

# Enhanced Generation Response
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