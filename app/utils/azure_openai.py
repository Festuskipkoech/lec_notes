from openai import AzureOpenAI
from app.config import settings
from typing import List, Dict, Any
import json
import logging

logger = logging.getLogger(__name__)

class AzureOpenAIClient:
    def __init__(self):
        self.client = AzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version
        )
    
    async def generate_subtopic_plan(self, topic_description: str, level: str, num_subtopics: int = None) -> List[str]:
        """Generate subtopic plan for a topic"""
        if num_subtopics:
            prompt = f"""
            Create a learning plan for the topic: "{topic_description}"
            Education Level: {level}
            Number of subtopics needed: {num_subtopics}
            
            Return only a list of {num_subtopics} subtopic titles that build progressively.
            Format as a numbered list.
            """
        else:
            prompt = f"""
            Create an optimal learning plan for the topic: "{topic_description}"
            Education Level: {level}
            
            Determine the best number of subtopics (between 3-8) and create titles that build progressively.
            Format as a numbered list.
            """
        
        response = self.client.chat.completions.create(
            model=settings.azure_openai_deployment_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        
        content = response.choices[0].message.content
        subtopics = [line.strip() for line in content.split('\n') if line.strip() and any(c.isdigit() for c in line[:3])]
        subtopics = [topic.split('.', 1)[-1].strip() for topic in subtopics]
        
        return subtopics
    async def generate_subtopic_with_vector_context(self, topic_title: str, subtopic_title: str, 
                                                level: str, formatted_context: str, 
                                                upcoming_concepts: List[str] = None) -> Dict[str, Any]:
        """
        Generate educational content AND quiz questions using vector-retrieved context.
        Returns both content and quiz_questions in single response.
        """
        
        # Detect if this is the first subtopic
        is_first_subtopic = (
            not formatted_context.strip() or 
            "RELEVANT CONCEPTS FROM PREVIOUS LESSONS:" in formatted_context and 
            len(formatted_context.strip()) < 100
        )
        
        # System prompt
        system_content = f"""You are a master educator creating a comprehensive course on "{topic_title}" for {level} learners.

    Your expertise:
    - Progressive concept building that flows naturally
    - Rich, memorable examples and applications  
    - Conceptual clarity without oversimplification
    - Consistent terminology throughout the course
    - Assessment design that tests understanding

    Your teaching philosophy:
    - Each concept builds naturally on established understanding
    - Use precise, consistent terminology 
    - Provide concrete examples before abstract concepts
    - Connect new ideas to previously covered foundations
    - Create assessments that test comprehension, not memorization

    CRITICAL: When creating quiz questions, you MUST distribute correct answers evenly across all options A, B, C, and D. Avoid bias toward any particular option.

    You must provide BOTH educational content AND quiz questions in a single response."""

        if is_first_subtopic:
            upcoming_text = f"\nNote: This content will later connect to: {', '.join(upcoming_concepts)}" if upcoming_concepts else ""
            
            user_content = f"""CREATE EDUCATIONAL CONTENT AND QUIZ FOR: {subtopic_title}

    {upcoming_text}

    You must provide BOTH:
    1. EDUCATIONAL CONTENT (700-900 words)
    2. QUIZ QUESTIONS (15-20 multiple choice questions)

    CONTENT REQUIREMENTS:
    - 700-900 words of substantive, engaging material
    - Jump directly into core concepts without meta-commentary
    - Include clear definitions and practical examples
    - Use precise, consistent terminology

    QUIZ REQUIREMENTS:
    - 15-20 multiple choice questions with 4 options each
    - Test understanding of key concepts
    - Include explanations for correct answers
    - IMPORTANT: Distribute correct answers evenly - roughly 25% each for A, B, C, and D options
    - Vary question types: definitions, applications, problem-solving, analysis

    RETURN AS JSON:
    {{
    "content": "Full educational content here...",
    
        "quiz_questions": [
            {{
                "id": unique_id,
                "question": "question text",
                "options": ["option A", "option B", "option C", "option D"],
                "correct_answer": "A" or "B" or "C" or "D",
                "explanation": "brief explanation of why this answer is correct"
            }}
        ]
    }}"""
        
        else:
            upcoming_text = f"\nNote: This content will later connect to: {', '.join(upcoming_concepts)}" if upcoming_concepts else ""
            
            user_content = f"""{formatted_context}

    {upcoming_text}

    CREATE EDUCATIONAL CONTENT AND QUIZ FOR: {subtopic_title}

    You must provide BOTH:
    1. EDUCATIONAL CONTENT (700-900 words)  
    2. QUIZ QUESTIONS (15-20 multiple choice questions)

    CONTENT REQUIREMENTS:
    - 700-900 words of substantive material
    - Weave in relevant concepts from context naturally
    - Include clear definitions and examples
    - Use consistent terminology from previous content

    QUIZ REQUIREMENTS:
    - 15-20 multiple choice questions with 4 options each
    - Test understanding of new concepts AND connections to previous material
    - Include explanations for correct answers
    - IMPORTANT: Distribute correct answers evenly - roughly 25% each for A, B, C, and D options
    - Mix question types: recall, application, analysis, synthesis

    RETURN AS JSON:
    {{
    "content": "Full educational content here...",
    "quiz_questions": [
        {{
        "question": "Question text?",
        "options": ["A", "B", "C", "D"], 
        "correct_answer": "A" or "B" or "C" or "D",
        "explanation": "Why this is correct"
        }}
    ]
    }}"""

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content}
        ]
        
        response = self.client.chat.completions.create(
            model=settings.azure_openai_deployment_name,
            messages=messages,
            temperature=0.5,
            max_tokens=10000  # Increased for more questions
        )
        
        content_response = response.choices[0].message.content.strip()
        
        # Extract JSON
        try:
            result_data = json.loads(content_response)
        except json.JSONDecodeError:
            import re
            json_match = re.search(r'\{.*\}', content_response, re.DOTALL)
            if json_match:
                result_data = json.loads(json_match.group())
            else:
                raise ValueError("Could not extract valid JSON from AI response")
        
        # Validate structure
        if not isinstance(result_data, dict) or 'content' not in result_data or 'quiz_questions' not in result_data:
            raise ValueError("Invalid response structure from AI")
        
        content = result_data['content']
        quiz_questions = result_data['quiz_questions']
        
        # Validate quiz questions
        validated_questions = []
        for question in quiz_questions:
            if self._validate_quiz_question(question):
                validated_questions.append(question)
        
        if not validated_questions:
            raise ValueError("No valid quiz questions generated")
        
        return {
            "content": content,
            "quiz_questions": validated_questions
        }
