from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class Topic(Base):
    __tablename__ = "topics"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text)
    level = Column(String, nullable=False)
    creator_id = Column(Integer, ForeignKey("users.id"))
    total_subtopics = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Use string-based relationship to avoid circular imports
    creator = relationship("User", back_populates="topics")
    subtopics = relationship("Subtopic", back_populates="topic", cascade="all, delete-orphan")
    generation_sessions = relationship("GenerationSession", back_populates="topic", cascade="all, delete-orphan")

class Subtopic(Base):
    __tablename__ = "subtopics"
    
    id = Column(Integer, primary_key=True, index=True)
    topic_id = Column(Integer, ForeignKey("topics.id"))
    order = Column(Integer, nullable=False)
    title = Column(String, nullable=False)
    content = Column(Text)
    is_published = Column(Boolean, default=False)
    published_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    topic = relationship("Topic", back_populates="subtopics")