from typing import List, Dict, Any
import re
import logging

logger = logging.getLogger(__name__)

class ChunkingService:
    """
    Breaks educational content into semantic chunks by concept type.
    Each chunk represents a specific educational element (definition, example, etc.)
    that can be independently embedded and retrieved for context.
    """
    
    def __init__(self):
        # Patterns to identify different types of educational content
        self.definition_patterns = [
            r"(.+?)(?:is|are|refers to|means|defined as)(.+?)(?=\n\n|\.|$)",
            r"(Definition|What is|What are)(.+?)(?=\n\n|Example|$)",
        ]
        
        self.example_patterns = [
            r"(Example|For example|Consider|For instance|Let's say)(.+?)(?=\n\n|$)",
            r"(Imagine|Suppose|Think about)(.+?)(?=\n\n|$)",
        ]
        
        self.procedure_patterns = [
            r"(Step \d+|First|Second|Third|Next|Finally|To do this)(.+?)(?=\n\n|Step|$)",
            r"(The process|The method|Algorithm|Procedure)(.+?)(?=\n\n|$)",
        ]
    
    def chunk_content(self, content: str, subtopic_title: str) -> List[Dict[str, Any]]:
        """
        Break content into semantic chunks based on educational patterns.
        
        Returns: List of chunks with type and content
        """
        chunks = []
        
        # Split content into paragraphs first
        paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
        
        for paragraph in paragraphs:
            chunk_type = self._identify_chunk_type(paragraph)
            
            # Only create chunk if paragraph has substantial content
            if len(paragraph.strip()) > 50:  # Skip very short paragraphs
                chunks.append({
                    'type': chunk_type,
                    'content': paragraph.strip(),
                    'subtopic_title': subtopic_title
                })
        
        # Always ensure we have at least one concept chunk from the subtopic title
        if not any(chunk['type'] == 'concept' for chunk in chunks):
            chunks.append({
                'type': 'concept',
                'content': f"Core concept: {subtopic_title}",
                'subtopic_title': subtopic_title
            })
        
        logger.info(f"Created {len(chunks)} chunks from content")
        return chunks
    
    def _identify_chunk_type(self, paragraph: str) -> str:
        """
        Analyze paragraph content to determine what type of educational element it is.
        """
        paragraph_lower = paragraph.lower()
        
        # Check for definitions first - these are most important for context
        for pattern in self.definition_patterns:
            if re.search(pattern, paragraph, re.IGNORECASE | re.DOTALL):
                return 'definition'
        
        # Check for examples
        for pattern in self.example_patterns:
            if re.search(pattern, paragraph, re.IGNORECASE | re.DOTALL):
                return 'example'
        
        # Check for procedures/steps
        for pattern in self.procedure_patterns:
            if re.search(pattern, paragraph, re.IGNORECASE | re.DOTALL):
                return 'procedure'
        
        # Check for applications (usually has words like "used for", "applies to")
        if any(phrase in paragraph_lower for phrase in [
            'used for', 'applies to', 'application', 'in practice', 'real world',
            'useful when', 'helps with', 'solves', 'addresses'
        ]):
            return 'application'
        
        # Default to concept if we can't identify specific type
        return 'concept'
    
    def create_context_summary(self, chunks: List[Dict[str, Any]]) -> str:
        """
        Create a condensed summary of chunks for use as context in generation.
        Prioritizes definitions and concepts over examples.
        """
        # Sort by importance for context: definitions > concepts > applications > procedures > examples
        importance_order = {'definition': 0, 'concept': 1, 'application': 2, 'procedure': 3, 'example': 4}
        
        sorted_chunks = sorted(chunks, key=lambda x: importance_order.get(x['type'], 5))
        
        # Build context string with type indicators
        context_parts = []
        for chunk in sorted_chunks:
            chunk_header = f"[{chunk['type'].upper()}]"
            context_parts.append(f"{chunk_header} {chunk['content'][:200]}...")  # Limit length
        
        return "\n\n".join(context_parts)

# Global instance
chunking_service = ChunkingService()