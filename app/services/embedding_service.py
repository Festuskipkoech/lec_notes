from typing import List
from openai import AzureOpenAI
from app.config import settings
import asyncio
import logging
import re

logger = logging.getLogger(__name__)

class EmbeddingService:
    """
    Handles all embedding operations using Azure OpenAI's text-embedding-ada-002 model.
    Converts text into 1536-dimensional vectors that represent semantic meaning.
    """
    
    def __init__(self):
        self.client = AzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version
        )
        self.model = settings.azure_openai_embedding_deployment_name  # Use your deployment name
        self.max_batch_size = 20  # Azure allows up to 2048 inputs, but we'll batch smaller
    
    def _clean_text_for_embedding(self, text: str) -> str:
        """
        Clean text before embedding by removing base64 image data and other large content
        that would exceed token limits.
        """
        if not text:
            return text
            
        # Remove base64 image data in markdown format: ![alt](data:image/...)
        text = re.sub(r'!\[[^\]]*\]\(data:image[^)]+\)', '[IMAGE]', text)
        
        # Remove base64 image data in HTML format: <img src="data:image/...">
        text = re.sub(r'<img[^>]*src="data:image[^"]*"[^>]*>', '[IMAGE]', text)
        
        # Remove standalone base64 data URLs
        text = re.sub(r'data:image/[^;]+;base64,[A-Za-z0-9+/=]+', '[IMAGE_DATA]', text)
        
        # Additional safety: truncate if still too long (rough token estimation)
        # 1 token ≈ 4 characters, so 30,000 chars ≈ 7,500 tokens (under 8,192 limit)
        max_chars = 30000
        if len(text) > max_chars:
            text = text[:max_chars] + "\n\n[CONTENT TRUNCATED FOR EMBEDDING]"
            logger.warning(f"Text truncated to {max_chars} characters for embedding")
        
        return text
    
    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Convert list of texts into embeddings. Handles batching for efficiency.
        Automatically cleans texts to remove large content before embedding.
        
        Returns: List of 1536-dimensional vectors (one per input text)
        """
        if not texts:
            return []
        
        # Clean all texts before embedding
        cleaned_texts = [self._clean_text_for_embedding(text) for text in texts]
        
        # Log cleaning results
        for i, (original, cleaned) in enumerate(zip(texts, cleaned_texts)):
            if len(original) != len(cleaned):
                logger.info(f"Text {i} cleaned: {len(original)} -> {len(cleaned)} chars")
        
        # Process in batches to avoid API limits
        all_embeddings = []
        for i in range(0, len(cleaned_texts), self.max_batch_size):
            batch = cleaned_texts[i:i + self.max_batch_size]
            batch_embeddings = await self._embed_batch(batch)
            all_embeddings.extend(batch_embeddings)
        
        return all_embeddings
    
    async def _embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Send one batch to Azure OpenAI for embedding.
        """
        try:
            # Run in thread pool since Azure OpenAI client is synchronous
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.embeddings.create(input=texts, model=self.model)
            )
            
            # Extract embeddings from response - they come back as objects with embedding arrays
            embeddings = []
            for item in response.data:
                embeddings.append(item.embedding)  # This is the 1536-number array we want
            
            logger.info(f"Successfully embedded {len(texts)} texts")
            return embeddings
            
        except Exception as e:
            logger.error(f"Embedding failed: {str(e)}")
            raise Exception(f"Failed to create embeddings: {str(e)}")
    
    async def embed_single_text(self, text: str) -> List[float]:
        """
        Convenience method for embedding a single piece of text.
        Automatically cleans text before embedding.
        """
        embeddings = await self.embed_texts([text])
        return embeddings[0] if embeddings else []

# Global instance
embedding_service = EmbeddingService()