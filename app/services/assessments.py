from typing import List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from app.models.assessments import SubtopicAssessment, Assignment, AssignmentSubmission, PracticeQuiz
from app.models.notes import Topic, Subtopic
from app.utils.azure_openai import azure_client
import logging

logger = logging.getLogger(__name__)

class AssessmentService:
    
    @staticmethod
    def store_subtopic_quiz(db: Session, subtopic_id: int, quiz_questions: List[Dict[str, Any]]) -> None:
        """Store quiz questions for a subtopic (used by generation workflow)"""
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
        """Get quiz questions for a subtopic (used by generation API)"""
        try:
            questions = db.query(SubtopicAssessment).filter(
                SubtopicAssessment.subtopic_id == subtopic_id
            ).all()
            
            return [
                {
                    "id": q.id,
                    "question": q.question,
                    "options": q.options
                } for q in questions
            ]
            
        except Exception as e:
            logger.error(f"Error getting quiz questions: {str(e)}")
            return []
    
    # Assignment Methods
    @staticmethod
    async def generate_assignment(db: Session, description: str, based_on_topics: List[int] = None) -> Dict[str, Any]:
        """Generate assignment questions using AI"""
        try:
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
            
            result = await azure_client.generate_assignment_questions(
                description=description,
                number_of_questions=5,
                difficulty_level="medium",
                context_content=context
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error generating assignment: {str(e)}")
            raise Exception(f"Failed to generate assignment: {str(e)}")
    
    @staticmethod
    def create_assignment(db: Session, admin_id: int, title: str, description: str, 
                         questions: List[Dict[str, Any]], due_date=None) -> Assignment:
        """Create and save assignment"""
        try:
            total_marks = sum(q.get('marks', 20) for q in questions)
            
            assignment = Assignment(
                title=title,
                description=description,
                questions=questions,
                total_marks=total_marks,
                created_by=admin_id,
                due_date=due_date
            )
            
            db.add(assignment)
            db.commit()
            db.refresh(assignment)
            
            logger.info(f"Created assignment: {title}")
            return assignment
            
        except Exception as e:
            logger.error(f"Error creating assignment: {str(e)}")
            db.rollback()
            raise Exception(f"Failed to create assignment: {str(e)}")
    
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
            
            logger.info(f"Published assignment {assignment_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error publishing assignment: {str(e)}")
            db.rollback()
            return False
    
    @staticmethod
    def get_assignments(db: Session, student_id: int) -> List[Dict[str, Any]]:
        """Get published assignments for student"""
        try:
            assignments = db.query(Assignment).filter(Assignment.is_published == True).all()
            
            result = []
            for assignment in assignments:
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
                    "score": submission.awarded_marks if submission and submission.graded_at else None
                })
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting assignments: {str(e)}")
            return []
    
    @staticmethod
    def submit_assignment(db: Session, student_id: int, assignment_id: int, answers: List[str]) -> bool:
        """Submit assignment answers"""
        try:
            # Check if already submitted
            existing = db.query(AssignmentSubmission).filter(
                AssignmentSubmission.assignment_id == assignment_id,
                AssignmentSubmission.student_id == student_id
            ).first()
            
            if existing:
                return False
            
            # Create submission
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
            return False
    
    @staticmethod
    def grade_assignment(db: Session, submission_id: int, awarded_marks: int, feedback: str = None) -> bool:
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
            
            logger.info(f"Graded submission {submission_id} with {awarded_marks} marks")
            return True
            
        except Exception as e:
            logger.error(f"Error grading assignment: {str(e)}")
            db.rollback()
            return False
    
    @staticmethod
    def get_submissions(db: Session, assignment_id: int, admin_id: int) -> List[Dict[str, Any]]:
        """Get assignment submissions for grading"""
        try:
            # Verify admin owns this assignment
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
    
    # Practice Quiz Methods
    @staticmethod
    async def generate_practice_quiz(db: Session, student_id: int, topic_description: str, num_questions: int = 10) -> int:
        """Generate and store practice quiz"""
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
            
            logger.info(f"Generated practice quiz {practice_quiz.id} for student {student_id}")
            return practice_quiz.id
            
        except Exception as e:
            logger.error(f"Error generating practice quiz: {str(e)}")
            db.rollback()
            raise Exception(f"Failed to generate practice quiz: {str(e)}")
    
    @staticmethod
    def submit_practice_quiz(db: Session, quiz_id: int, student_id: int, answers: List[int]) -> Dict[str, Any]:
        """Submit practice quiz attempt"""
        try:
            quiz = db.query(PracticeQuiz).filter(
                PracticeQuiz.id == quiz_id,
                PracticeQuiz.student_id == student_id
            ).first()
            
            if not quiz:
                raise ValueError("Practice quiz not found")
            
            questions = quiz.questions
            if len(answers) != len(questions):
                raise ValueError("Answer count mismatch")
            
            # Calculate score
            correct_count = 0
            for i, answer in enumerate(answers):
                if answer == questions[i]['correct_answer']:
                    correct_count += 1
            
            score = (correct_count / len(questions)) * 100
            
            # Update quiz with score
            quiz.score_percentage = score
            db.commit()
            
            logger.info(f"Practice quiz {quiz_id} submitted with score {score}%")
            
            return {
                "score_percentage": score,
                "correct_answers": correct_count,
                "total_questions": len(questions)
            }
            
        except Exception as e:
            logger.error(f"Error submitting practice quiz: {str(e)}")
            db.rollback()
            raise Exception(f"Failed to submit practice quiz: {str(e)}")

# Create service instance
assessment_service = AssessmentService()