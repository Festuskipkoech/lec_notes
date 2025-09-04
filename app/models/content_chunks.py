from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
from pgvector.sqlalchemy import Vector

class ContentChunk(Base):
    """
    Stores semantic chunks of subtopic content with their vector embeddings.
    Each chunk represents a specific concept, example, or definition that can be
    retrieved later for building context in future generations.
    """
    __tablename__ = "content_chunks"
    
    id = Column(Integer, primary_key=True, index=True)
    subtopic_id = Column(Integer, ForeignKey("subtopics.id", ondelete="CASCADE"), nullable=False)
    chunk_type = Column(String(50), nullable=False)  # definition, example, application, etc.
    content = Column(Text, nullable=False)
    embedding = Column(Vector(1536))  # Vector storage for 1536-dimensional embeddings
    token_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationship back to subtopic
    subtopic = relationship("Subtopic", back_populates="content_chunks")