from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.models.generation import GenerationSession,ConversationMessage
import tiktoken
import logging

logger = logging.getLogger(__name__)

class ConversationService:
    def __init__(self):
        # Initialize tokenizer for token counting
        self.tokenizer = tiktoken.get_encoding("cl100k_base")
        self.max_tokens = 4000  # Reserve tokens for generation
        
    def count_tokens(self, text: str) -> int:
        """Count tokens in text"""
        return len(self.tokenizer.encode(text))
    
    def get_conversation_history(self, db: Session, session_id: int) -> List[Dict[str, str]]:
        """Get conversation messages in OpenAI format"""
        messages = db.query(ConversationMessage).filter(
            ConversationMessage.session_id == session_id
        ).order_by(ConversationMessage.created_at).all()
        
        return [
            {
                "role": msg.role,
                "content": msg.content
            }
            for msg in messages
        ]
    
    def add_message(self, db: Session, session_id: int, role: str, 
                   content: str, subtopic_index: Optional[int] = None) -> ConversationMessage:
        """Add message to conversation"""
        token_count = self.count_tokens(content)
        
        message = ConversationMessage(
            session_id=session_id,
            role=role,
            content=content,
            subtopic_index=subtopic_index,
            token_count=token_count
        )
        db.add(message)
        
        # Update session token count
        session = db.query(GenerationSession).filter(
            GenerationSession.id == session_id
        ).first()
        if session:
            session.conversation_token_count += token_count
        
        db.commit()
        return message
    
    def truncate_conversation_if_needed(self, db: Session, session_id: int):
        """Intelligently truncate conversation to stay within token limits"""
        messages = db.query(ConversationMessage).filter(
            ConversationMessage.session_id == session_id
        ).order_by(ConversationMessage.created_at).all()
        
        total_tokens = sum(msg.token_count for msg in messages)
        
        if total_tokens > self.max_tokens:
            # Keep system message and recent messages
            system_messages = [msg for msg in messages if msg.role == "system"]
            other_messages = [msg for msg in messages if msg.role != "system"]
            
            # Keep last few subtopics worth of messages
            tokens_to_keep = self.max_tokens - sum(msg.token_count for msg in system_messages)
            
            messages_to_keep = []
            current_tokens = 0
            
            # Keep recent messages first
            for msg in reversed(other_messages):
                if current_tokens + msg.token_count <= tokens_to_keep:
                    messages_to_keep.insert(0, msg)
                    current_tokens += msg.token_count
                else:
                    # Remove old message
                    db.delete(msg)
            
            # Update session token count
            session = db.query(GenerationSession).filter(
                GenerationSession.id == session_id
            ).first()
            if session:
                session.conversation_token_count = sum(
                    msg.token_count for msg in system_messages + messages_to_keep
                )
            
            db.commit()
            logger.info(f"Truncated conversation for session {session_id}, kept {len(messages_to_keep)} messages")
    
    def initialize_conversation(self, db: Session, session_id: int, 
                              topic_title: str, topic_description: str, 
                              level: str, subtopic_titles: List[str]):
        """Initialize conversation with system message"""
        subtopic_list = "\n".join([f"{i+1}. {title}" for i, title in enumerate(subtopic_titles)])
        
        system_content = f"""You are generating comprehensive educational content for a course on "{topic_title}" at the {level} level.

Course Description: {topic_description}

Course Structure:
{subtopic_list}

Your role:
- Generate detailed, engaging educational content for each subtopic in sequence
- Build concepts progressively, referencing and building upon previous subtopics naturally
- Maintain consistent terminology and examples throughout
- Use clear structure with headings and bullet points
- Target 500-800 words per subtopic
- Reference previous concepts when relevant (e.g., "As we discussed in our coverage of...")

You will be prompted to generate content for each subtopic in order. Each should flow naturally from what came before while standing as complete educational material."""
        
        self.add_message(db, session_id, "system", system_content)
        logger.info(f"Initialized conversation for session {session_id}")

conversation_service = ConversationService()