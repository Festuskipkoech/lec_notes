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

# Subtopic Quiz Endpoints (for quizzes generated with content)
@router.post("/quiz/submit")
async def submit_subtopic_quiz(
    subtopic_id: int,
    answers: List[int],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Submit subtopic quiz answers"""
    try:
        result = assessment_service.submit_subtopic_quiz(
            db, current_user.id, subtopic_id, answers
        )
        return {
            "success": True,
            "subtopic_id": subtopic_id,
            "score_percentage": result["score_percentage"],
            "correct_answers": result["correct_answers"],
            "total_questions": result["total_questions"],
            "passed": result["passed"],
            "results": result["results"]
        }
    except ValueError as e:
        logger.error(f"Quiz submission error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error submitting quiz: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit quiz: {str(e)}"
        )

@router.get("/quiz/history")
async def get_quiz_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get student's quiz history"""
    try:
        history = assessment_service.get_quiz_history(db, current_user.id)
        return {
            "success": True,
            "quiz_attempts": history,
            "total_attempts": len(history)
        }
    except Exception as e:
        logger.error(f"Error getting quiz history: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get quiz history: {str(e)}"
        )

# Assignment Endpoints - Admin (Generate → Review → Publish workflow)
@router.post("/assignments/generate")
async def generate_assignment(
    request: AssignmentRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    """Generate assignment with AI and create automatically"""
    try:
        assignment = await assessment_service.generate_and_create_assignment(
            db, current_admin.id, request.description, request.based_on_topics
        )
        
        return {
            "success": True,
            "assignment_id": assignment.id,
            "title": assignment.title,
            "description": assignment.description,
            "questions": assignment.questions,
            "total_marks": assignment.total_marks,
            "status": "generated_ready_for_review"
        }
    except Exception as e:
        logger.error(f"Error generating assignment: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate assignment: {str(e)}"
        )

@router.put("/assignments/{assignment_id}/edit")
async def edit_assignment(
    assignment_id: int,
    assignment: AssignmentCreate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    """Edit assignment before publishing"""
    try:
        success = assessment_service.edit_assignment(
            db, assignment_id, current_admin.id,
            assignment.title, assignment.description, 
            assignment.questions, assignment.due_date
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assignment not found or already published"
            )
        
        return {
            "success": True,
            "message": "Assignment updated successfully",
            "assignment_id": assignment_id
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error editing assignment: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to edit assignment: {str(e)}"
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
            "message": "Assignment published successfully",
            "assignment_id": assignment_id
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
async def get_assignment_submissions(
    assignment_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    """Get assignment submissions for grading"""
    try:
        submissions = assessment_service.get_assignment_submissions(
            db, assignment_id, current_admin.id
        )
        
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
async def grade_assignment_submission(
    submission_id: int,
    grade: AssignmentGrade,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    """Grade assignment submission"""
    try:
        success = assessment_service.grade_assignment_submission(
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
            "submission_id": submission_id,
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
async def get_available_assignments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get published assignments for student"""
    try:
        assignments = assessment_service.get_assignments_for_student(db, current_user.id)
        
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
                detail="Assignment already submitted or not found"
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

# Practice Quiz Endpoints - Student
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
            "quiz_id": quiz.id,
            "topic_description": quiz.topic_description,
            "questions": quiz.questions,
            "total_questions": len(quiz.questions)
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
            "score_percentage": result["score_percentage"],
            "correct_answers": result["correct_answers"],
            "total_questions": result["total_questions"]
        }
    except ValueError as e:
        logger.error(f"Practice quiz validation error: {str(e)}")
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