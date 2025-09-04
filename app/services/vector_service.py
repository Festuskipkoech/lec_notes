from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.models.content_chunks import ContentChunk
from app.models.notes import Subtopic
from app.services.embedding_service import embedding_service
import logging

logger = logging.getLogger(__name__)

class VectorService:
    """
    Handles all vector operations including storage, retrieval, and similarity search.
    Uses PostgreSQL with pgvector extension for efficient vector operations.
    """
    
    async def store_content_chunks(self, db: Session, subtopic_id: int, chunks: List[Dict[str, Any]]) -> List[ContentChunk]:
        """
        Store content chunks with their embeddings in the database.
        """
        if not chunks:
            return []
        
        # Extract just the text content for embedding
        texts_to_embed = [chunk['content'] for chunk in chunks]
        
        # Get embeddings from Azure OpenAI
        embeddings = await embedding_service.embed_texts(texts_to_embed)
        
        # Create ContentChunk records
        stored_chunks = []
        for chunk_data, embedding in zip(chunks, embeddings):
            chunk_record = ContentChunk(
                subtopic_id=subtopic_id,
                chunk_type=chunk_data['type'],
                content=chunk_data['content'],
                embedding=embedding,  # pgvector handles the array conversion
                token_count=len(chunk_data['content'].split())  # Rough token estimate
            )
            db.add(chunk_record)
            stored_chunks.append(chunk_record)
        
        db.commit()
        logger.info(f"Stored {len(stored_chunks)} content chunks for subtopic {subtopic_id}")
        
        return stored_chunks
    
    async def find_relevant_context(self, db: Session, topic_id: int, query_text: str, 
                                   current_subtopic_index: int, limit: int = 7) -> List[Dict[str, Any]]:
        """
        Find the most relevant content chunks from previous subtopics using vector similarity.
        This is where the magic happens - semantic search across all previous learning.
        """
        # Get embedding for the query (what we're about to generate)
        query_embedding = await embedding_service.embed_single_text(query_text)
        
        # Use pgvector's cosine_distance function with proper SQLAlchemy syntax
        from sqlalchemy import select
        from app.models.content_chunks import ContentChunk
        from app.models.notes import Subtopic
        
        # Build query using SQLAlchemy ORM with pgvector functions
        query = (
            select(
                ContentChunk.content,
                ContentChunk.chunk_type,
                Subtopic.title.label('subtopic_title'),
                Subtopic.order.label('subtopic_order'),
                ContentChunk.embedding.cosine_distance(query_embedding).label('similarity_distance')
            )
            .join(Subtopic, ContentChunk.subtopic_id == Subtopic.id)
            .where(
                Subtopic.topic_id == topic_id,
                Subtopic.order < current_subtopic_index + 1,  # +1 because order is 1-based
                Subtopic.is_published == True
            )
            .order_by(ContentChunk.embedding.cosine_distance(query_embedding))
            .limit(limit)
        )
        
        result = db.execute(query)
        
        # Convert results to list of dictionaries
        relevant_chunks = []
        for row in result:
            relevant_chunks.append({
                'content': row.content,
                'type': row.chunk_type,
                'subtopic_title': row.subtopic_title,
                'subtopic_order': row.subtopic_order,
                'similarity_score': 1 - row.similarity_distance  # Convert distance to similarity score
            })
        
        logger.info(f"Found {len(relevant_chunks)} relevant chunks for context")
        return relevant_chunks
    
    async def get_previous_subtopic_content(self, db: Session, topic_id: int, 
                                          current_subtopic_index: int) -> Optional[str]:
        """
        Get the full content of the immediately previous subtopic for natural flow continuity.
        """
        if current_subtopic_index == 0:
            return None  # No previous subtopic
        
        previous_subtopic = db.query(Subtopic).filter(
            Subtopic.topic_id == topic_id,
            Subtopic.order == current_subtopic_index,  # Previous order (current_index is 0-based, order is 1-based)
            Subtopic.is_published == True
        ).first()
        
        return previous_subtopic.content if previous_subtopic else None
    
    def format_context_for_generation(self, relevant_chunks: List[Dict[str, Any]], 
                                    previous_content: Optional[str] = None) -> str:
        """
        Format retrieved chunks and previous content into a coherent context for generation.
        """
        context_parts = []
        
        # Add relevant chunks grouped by type
        if relevant_chunks:
            context_parts.append("RELEVANT CONCEPTS FROM PREVIOUS LESSONS:")
            
            # Group chunks by type for better organization
            chunks_by_type = {}
            for chunk in relevant_chunks:
                chunk_type = chunk['type']
                if chunk_type not in chunks_by_type:
                    chunks_by_type[chunk_type] = []
                chunks_by_type[chunk_type].append(chunk)
            
            # Add each type section
            for chunk_type, type_chunks in chunks_by_type.items():
                context_parts.append(f"\n{chunk_type.upper()} concepts:")
                for chunk in type_chunks[:3]:  # Limit per type
                    context_parts.append(f"- {chunk['content'][:300]}...")  # Truncate for brevity
        
        # Add previous subtopic for natural flow
        if previous_content:
            context_parts.append(f"\nPREVIOUS LESSON CONCLUSION:")
            context_parts.append(previous_content[-500:])  # Last 500 chars for flow continuity
        
        return "\n".join(context_parts)
    
    async def get_concept_coverage_analysis(self, db: Session, topic_id: int) -> Dict[str, Any]:
        """
        Analyze concept coverage across the topic to identify gaps or redundancies.
        """
        # Get all chunks for this topic
        chunks_query = text("""
            SELECT cc.chunk_type, COUNT(*) as count
            FROM content_chunks cc
            JOIN subtopics s ON cc.subtopic_id = s.id
            WHERE s.topic_id = :topic_id
            GROUP BY cc.chunk_type
            ORDER BY count DESC
        """)
        
        result = db.execute(chunks_query, {'topic_id': topic_id})
        
        coverage = {}
        for row in result:
            coverage[row.chunk_type] = row.count
        
        return {
            'total_chunks': sum(coverage.values()),
            'coverage_by_type': coverage,
            'balance_score': self._calculate_balance_score(coverage)
        }
    
    def _calculate_balance_score(self, coverage: Dict[str, int]) -> float:
        """
        Calculate how well-balanced the content is across different concept types.
        """
        if not coverage:
            return 0.0
        
        # Ideal ratios for educational content
        ideal_ratios = {
            'definition': 0.3,  # 30% should be definitions/concepts
            'example': 0.25,    # 25% examples
            'application': 0.25, # 25% applications
            'procedure': 0.15,   # 15% procedures
            'concept': 0.05     # 5% general concepts
        }
        
        total_chunks = sum(coverage.values())
        if total_chunks == 0:
            return 0.0
        
        # Calculate actual ratios
        actual_ratios = {k: v/total_chunks for k, v in coverage.items()}
        
        # Compare with ideal ratios
        balance_score = 0.0
        for chunk_type, ideal_ratio in ideal_ratios.items():
            actual_ratio = actual_ratios.get(chunk_type, 0)
            # Penalize deviation from ideal
            deviation = abs(actual_ratio - ideal_ratio)
            balance_score += max(0, 1 - deviation)
        
        return balance_score / len(ideal_ratios)

# Global instance
vector_service = VectorService()