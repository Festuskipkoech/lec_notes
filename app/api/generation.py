from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Dict, Any,Optional
from app.database import get_db
from app.dependencies import get_current_admin
from app.schemas.generation import (
    GenerationStart, GenerationSession, EditContentRequest
)
from app.services.generation_service import generation_service
from app.models.user import User
from app.models.generation import GenerationSession as GenerationSessionModel
import logging
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/generation", tags=["generation"])

@router.post("/start")
async def start_generation(
    request: GenerationStart,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
) -> Dict[str, Any]:
    """Start a new notes generation session"""
    try:
        result = await generation_service.start_generation(
            db=db,
            topic_description=request.topic_description,
            level=request.level,
            num_subtopics=request.num_subtopics,
            creator_id=current_user.id
        )
        return result
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start generation: {str(e)}"
        )
@router.post("/{session_id}/begin")
async def begin_generation(
    session_id: int,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Begin actual content generation - now returns content + quiz"""
    try:
        result = await generation_service.begin_generation(db, session_id)
        return {
            "content": result["content"],
            "subtopic_title": result["subtopic_title"],
            "current_subtopic": result["current_subtopic"],
            "total_subtopics": result["total_subtopics"],
            "quiz_questions": result["quiz_questions"],  # ADDED
            "error": result["error"]
        }
    except ValueError as e:
        logger.error(f"Error {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to begin generation: {str(e)}"
        )

@router.post("/{session_id}/next")
async def generate_next_subtopic(
    session_id: int,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Generate next subtopic - now returns content + quiz"""
    try:
        result = await generation_service.generate_next_subtopic(db, session_id)
        return {
            "content": result["content"],
            "subtopic_title": result["subtopic_title"],
            "current_subtopic": result["current_subtopic"],
            "total_subtopics": result["total_subtopics"],
            "quiz_questions": result["quiz_questions"],  # ADDED
            "error": result["error"]
        }
    except ValueError as e:
        logger.error(f"Error {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate next subtopic: {str(e)}"
        )

@router.put("/{session_id}/edit")
async def edit_subtopic_content(
    session_id: int,
    request: EditContentRequest,
    subtopic_order: Optional[int] = None,  # ADD THIS PARAMETER
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Edit subtopic content - can specify which subtopic to edit"""
    try:
        session = db.query(GenerationSessionModel).filter(
            GenerationSessionModel.id == session_id
        ).first()
        
        if not session:
            raise ValueError("Generation session not found")
        
        # Use specified subtopic or default to current
        target_subtopic_order = subtopic_order or session.current_subtopic
        
        # Find the target subtopic to edit
        from app.models.notes import Subtopic
        target_subtopic = db.query(Subtopic).filter(
            Subtopic.topic_id == session.topic_id,
            Subtopic.order == target_subtopic_order
        ).first()
        
        if not target_subtopic:
            raise ValueError(f"Subtopic {target_subtopic_order} not found")
        
        # Update the target subtopic content directly
        target_subtopic.title = request.title
        target_subtopic.content = request.content
        
        # Re-process vector embeddings
        from app.models.content_chunks import ContentChunk
        db.query(ContentChunk).filter(
            ContentChunk.subtopic_id == target_subtopic.id
        ).delete()
        
        # Re-chunk and re-embed the new content
        from app.services.chunking_service import chunking_service
        from app.services.vector_service import vector_service
        chunks = chunking_service.chunk_content(request.content, request.title)
        await vector_service.store_content_chunks(db, target_subtopic.id, chunks)
        
        db.commit()
        
        return {
            "success": True,
            "message": "Subtopic content updated successfully",
            "subtopic_title": request.title,
            "content": request.content,
            "edited_subtopic": target_subtopic_order,
            "total_subtopics": session.total_subtopics
        }
        
    except Exception as e:
        logger.error(f"Error editing subtopic: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to edit subtopic: {str(e)}"
        )

# AI-Consult endpoint - SUSPENDED (temporarily disabled)
# @router.post("/{session_id}/ai-consult", response_model=AIConsultResponse)
# async def consult_ai(
#     session_id: int,
#     request: AIConsultRequest,
#     db: Session = Depends(get_db)
# ):
#     """Get AI suggestions for improving current subtopic"""
#     try:
#         result = await generation_service.consult_ai(
#             db, session_id, request.improvement_request
#         )
        
#         if result["error"]:
#             raise HTTPException(
#                 status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#                 detail=result["error"]
#             )
        
#         # Fix: Handle the case where suggestions might be None
#         suggestions = result.get("suggestions")
        
#         if suggestions is None:
#             # Return empty response if no suggestions
#             return AIConsultResponse(
#                 suggestions="",
#                 recommended_changes=[]
#             )
        
#         # Handle both dict and string responses from AI
#         if isinstance(suggestions, dict):
#             return AIConsultResponse(
#                 suggestions=suggestions.get("suggestions", ""),
#                 recommended_changes=suggestions.get("recommended_changes", [])
#             )
#         else:
#             # If suggestions is a string, put it in suggestions field
#             return AIConsultResponse(
#                 suggestions=str(suggestions),
#                 recommended_changes=[]
#             )
            
#     except ValueError as e:
#         logger.error(f"Error {str(e)}")
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail=str(e)
#         )
#     except Exception as e:
#         logger.error(f"Error {str(e)}")
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail=f"AI consultation failed: {str(e)}"
#         )

@router.post("/{session_id}/publish")
async def publish_subtopic(
    session_id: int,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Publish current subtopic for student access"""
    try:
        result = await generation_service.publish_subtopic(db, session_id)
        return result
    except ValueError as e:
        logger.error(f"Error {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to publish subtopic: {str(e)}"
        )

@router.get("/{session_id}/status", response_model=GenerationSession)
async def get_generation_status(
    session_id: int,
    db: Session = Depends(get_db)
):
    """Get current generation session status"""
    session = db.query(GenerationSessionModel).filter(
        GenerationSessionModel.id == session_id
    ).first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generation session not found"
        )
    
    return session

@router.delete("/{session_id}")
async def cancel_generation(
    session_id: int,
    db: Session = Depends(get_db)
):
    """Cancel generation session"""
    session = db.query(GenerationSessionModel).filter(
        GenerationSessionModel.id == session_id
    ).first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generation session not found"
        )
    
    session.status = "cancelled"
    db.commit()
    
    return {"message": "Generation session cancelled"}

@router.get("/{session_id}/analytics")
async def get_content_analytics(
    session_id: int,
    db: Session = Depends(get_db)
):
    """Get content quality analytics and vector coverage analysis"""
    session = db.query(GenerationSessionModel).filter(
        GenerationSessionModel.id == session_id
    ).first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generation session not found"
        )
    
    analytics = await generation_service.get_content_analytics(db, session.topic_id)
    
    return {
        "session_id": session_id,
        "topic_id": session.topic_id,
        "analytics": analytics
    }