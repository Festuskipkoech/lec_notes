from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
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
    conversation_token_count = Column(Integer,default=0)
    last_conversation_update = Column(DateTime(timezone=True), server_default=func.now())
    
    # Remove relationship to avoid circular dependency

class LangGraphCheckpoint(Base):
    __tablename__ = "langgraph_checkpoints"
    
    id = Column(Integer, primary_key=True, index=True)
    thread_id = Column(String, index=True)
    checkpoint_data = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
class ConversationMessage(Base):
    __tablename__ = "conversation_message"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("generation_sessions.id"), nullable=False)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    subtopic_index = Column(Integer, nullable=True)
    token_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True),server_default=func.now())