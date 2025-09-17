from typing import List, Dict, Any,Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from app.models.assessments import (
    SubtopicAssessment, QuizAttempt, Assignment, AssignmentSubmission, PracticeQuiz
)
from app.schemas.assessments import QuestionSchema, AdminGradeReview, AssignmentCreate
from app.models.notes import Topic, Subtopic
from app.utils.azure_openai import azure_client
import logging

logger = logging.getLogger(__name__)

class AssessmentService:
    
    @staticmethod
    def store_subtopic_quiz(db: Session, subtopic_id: int, quiz_questions: List[Dict[str, Any]]) -> None:
        """Store quiz questions generated alongside content"""
        try:
            # Delete existing questions
            db.query(SubtopicAssessment).filter(
                SubtopicAssessment.subtopic_id == subtopic_id
            ).delete()
            
            # Store new questions
            for q in quiz_questions:
                assessment = SubtopicAssessment(
                    subtopic_id=subtopic_id,
                    question=q['question'],
                    options=q['options'],
                    correct_answer=q['correct_answer'],
                    explanation=q.get('explanation')
                )
                db.add(assessment)
            
            db.commit()
            logger.info(f"Stored {len(quiz_questions)} quiz questions for subtopic {subtopic_id}")
            
        except Exception as e:
            logger.error(f"Error storing quiz questions: {str(e)}")
            db.rollback()
            raise
    
    @staticmethod
    def get_subtopic_quiz(db: Session, subtopic_id: int) -> List[Dict[str, Any]]:
        """Get quiz questions for display (used by generation API)"""
        try:
            questions = db.query(SubtopicAssessment).filter(
                SubtopicAssessment.subtopic_id == subtopic_id
            ).all()
            
            return [
                {
                    "id": q.id,
                    "question": q.question,
                    "options": q.options,
                    "explanation": q.explanation
                } for q in questions
            ]
            
        except Exception as e:
            logger.error(f"Error getting quiz questions: {str(e)}")
            return []

    @staticmethod
    def submit_subtopic_quiz(db: Session, student_id: int, subtopic_id: int, answers: List[int]) -> Dict[str, Any]:
        """Submit and grade subtopic quiz"""
        try:
            # CHECK FOR EXISTING ATTEMPT FIRST
            existing_attempt = db.query(QuizAttempt).filter(
                QuizAttempt.student_id == student_id,
                QuizAttempt.subtopic_id == subtopic_id
            ).first()
            
            if existing_attempt:
                raise ValueError("Quiz already completed. Only one attempt allowed per quiz.")
            
            # Get questions
            questions = db.query(SubtopicAssessment).filter(
                SubtopicAssessment.subtopic_id == subtopic_id
            ).order_by(SubtopicAssessment.id).all()
            
            if not questions:
                raise ValueError("No quiz found for this subtopic")
            
            if len(answers) != len(questions):
                raise ValueError("Answer count doesn't match question count")
            
            # Grade quiz
            correct_count = 0
            results = []
            
            for i, (question, answer) in enumerate(zip(questions, answers)):
                is_correct = answer == question.correct_answer
                if is_correct:
                    correct_count += 1
                
                results.append({
                    "question": question.question,
                    "options": question.options,
                    "selected": answer,
                    "correct_answer": question.correct_answer,  # Fixed field name
                    "is_correct": is_correct,
                    "explanation": question.explanation
                })
            
            score_percentage = (correct_count / len(questions)) * 100
            
            # Store attempt WITH ANSWERS
            attempt = QuizAttempt(
                student_id=student_id,
                subtopic_id=subtopic_id,
                score_percentage=score_percentage,
                student_answers=answers  # Store individual answers
            )
            db.add(attempt)
            db.commit()
            
            logger.info(f"Quiz submitted: Student {student_id}, Score {score_percentage}%")
            
            return {
                "score_percentage": score_percentage,
                "correct_answers": [q.correct_answer for q in questions],  # Array format
                "total_questions": len(questions),
                "results": results,
                "passed": score_percentage >= 70
            }
            
        except Exception as e:
            logger.error(f"Error submitting quiz: {str(e)}")
            db.rollback()
            raise    
    @staticmethod
    def get_student_quiz_attempt(db: Session, student_id: int, subtopic_id: int) -> Dict[str, Any]:
        """Check if student has already attempted this subtopic quiz"""
        try:
            # Check for existing attempt
            attempt = db.query(QuizAttempt).filter(
                QuizAttempt.student_id == student_id,
                QuizAttempt.subtopic_id == subtopic_id
            ).order_by(QuizAttempt.completed_at.desc()).first() 
            
            if attempt:
                # Get the quiz questions
                questions = db.query(SubtopicAssessment).filter(
                    SubtopicAssessment.subtopic_id == subtopic_id
                ).order_by(SubtopicAssessment.id).all()                
                results = []
                for i, (question, student_answer) in enumerate(zip(questions, attempt.student_answers)):
                    is_correct = student_answer == question.correct_answer
                    results.append({
                        "question": question.question,
                        "options": question.options,
                        "selected": student_answer,
                        "correct_answer": question.correct_answer,
                        "is_correct": is_correct,
                        "explanation": question.explanation
                    })

                return {
                    "already_attempted": True,
                    "attempt_id": attempt.id,
                    "score_percentage": float(attempt.score_percentage),
                    "completed_at": attempt.completed_at,
                    "student_answers": attempt.student_answers,
                    "questions": [
                        {
                            "id": q.id,
                            "question": q.question,
                            "options": q.options,
                            "explanation": q.explanation
                        } for q in questions
                    ],
                    "results": {
                        "score_percentage": float(attempt.score_percentage),
                        "correct_answers": [q.correct_answer for q in questions],
                        "total_questions": len(questions),
                        "results": results,
                        "passed": attempt.score_percentage >= 70
                    }
                }
            else:
                return {"already_attempted": False}
                
        except Exception as e:
            logger.error(f"Error checking quiz attempt: {str(e)}")
            return {"already_attempted": False}
    @staticmethod
    def get_quiz_history(db: Session, student_id: int) -> List[Dict[str, Any]]:
        """Get student's quiz history"""
        try:
            attempts = db.query(QuizAttempt).join(Subtopic).filter(
                QuizAttempt.student_id == student_id
            ).order_by(QuizAttempt.completed_at.desc()).all()
            
            return [
                {
                    "attempt_id": attempt.id,
                    "subtopic_id": attempt.subtopic_id,
                    "subtopic_title": attempt.subtopic.title,
                    "score_percentage": float(attempt.score_percentage),
                    "completed_at": attempt.completed_at,
                    "passed": attempt.score_percentage >= 70
                } for attempt in attempts
            ]
            
        except Exception as e:
            logger.error(f"Error getting quiz history: {str(e)}")
            return []
    
    @staticmethod
    def create_assignment(db: Session, admin_id: int, assignment_data: AssignmentCreate) -> int:
        """Create assignment manually by admin"""
        try:
            # Convert QuestionSchema objects to dictionaries
            questions_dict = [
                {
                    "question": q.question,
                    "marks": q.marks,
                    "guidance": q.guidance,
                    "marking_criteria": q.marking_criteria
                }
                for q in assignment_data.questions
            ]
            
            total_marks = sum(q.marks for q in assignment_data.questions)
            
            assignment = Assignment(
                title=assignment_data.title,
                description=assignment_data.description,
                questions=questions_dict,
                total_marks=total_marks,
                created_by=admin_id,
                due_date=assignment_data.due_date,
                is_published=False  # Created but not published
            )
            
            db.add(assignment)
            db.commit()
            db.refresh(assignment)
            
            logger.info(f"Assignment created manually: {assignment.title}")
            return assignment.id
            
        except Exception as e:
            logger.error(f"Error creating assignment: {str(e)}")
            db.rollback()
            raise
    
    @staticmethod
    def edit_assignment(
        db: Session,                          
        assignment_id: int,                   
        admin_id: int,                        
        title: str,                           
        description: str,                     
        questions: List[QuestionSchema],      
        due_date: Optional[datetime] = None   
    ) -> bool:
        """Edit assignment - now allows editing published assignments"""
        try:
            # REMOVE the is_published == False restriction
            assignment = db.query(Assignment).filter(
                Assignment.id == assignment_id,
                Assignment.created_by == admin_id
                # Removed: Assignment.is_published == False
            ).first()
            
            if not assignment:
                return False
            
            assignment.title = title
            assignment.description = description
            
            # Convert QuestionSchema objects to dictionaries for JSON storage
            questions_dict = [
                {
                    "question": q.question,
                    "marks": q.marks,
                    "guidance": q.guidance,
                    "marking_criteria": q.marking_criteria
                }
                for q in questions
            ]
            assignment.questions = questions_dict
            assignment.due_date = due_date
            assignment.total_marks = sum(q.marks for q in questions)
            
            db.commit()
            logger.info(f"Assignment {assignment_id} edited (was_published: {assignment.is_published})")
            return True
            
        except Exception as e:
            logger.error(f"Error editing assignment: {str(e)}")
            db.rollback()
            return False
    
    @staticmethod
    def publish_assignment(db: Session, assignment_id: int, admin_id: int) -> bool:
        """Publish assignment to students"""
        try:
            assignment = db.query(Assignment).filter(
                Assignment.id == assignment_id,
                Assignment.created_by == admin_id
            ).first()
            
            if not assignment:
                return False
            
            assignment.is_published = True
            db.commit()
            
            logger.info(f"Assignment {assignment_id} published")
            return True
            
        except Exception as e:
            logger.error(f"Error publishing assignment: {str(e)}")
            db.rollback()
            return False
    
    @staticmethod
    def get_assignments_for_student(db: Session, student_id: int) -> List[Dict[str, Any]]:
        """Get published assignments for student"""
        try:
            assignments = db.query(Assignment).filter(Assignment.is_published == True).all()
            
            result = []
            for assignment in assignments:
                # Check submission status
                submission = db.query(AssignmentSubmission).filter(
                    AssignmentSubmission.assignment_id == assignment.id,
                    AssignmentSubmission.student_id == student_id
                ).first()
                
                student_questions = [
                    {
                        "question": q["question"],
                        "marks": q["marks"],
                        "guidance": q.get("guidance", "")
                    }
                    for q in assignment.questions
                ]
                
                result.append({
                    "id": assignment.id,
                    "title": assignment.title,
                    "description": assignment.description,
                    "questions": student_questions, 
                    "total_marks": assignment.total_marks,
                    "due_date": assignment.due_date,
                    "submitted": submission is not None,
                    "grade": submission.graded_at is not None if submission else False,
                    "awarded_marks": submission.awarded_marks if submission and submission.graded_at else None
                })
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting assignments: {str(e)}")
            return []
    
    @staticmethod
    async def submit_assignment(db: Session, student_id: int, assignment_id: int, answers: List[str]) -> bool:
        """Submit assignment and trigger AI grading"""
        try:
            # Check if already submitted
            existing = db.query(AssignmentSubmission).filter(
                AssignmentSubmission.assignment_id == assignment_id,
                AssignmentSubmission.student_id == student_id
            ).first()
            
            if existing:
                raise ValueError("Assignment already submitted. Only one submission allowed per assignment.")
            
            # Get assignment questions for AI grading
            assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
            if not assignment:
                raise ValueError("Assignment not found")
            
            # Trigger AI grading
            ai_grading_result = await azure_client.grade_assignment_submission(
                assignment.questions, answers
            )
            
            # Create submission with AI grades and status
            submission = AssignmentSubmission(
                assignment_id=assignment_id,
                student_id=student_id,
                answers=answers,
                ai_grades=ai_grading_result,
                awarded_marks=ai_grading_result['total_ai_marks'],
                status="ai_graded"  # Set status after AI grading
            )
            
            db.add(submission)
            db.commit()
            
            logger.info(f"Assignment {assignment_id} submitted by student {student_id} and AI-graded with {ai_grading_result['total_ai_marks']}/{ai_grading_result['total_max_marks']} marks")
            return True
            
        except Exception as e:
            logger.error(f"Error submitting assignment: {str(e)}")
            db.rollback()
            raise
    
    @staticmethod
    def get_assignment_submissions(db: Session, assignment_id: int, admin_id: int) -> Dict[str, Any]:
        """Get assignment with questions AND submissions for admin review"""
        try:
            # Get assignment with questions
            assignment = db.query(Assignment).filter(
                Assignment.id == assignment_id,
                Assignment.created_by == admin_id
            ).first()
            
            if not assignment:
                return {"assignment": None, "submissions": []}
            
            # Get submissions with AI grades
            submissions = db.query(AssignmentSubmission).filter(
                AssignmentSubmission.assignment_id == assignment_id
            ).order_by(AssignmentSubmission.submitted_at.asc()).all()
            
            return {
                "assignment": {
                    "id": assignment.id,
                    "title": assignment.title,
                    "description": assignment.description,
                    "questions": assignment.questions,
                    "total_marks": assignment.total_marks
                },
                "submissions": [
                    {
                        "id": sub.id,
                        "student_id": sub.student_id,
                        "answers": sub.answers,
                        "submitted_at": sub.submitted_at,
                        "ai_grades": sub.ai_grades,
                        "awarded_marks": sub.awarded_marks,
                        "feedback": sub.feedback,
                        "status": sub.status,
                        "graded_at": sub.graded_at,
                        "needs_review": sub.status == "ai_graded",
                        "completed": sub.status == "admin_reviewed"
                    } for sub in submissions
                ]
            }
        except Exception as e:
            logger.error(f"Error getting assignment for admin review: {str(e)}")
            return {"assignment": None, "submissions": []}
    @staticmethod
    def get_student_assignment_result(db: Session, student_id: int, assignment_id: int) -> Optional[Dict[str, Any]]:
        """Get student's graded assignment result with correct answers"""
        try:
            # Get the submission
            submission = db.query(AssignmentSubmission).filter(
                AssignmentSubmission.assignment_id == assignment_id,
                AssignmentSubmission.student_id == student_id
            ).first()
            
            if not submission or not submission.ai_grades:
                return None
            
            # Get assignment details
            assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
            if not assignment:
                return None
            
            # Build question results
            question_results = []
            ai_grades = submission.ai_grades
            
            for i, question in enumerate(assignment.questions):
                if i < len(ai_grades['question_grades']):
                    grade_info = ai_grades['question_grades'][i]
                    
                    # Use admin marks if available, otherwise AI marks
                    awarded_marks = grade_info.get('admin_awarded_marks', grade_info.get('ai_awarded_marks', 0))
                    
                    question_results.append({
                        "question_text": question['question'],
                        "max_marks": question['marks'],
                        "student_answer": submission.answers[i] if i < len(submission.answers) else "",
                        "awarded_marks": awarded_marks,
                        "ai_explanation": grade_info.get('ai_explanation', ''),
                        "correct_answer": grade_info.get('correct_answer', 'No model answer available'),
                        "admin_notes": grade_info.get('admin_notes')
                    })
            
            percentage = (submission.awarded_marks / assignment.total_marks) * 100 if assignment.total_marks > 0 else 0
            
            return {
                "assignment_id": assignment.id,
                "assignment_title": assignment.title,
                "total_marks": assignment.total_marks,
                "awarded_marks": submission.awarded_marks,
                "percentage": round(percentage, 1),
                "status": submission.status,
                "submitted_at": submission.submitted_at,
                "graded_at": submission.graded_at,
                "question_results": question_results
            }
            
        except Exception as e:
            logger.error(f"Error getting student assignment result: {str(e)}")
            return None   
    @staticmethod
    def get_admin_assignments(db: Session, admin_id: int) -> List[Dict[str, Any]]:
        """Get assignments created by admin with submission counts"""
        try:
            # REMOVE the is_published filter to show ALL assignments by admin
            assignments = db.query(Assignment).filter(
                Assignment.created_by == admin_id  # <-- REMOVED is_published == True filter
            ).order_by(Assignment.created_at.desc()).all()
            
            result = []
            for assignment in assignments:
                submission_count = db.query(AssignmentSubmission).filter(
                    AssignmentSubmission.assignment_id == assignment.id
                ).count()
                
                graded_count = db.query(AssignmentSubmission).filter(
                    AssignmentSubmission.assignment_id == assignment.id,
                    AssignmentSubmission.status == "admin_reviewed"
                ).count()
                
                result.append({
                    "id": assignment.id,
                    "title": assignment.title,
                    "description": assignment.description,
                    "total_marks": assignment.total_marks,
                    "is_published": assignment.is_published,  # This will show True/False
                    "due_date": assignment.due_date,
                    "created_at": assignment.created_at,
                    "submission_count": submission_count,
                    "graded_count": graded_count,
                    "pending_grading": submission_count - graded_count
                })
            
            return result
        except Exception as e:
            logger.error(f"Error getting admin assignments: {str(e)}")
            return []
    
    @staticmethod
    def update_admin_grades(db: Session, submission_id: int, admin_review: AdminGradeReview) -> bool:
        """Admin reviews and updates AI grades"""
        try:
            submission = db.query(AssignmentSubmission).filter(
                AssignmentSubmission.id == submission_id
            ).first()
            
            if not submission:
                return False
            
            # Update AI grades with admin overrides
            ai_grades = submission.ai_grades
            total_admin_marks = 0
            
            for admin_grade in admin_review.question_grades:
                question_idx = admin_grade.question_index
                if question_idx < len(ai_grades['question_grades']):
                    ai_grades['question_grades'][question_idx]['admin_awarded_marks'] = admin_grade.admin_awarded_marks or admin_grade.ai_awarded_marks
                    ai_grades['question_grades'][question_idx]['admin_notes'] = admin_grade.admin_notes
                    total_admin_marks += ai_grades['question_grades'][question_idx]['admin_awarded_marks']
            
            # Update submission with final marks and status
            submission.ai_grades = ai_grades
            submission.awarded_marks = total_admin_marks
            submission.status = "admin_reviewed"  # Update status
            submission.graded_at = func.now()     # Set final grading timestamp
            
            db.commit()
            logger.info(f"Admin updated grades for submission {submission_id}: {total_admin_marks} marks")
            return True
            
        except Exception as e:
            logger.error(f"Error updating admin grades: {str(e)}")
            db.rollback()
            return False
    
    # NEW: Get pending submissions count
    @staticmethod
    def get_pending_submissions_count(db: Session, admin_id: int) -> Dict[str, int]:
        """Get count of submissions pending admin review"""
        try:
            # Get assignments created by this admin
            admin_assignments = db.query(Assignment.id).filter(
                Assignment.created_by == admin_id,
                Assignment.is_published == True
            ).subquery()
            
            # Count submissions by status
            ai_graded_count = db.query(AssignmentSubmission).join(
                admin_assignments, AssignmentSubmission.assignment_id == admin_assignments.c.id
            ).filter(AssignmentSubmission.status == "ai_graded").count()
            
            admin_reviewed_count = db.query(AssignmentSubmission).join(
                admin_assignments, AssignmentSubmission.assignment_id == admin_assignments.c.id
            ).filter(AssignmentSubmission.status == "admin_reviewed").count()
            
            return {
                "pending_review": ai_graded_count,
                "completed": admin_reviewed_count,
                "total": ai_graded_count + admin_reviewed_count
            }
            
        except Exception as e:
            logger.error(f"Error getting pending submissions count: {str(e)}")
            return {"pending_review": 0, "completed": 0, "total": 0}

    @staticmethod
    async def generate_practice_quiz(db: Session, student_id: int, topic_description: str, num_questions: int = 10) -> int:
        """Generate practice quiz"""
        try:
            quiz_data = await azure_client.generate_practice_quiz(
                topic_description, num_questions, "medium"
            )
            
            practice_quiz = PracticeQuiz(
                student_id=student_id,
                topic_description=topic_description,
                questions=quiz_data['questions']
            )
            
            db.add(practice_quiz)
            db.commit()
            db.refresh(practice_quiz)
            
            logger.info(f"Practice quiz {practice_quiz.id} generated")
            return practice_quiz.id
            
        except Exception as e:
            logger.error(f"Error generating practice quiz: {str(e)}")
            db.rollback()
            raise
    @staticmethod
    def submit_practice_quiz(db: Session, quiz_id: int, student_id: int, answers: List[int]) -> Dict[str, Any]:
        """Submit practice quiz"""
        try:
            quiz = db.query(PracticeQuiz).filter(
                PracticeQuiz.id == quiz_id,
                PracticeQuiz.student_id == student_id
            ).first()
            
            if not quiz:
                raise ValueError("Practice quiz not found")
            
            # Check if already completed
            if quiz.score_percentage is not None:
                raise ValueError("Practice quiz already completed. Only one attempt allowed.")
            
            questions = quiz.questions
            if len(answers) != len(questions):
                raise ValueError("Answer count mismatch")
            
            # Calculate score
            correct_count = 0
            for i, answer in enumerate(answers):
                if answer == questions[i]['correct_answer']:
                    correct_count += 1
            
            score = (correct_count / len(questions)) * 100
            quiz.score_percentage = score
            db.commit()
            
            logger.info(f"Practice quiz {quiz_id} completed with {score}%")
            
            return {
                "score_percentage": score,
                "correct_answers": correct_count,
                "total_questions": len(questions)
            }
            
        except Exception as e:
            logger.error(f"Error submitting practice quiz: {str(e)}")
            db.rollback()
            raise

# Create service instance
assessment_service = AssessmentService()