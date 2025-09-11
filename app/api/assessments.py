from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.dependencies import get_current_user, get_current_admin
from app.models.user import User
from app.schemas.assessments import (
    AssignmentRequest, AssignmentCreate, AssignmentSubmission, AssignmentGrade,
    PracticeQuizRequest
)
from app.services.assessments import assessment_service
from app.models.assessments import PracticeQuiz
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assessments", tags=["assessments"])

# Assignment Endpoints - Admin
@router.post("/assignments/generate")
async def generate_assignment(
    request: AssignmentRequest,
    db: Session = Depends(get_db)
    ):
    """Generate assignment questions using AI"""
    try:
        result = await assessment_service.generate_assignment(
            db, request.description, request.based_on_topics
        )
        return {
            "success": True,
            "assignment_data": result
        }
    except Exception as e:
        logger.error(f"Error generating assignment: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate assignment: {str(e)}"
        )

@router.post("/assignments")
async def create_assignment(
    assignment: AssignmentCreate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    """Create and save assignment"""
    try:
        result = assessment_service.create_assignment(
            db, current_admin.id, assignment.title, assignment.description,
            assignment.questions, assignment.due_date
        )
        return {
            "success": True,
            "assignment_id": result.id,
            "title": result.title
        }
    except Exception as e:
        logger.error(f"Error creating assignment: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create assignment: {str(e)}"
        )

@router.post("/assignments/{assignment_id}/publish")
async def publish_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    """Publish assignment to students"""
    try:
        success = assessment_service.publish_assignment(db, assignment_id, current_admin.id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assignment not found or access denied"
            )
        return {
            "success": True,
            "message": "Assignment published successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error publishing assignment: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to publish assignment: {str(e)}"
        )

@router.get("/assignments/{assignment_id}/submissions")
async def get_submissions(
    assignment_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    """Get assignment submissions for grading"""
    try:
        submissions = assessment_service.get_submissions(db, assignment_id, current_admin.id)
        return {
            "success": True,
            "assignment_id": assignment_id,
            "submissions": submissions,
            "total_submissions": len(submissions)
        }
    except Exception as e:
        logger.error(f"Error getting submissions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get submissions: {str(e)}"
        )

@router.post("/assignments/submissions/{submission_id}/grade")
async def grade_submission(
    submission_id: int,
    grade: AssignmentGrade,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    """Grade assignment submission"""
    try:
        success = assessment_service.grade_assignment(
            db, submission_id, grade.awarded_marks, grade.feedback
        )
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Submission not found"
            )
        return {
            "success": True,
            "message": "Submission graded successfully",
            "awarded_marks": grade.awarded_marks
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error grading submission: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to grade submission: {str(e)}"
        )

# Assignment Endpoints - Student
@router.get("/assignments")
async def get_assignments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get available assignments for student"""
    try:
        assignments = assessment_service.get_assignments(db, current_user.id)
        return {
            "success": True,
            "assignments": assignments,
            "total_assignments": len(assignments)
        }
    except Exception as e:
        logger.error(f"Error getting assignments: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get assignments: {str(e)}"
        )

@router.post("/assignments/{assignment_id}/submit")
async def submit_assignment(
    assignment_id: int,
    submission: AssignmentSubmission,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Submit assignment answers"""
    try:
        success = assessment_service.submit_assignment(
            db, current_user.id, assignment_id, submission.answers
        )
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Assignment already submitted or assignment not found"
            )
        return {
            "success": True,
            "message": "Assignment submitted successfully",
            "assignment_id": assignment_id
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting assignment: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit assignment: {str(e)}"
        )

# Practice Quiz Endpoints
@router.post("/practice/generate")
async def generate_practice_quiz(
    request: PracticeQuizRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Generate practice quiz for self-assessment"""
    try:
        quiz_id = await assessment_service.generate_practice_quiz(
            db, current_user.id, request.topic_description, request.num_questions
        )
        
        # Get the generated quiz
        quiz = db.query(PracticeQuiz).filter(PracticeQuiz.id == quiz_id).first()
        if not quiz:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve generated quiz"
            )
        
        return {
            "success": True,
            "quiz": {
                "id": quiz.id,
                "topic_description": quiz.topic_description,
                "questions": quiz.questions,
                "total_questions": len(quiz.questions),
                "score_percentage": quiz.score_percentage
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating practice quiz: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate practice quiz: {str(e)}"
        )

@router.post("/practice/{quiz_id}/submit")
async def submit_practice_quiz(
    quiz_id: int,
    answers: List[int],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Submit practice quiz attempt"""
    try:
        result = assessment_service.submit_practice_quiz(
            db, quiz_id, current_user.id, answers
        )
        return {
            "success": True,
            "quiz_id": quiz_id,
            "results": result
        }
    except ValueError as e:
        logger.error(f"Validation error in practice quiz: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error submitting practice quiz: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit practice quiz: {str(e)}"
        )