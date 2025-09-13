from typing import List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from app.models.assessments import (
    SubtopicAssessment, QuizAttempt, Assignment, AssignmentSubmission, PracticeQuiz
)
from app.models.notes import Topic, Subtopic
from app.utils.azure_openai import azure_client
import logging

logger = logging.getLogger(__name__)

class AssessmentService:
    
    # Subtopic Quiz Management (for generation workflow)
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
    
    # Assignment Management (Generate → Review → Publish workflow)
    @staticmethod
    async def generate_and_create_assignment(db: Session, admin_id: int, description: str, 
                                           based_on_topics: List[int] = None) -> Assignment:
        """Generate assignment with AI and create it automatically"""
        try:
            # Get context from topics if provided
            context = ""
            if based_on_topics:
                topics = db.query(Topic).filter(Topic.id.in_(based_on_topics)).all()
                for topic in topics:
                    subtopics = db.query(Subtopic).filter(
                        Subtopic.topic_id == topic.id,
                        Subtopic.is_published == True
                    ).all()
                    for sub in subtopics:
                        if sub.content:
                            context += f"{sub.title}: {sub.content[:500]}...\n"
            
            # Generate questions
            assignment_data = await azure_client.generate_assignment_questions(
                description=description,
                number_of_questions=5,
                difficulty_level="medium",
                context_content=context
            )
            
            # Auto-create assignment
            total_marks = assignment_data.get('total_marks', 100)
            title = assignment_data.get('suggested_title', f"Assignment: {description[:50]}")
            
            assignment = Assignment(
                title=title,
                description=description,
                questions=assignment_data['questions'],
                total_marks=total_marks,
                created_by=admin_id,
                is_published=False  # Created but not published
            )
            
            db.add(assignment)
            db.commit()
            db.refresh(assignment)
            
            logger.info(f"Generated and created assignment: {title}")
            return assignment
            
        except Exception as e:
            logger.error(f"Error generating assignment: {str(e)}")
            db.rollback()
            raise
    
    @staticmethod
    def edit_assignment(db: Session, assignment_id: int, admin_id: int, 
                       title: str, description: str, questions: List[Dict[str, Any]], 
                       due_date=None) -> bool:
        """Edit assignment before publishing"""
        try:
            assignment = db.query(Assignment).filter(
                Assignment.id == assignment_id,
                Assignment.created_by == admin_id,
                Assignment.is_published == False  # Only edit unpublished
            ).first()
            
            if not assignment:
                return False
            
            assignment.title = title
            assignment.description = description
            assignment.questions = questions
            assignment.due_date = due_date
            assignment.total_marks = sum(q.get('marks', 20) for q in questions)
            
            db.commit()
            logger.info(f"Assignment {assignment_id} edited")
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
                
                result.append({
                    "id": assignment.id,
                    "title": assignment.title,
                    "description": assignment.description,
                    "questions": assignment.questions,
                    "total_marks": assignment.total_marks,
                    "due_date": assignment.due_date,
                    "submitted": submission is not None,
                    "graded": submission.graded_at is not None if submission else False,
                    "awarded_marks": submission.awarded_marks if submission and submission.graded_at else None
                })
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting assignments: {str(e)}")
            return []
    
    @staticmethod
    def submit_assignment(db: Session, student_id: int, assignment_id: int, answers: List[str]) -> bool:
        """Submit assignment"""
        try:
            # Check if already submitted
            existing = db.query(AssignmentSubmission).filter(
                AssignmentSubmission.assignment_id == assignment_id,
                AssignmentSubmission.student_id == student_id
            ).first()
            
            if existing:
                raise ValueError("Assignment already submitted. Only one submission allowed per assignment.")
            
            submission = AssignmentSubmission(
                assignment_id=assignment_id,
                student_id=student_id,
                answers=answers
            )
            
            db.add(submission)
            db.commit()
            
            logger.info(f"Assignment {assignment_id} submitted by student {student_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error submitting assignment: {str(e)}")
            db.rollback()
            raise  # Changed from return False to raise
    
    @staticmethod
    def get_assignment_submissions(db: Session, assignment_id: int, admin_id: int) -> List[Dict[str, Any]]:
        """Get submissions for grading"""
        try:
            # Verify admin owns assignment
            assignment = db.query(Assignment).filter(
                Assignment.id == assignment_id,
                Assignment.created_by == admin_id
            ).first()
            
            if not assignment:
                return []
            
            submissions = db.query(AssignmentSubmission).filter(
                AssignmentSubmission.assignment_id == assignment_id
            ).all()
            
            return [
                {
                    "id": sub.id,
                    "student_id": sub.student_id,
                    "answers": sub.answers,
                    "submitted_at": sub.submitted_at,
                    "awarded_marks": sub.awarded_marks,
                    "feedback": sub.feedback,
                    "graded": sub.graded_at is not None
                } for sub in submissions
            ]
            
        except Exception as e:
            logger.error(f"Error getting submissions: {str(e)}")
            return []
    
    @staticmethod
    def grade_assignment_submission(db: Session, submission_id: int, awarded_marks: int, feedback: str = None) -> bool:
        """Grade assignment submission"""
        try:
            submission = db.query(AssignmentSubmission).filter(
                AssignmentSubmission.id == submission_id
            ).first()
            
            if not submission:
                return False
            
            submission.awarded_marks = awarded_marks
            submission.feedback = feedback
            submission.graded_at = func.now()
            
            db.commit()
            logger.info(f"Submission {submission_id} graded with {awarded_marks} marks")
            return True
            
        except Exception as e:
            logger.error(f"Error grading submission: {str(e)}")
            db.rollback()
            return False
    
    # Practice Quiz Management
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