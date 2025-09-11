from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, JSON, DECIMAL
from sqlalchemy.sql import func
from app.database import Base

class SubtopicAssessment(Base):
    """Auto-generated quiz questions for subtopics"""
    __tablename__ = "subtopic_assessments"
    
    id = Column(Integer, primary_key=True, index=True)
    subtopic_id = Column(Integer, ForeignKey("subtopics.id", ondelete="CASCADE"), nullable=False)
    question = Column(Text, nullable=False)
    options = Column(JSON, nullable=False)
    correct_answer = Column(Integer, nullable=False)
    explanation = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class QuizAttempt(Base):
    """Student quiz attempts"""
    __tablename__ = "quiz_attempts"
    
    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    subtopic_id = Column(Integer, ForeignKey("subtopics.id", ondelete="CASCADE"), nullable=False)
    score_percentage = Column(DECIMAL(5, 2), nullable=False, default=0.00)
    completed_at = Column(DateTime(timezone=True), server_default=func.now())

class Assignment(Base):
    """Admin-created assignments"""
    __tablename__ = "assignments"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    questions = Column(JSON, nullable=False)
    total_marks = Column(Integer, nullable=False, default=0)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    due_date = Column(DateTime(timezone=True))
    is_published = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class AssignmentSubmission(Base):
    """Assignment submissions"""
    __tablename__ = "assignment_submissions"
    
    id = Column(Integer, primary_key=True, index=True)
    assignment_id = Column(Integer, ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False)
    student_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    answers = Column(JSON, nullable=False)
    awarded_marks = Column(Integer, default=0)
    feedback = Column(Text)
    submitted_at = Column(DateTime(timezone=True), server_default=func.now())
    graded_at = Column(DateTime(timezone=True))

class PracticeQuiz(Base):
    """Student practice quizzes"""
    __tablename__ = "practice_quizzes"
    
    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    topic_description = Column(Text, nullable=False)
    questions = Column(JSON, nullable=False)
    score_percentage = Column(DECIMAL(5, 2))
    completed_at = Column(DateTime(timezone=True), server_default=func.now())