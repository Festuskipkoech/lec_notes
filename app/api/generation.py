
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Dict, Any
from app.database import get_db
from app.dependencies import get_current_admin
from app.schemas.generation import (
    GenerationStart, GenerationSession, AIConsultRequest, 
    AIConsultResponse, EditSubtopicRequest
)
from app.services.generation_service import generation_service
from app.models.user import User
from app.models.generation import GenerationSession as GenerationSessionModel

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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start generation: {str(e)}"
        )

@router.post("/{session_id}/begin")
async def begin_generation(
    session_id: int,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Begin actual content generation for first subtopic"""
    try:
        result = await generation_service.begin_generation(db, session_id)
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to begin generation: {str(e)}"
        )

@router.post("/{session_id}/next")
async def generate_next_subtopic(
    session_id: int,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Generate next subtopic content"""
    try:
        result = await generation_service.generate_next_subtopic(db, session_id)
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate next subtopic: {str(e)}"
        )

@router.put("/{session_id}/edit")
async def edit_subtopic(
    session_id: int,
    request: EditSubtopicRequest,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Edit current subtopic content"""
    try:
        result = await generation_service.edit_subtopic(
            db, session_id, request.title, request.content
        )
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to edit subtopic: {str(e)}"
        )

@router.post("/{session_id}/ai-consult", response_model=AIConsultResponse)
async def consult_ai(
    session_id: int,
    request: AIConsultRequest,
    db: Session = Depends(get_db)
):
    """Get AI suggestions for improving current subtopic"""
    try:
        result = await generation_service.consult_ai(
            db, session_id, request.improvement_request
        )
        
        if result["error"]:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result["error"]
            )
        
        suggestions = result["suggestions"]
        return AIConsultResponse(
            suggestions=suggestions.get("suggestions", ""),
            recommended_changes=suggestions.get("recommended_changes", [])
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI consultation failed: {str(e)}"
        )

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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
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