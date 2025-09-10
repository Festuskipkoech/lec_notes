# Import all models first without relationships
from app.models.user import User
from app.models.notes import Topic, Subtopic
from app.models.generation import GenerationSession
from app.models.content_chunks import ContentChunk

# All models are now available for relationship resolution