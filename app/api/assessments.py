from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.dependencies import get_current_user, get_current_admin
from app.models.user import User
from app.schemas.assessments import (
    AssignmentCreate, AssignmentSubmission, 
    PracticeQuizRequest, QuizAttemptRequest, AdminGradeReview, SubtopicQuizEdit
)
from app.services.assessments import assessment_service
from app.models.assessments import PracticeQuiz
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assessments", tags=["assessments"])

@router.post("/quiz/submit")
async def submit_subtopic_quiz(
    request: QuizAttemptRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Submit subtopic quiz answers"""
    try:
        result = assessment_service.submit_subtopic_quiz(
            db, current_user.id, request.subtopic_id, request.answers
        )
        return {
            "success": True,
            "subtopic_id": request.subtopic_id,
            **result
        }
    except ValueError as e:
        # Handle duplicate submission gracefully
        logger.warning(f"Quiz submission validation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,  # Changed to 409 Conflict
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error submitting quiz: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit quiz: {str(e)}"
        )
        
@router.get("/subtopic/{subtopic_id}/quiz")
async def get_subtopic_quiz(
    subtopic_id:int,
    db:Session = Depends(get_db)
):
    # Get quiz questions for a published topic
    try:
        quiz_questions = assessment_service.get_subtopic_quiz(db, subtopic_id)
        return {
            "success": True,
            "questions": quiz_questions,
            "subtopic_id": subtopic_id
        }
    except Exception as e:
        raise HTTPException(
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail = f"Failed to get subtopic quiz {str(e)}"
        )

@router.get("/subtopic/{subtopic_id}/attempt")
async def get_quiz_attempt_status(
    subtopic_id: int, 
    db: Session =  Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        attempt_data = assessment_service.get_student_quiz_attempt(
            db, current_user.id, subtopic_id
        )
        return {
            "success": True,
            "subtopic_id": subtopic_id,
            **attempt_data
        }
    except Exception as e:
        logger.error(f"Error getting current status {str(e)}")
        raise HTTPException(
            status_code =status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail = f"Failed to get attempt status {str(e)}"
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

# Assignment Endpoints - Admin (Manual Create → Edit → Publish → AI Grade → Admin Review workflow)
@router.get("/assignments/{assignment_id}/result")
async def get_assignment_result(
    assignment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get student's assignment result with correct answers and explanations"""
    try:
        result = assessment_service.get_student_assignment_result(
            db, current_user.id, assignment_id
        )
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assignment result not found or not yet graded"
            )
        
        return {
            "success": True,
            **result
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting assignment result: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get assignment result: {str(e)}"
        )
@router.put("/subtopic/{subtopic_id}/edit-quiz")
async def edit_subtopic_quiz(
    subtopic_id: int,
    quiz_edit: SubtopicQuizEdit,
    db: Session= Depends(get_db),
    current_admin: Session = Depends(get_current_admin)
):
    try:
        from app.models.notes import Subtopic, Topic
        subtopic = db.query(Subtopic).join(Topic).filter(
            Subtopic.id == subtopic_id,
            Topic.creator_id == current_admin.id
        ).first()
        if not subtopic:
            raise HTTPException(
                status_code = status.HTTP_403_FORBIDDEN,
                detail ="Access denied!"
            )
        result = assessment_service.edit_subtopic_quiz(
            db, subtopic_id, quiz_edit.quiz_questions
        )
        return {
            "success": True,
            "subtopic_id": subtopic_id,
            **result
        }
    except Exception as e:
        logger.error(f"Error editing subtopic quiz: {str(e)}")
@router.post("/assignments/create")
async def create_assignment(
    assignment: AssignmentCreate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    """Admin creates assignment manually"""
    try:
        assignment_id = assessment_service.create_assignment(
            db, current_admin.id, assignment
        )
        
        return {
            "success": True,
            "assignment_id": assignment_id,
            "message": "Assignment created successfully"
        }
    except Exception as e:
        logger.error(f"Error creating assignment: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create assignment: {str(e)}"
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
            db,
            assignment_id, 
            current_admin.id,
            assignment.title,
            assignment.description,
            assignment.questions,
            assignment.due_date
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
            **submissions
        }
    except Exception as e:
        logger.error(f"Error getting submissions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get submissions: {str(e)}"
        )

@router.get("/assignments/admin")
async def get_admin_assignments(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    # Get all published assignments by admin with submission stats
    try:
        assignments = assessment_service.get_admin_assignments(db, current_admin.id)
        return {
            "success": True,
            "assignments": assignments
        }
    except Exception as e:
        logger.error(f"Error getting admin assignments {str(e)}")
        raise HTTPException(
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail = f"Failed to get assignments: {str(e)}"
        )

# NEW: Admin grade review endpoint
@router.put("/assignments/submissions/{submission_id}/review-grades")
async def review_ai_grades(
    submission_id: int,
    admin_review: AdminGradeReview,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    """Admin reviews and adjusts AI-awarded grades"""
    try:
        success = assessment_service.update_admin_grades(
            db, submission_id, admin_review
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Submission not found"
            )
        
        return {
            "success": True,
            "message": "Grades reviewed and updated successfully",
            "submission_id": submission_id
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reviewing grades: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to review grades: {str(e)}"
        )

# NEW: Get pending submissions count
@router.get("/assignments/pending-submissions")
async def get_pending_submissions(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    """Get count of submissions pending admin review"""
    try:
        counts = assessment_service.get_pending_submissions_count(db, current_admin.id)
        return {
            "success": True,
            **counts
        }
    except Exception as e:
        logger.error(f"Error getting pending submissions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get pending submissions: {str(e)}"
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

# UPDATED: Submit assignment with AI grading
@router.post("/assignments/{assignment_id}/submit")
async def submit_assignment(
    assignment_id: int,
    submission: AssignmentSubmission,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Submit assignment answers and trigger AI grading"""
    try:
        success = await assessment_service.submit_assignment(
            db, current_user.id, assignment_id, submission.answers
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Assignment already submitted or not found"
            )
        
        return {
            "success": True,
            "message": "Assignment submitted and AI-graded successfully",
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

# Practice Quiz Endpoints - Student (KEEP AS IS)
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
    submission: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Submit practice quiz attempt"""
    try:
        answers = submission.get('answers', [])
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