# NEW: AI Grading Method
    async def grade_assignment_submission(self, assignment_questions: List[Dict[str, Any]], 
                                        student_answers: List[str]) -> Dict[str, Any]:
        """Grade assignment submission question by question"""
        
        # Format assignment data for AI
        grading_data = []
        for i, (question, answer) in enumerate(zip(assignment_questions, student_answers)):
            grading_data.append({
                "question_number": i + 1,
                "question_text": question['question'],
                "max_marks": question['marks'],
                "marking_criteria": question.get('marking_criteria', 'Grade based on accuracy and completeness'),
                "guidance": question.get('guidance', ''),
                "student_answer": answer
            })
        
        prompt = f"""
        You are grading an assignment submission. Grade each question based on its marking criteria and award marks proportionally.

        Assignment Data: {json.dumps(grading_data, indent=2)}

        For each question:
        1. Read the question, marking criteria, and student answer
        2. Award marks out of the maximum available
        3. Provide clear explanation for your grading decision
        4. Provide the correct/model answer for student learning
        5. Be fair but thorough in assessment

        Return ONLY valid JSON in this exact format:
        {{
        "total_ai_marks": total_marks_awarded,
        "total_max_marks": sum_of_all_max_marks,
        "question_grades": [
            {{
            "question_index": 0,
            "ai_awarded_marks": marks_awarded,
            "max_marks": maximum_possible_marks,
            "ai_explanation": "Detailed explanation of why this grade was awarded",
            "correct_answer": "The complete correct/model answer for this question"
            }}
        ]
        }}
        """
        
        response = self.client.chat.completions.create(
            model=settings.azure_openai_deployment_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=4000
        )
        
        content_response = response.choices[0].message.content.strip()
        
        try:
            grading_result = json.loads(content_response)
        except json.JSONDecodeError:
            import re
            json_match = re.search(r'\{.*\}', content_response, re.DOTALL)
            if json_match:
                grading_result = json.loads(json_match.group())
            else:
                raise ValueError("Could not extract valid JSON from AI grading response")
        
        if not self._validate_grading_result(grading_result, len(assignment_questions)):
            raise ValueError("Invalid grading result structure from AI")
        
        return grading_result

    async def generate_practice_quiz(self, topic_description: str, number_of_questions: int, 
                                   difficulty_level: str) -> Dict[str, Any]:
        """Generate practice quiz questions for student self-assessment"""
        
        prompt = f"""
        Create a practice quiz for self-assessment on this topic: {topic_description}
        
        Requirements:
        - {number_of_questions} multiple choice questions
        - Difficulty level: {difficulty_level}
        - Questions should help students test their understanding
        - Mix different types: definitions, applications, problem-solving
        - Include common misconceptions as wrong answers
        - Provide helpful explanations for learning
        
        Return as JSON in this format:
        {{
          "title": "Practice Quiz: {topic_description[:50]}",
          "questions": [
            {{
              "question": "Question text?",
              "options": ["Option A", "Option B", "Option C", "Option D"],
              "correct_answer": 0,
              "explanation": "Detailed explanation for learning",
              "difficulty_level": "{difficulty_level}"
            }}
          ]
        }}
        """
        
        response = self.client.chat.completions.create(
            model=settings.azure_openai_deployment_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=3000
        )
        
        content_response = response.choices[0].message.content.strip()
        
        try:
            quiz_data = json.loads(content_response)
        except json.JSONDecodeError:
            import re
            json_match = re.search(r'\{.*\}', content_response, re.DOTALL)
            if json_match:
                quiz_data = json.loads(json_match.group())
            else:
                raise ValueError("Could not extract valid JSON from AI response")
        
        validated_questions = []
        for question in quiz_data.get('questions', []):
            if self._validate_quiz_question(question):
                validated_questions.append(question)
        
        if not validated_questions:
            raise ValueError("No valid questions generated")
        
        return {
            "title": quiz_data.get('title', f"Practice Quiz: {topic_description}"),
            "questions": validated_questions
        }

    async def consult_in_conversation(self, messages: List[Dict[str, str]], 
                                    improvement_request: str) -> Dict[str, Any]:
        """Get AI consultation within conversation context"""
        
        user_prompt = f"""Please review the content we just generated and provide specific improvement suggestions based on this request: {improvement_request}

Provide:
1. General suggestions for improvement
2. Specific recommended changes (as a list)

Format your response as JSON with keys: "suggestions" and "recommended_changes\""""
        
        conversation_messages = messages + [{"role": "user", "content": user_prompt}]
        
        response = self.client.chat.completions.create(
            model=settings.azure_openai_deployment_name,
            messages=conversation_messages,
            temperature=0.5,
            max_tokens=800
        )
        
        raw_content = response.choices[0].message.content
        
        try:
            parsed_response = json.loads(raw_content)
            return parsed_response
        except json.JSONDecodeError:
            return {
                "suggestions": raw_content,
                "recommended_changes": ["Review the suggestions above"]
            }

    def _validate_quiz_question(self, question: Dict[str, Any]) -> bool:
        """Validate that a quiz question has the required structure"""
        required_fields = ['question', 'options', 'correct_answer']
        
        for field in required_fields:
            if field not in question:
                return False
        
        if not isinstance(question['options'], list) or len(question['options']) != 4:
            return False
        correct_answer = question['correct_answer']
        
        if isinstance(correct_answer, str):
            # convert letter to index
            if correct_answer.upper() in ['A', 'B', 'C', 'D']:
                question['correct_answer'] = ord(correct_answer.upper()) -ord('A')
            else:
                return False
        elif isinstance(correct_answer, int):
            # Validate integer range
            if not (0 <= correct_answer <= 3):
                return False
        
        if not isinstance(question['correct_answer'], int) or not (0 <= question['correct_answer'] <= 3):
            return False
        
        if not isinstance(question['question'], str) or len(question['question'].strip()) < 10:
            return False
        
        return True
    
    # NEW: Validation for AI grading results
    def _validate_grading_result(self, result: Dict[str, Any], expected_questions: int) -> bool:
        """Validate AI grading result structure"""
        if not isinstance(result, dict):
            return False
        
        required_fields = ['total_ai_marks', 'total_max_marks', 'question_grades']
        for field in required_fields:
            if field not in result:
                return False
        
        if len(result['question_grades']) != expected_questions:
            return False
        
        for grade in result['question_grades']:
            required_grade_fields = ['question_index', 'ai_awarded_marks', 'max_marks', 'ai_explanation']
            for field in required_grade_fields:
                if field not in grade:
                    return False
            
            if not isinstance(grade['ai_awarded_marks'], int) or grade['ai_awarded_marks'] < 0:
                return False
            
            if grade['ai_awarded_marks'] > grade['max_marks']:
                return False
        
        return True

# Create global instance
azure_client = AzureOpenAIClient()