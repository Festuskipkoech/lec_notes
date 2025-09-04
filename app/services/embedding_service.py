from typing import List, Dict, Any
from openai import AzureOpenAI
from app.config import settings
import asyncio
import logging

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
    
    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Convert list of texts into embeddings. Handles batching for efficiency.
        
        Returns: List of 1536-dimensional vectors (one per input text)
        """
        if not texts:
            return []
        
        # Process in batches to avoid API limits
        all_embeddings = []
        for i in range(0, len(texts), self.max_batch_size):
            batch = texts[i:i + self.max_batch_size]
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
        """
        embeddings = await self.embed_texts([text])
        return embeddings[0] if embeddings else []

# Global instance
embedding_service = EmbeddingService()