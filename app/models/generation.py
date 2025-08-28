from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import enum

class GenerationStatus(str, enum.Enum):
    planning = "planning"
    generating = "generating"
    reviewing = "reviewing"
    completed = "completed"
    cancelled = "cancelled"

class GenerationSession(Base):
    __tablename__ = "generation_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    topic_id = Column(Integer, ForeignKey("topics.id"))
    thread_id = Column(String, unique=True, nullable=False)
    current_subtopic = Column(Integer, default=0)
    total_subtopics = Column(Integer, nullable=False)
    status = Column(String, default=GenerationStatus.planning)
    subtopic_titles = Column(JSON)  # Store planned subtopic titles
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    topic = relationship("Topic", back_populates="generation_sessions")

class LangGraphCheckpoint(Base):
    __tablename__ = "langgraph_checkpoints"
    
    id = Column(Integer, primary_key=True, index=True)
    thread_id = Column(String, index=True)
    checkpoint_data = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())