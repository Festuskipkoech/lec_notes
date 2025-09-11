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

You must provide BOTH educational content AND quiz questions in a single response."""

        if is_first_subtopic:
            upcoming_text = f"\nNote: This content will later connect to: {', '.join(upcoming_concepts)}" if upcoming_concepts else ""
            
            user_content = f"""CREATE EDUCATIONAL CONTENT AND QUIZ FOR: {subtopic_title}

{upcoming_text}

You must provide BOTH:
1. EDUCATIONAL CONTENT (700-900 words)
2. QUIZ QUESTIONS (4-6 multiple choice questions)

CONTENT REQUIREMENTS:
- 700-900 words of substantive, engaging material
- Jump directly into core concepts without meta-commentary
- Include clear definitions and practical examples
- Use precise, consistent terminology

QUIZ REQUIREMENTS:
- 4-6 multiple choice questions with 4 options each
- Test understanding of key concepts
- Include explanations for correct answers

RETURN AS JSON:
{{
  "content": "Full educational content here...",
  "quiz_questions": [
    {{
      "question": "Question text?",
      "options": ["A", "B", "C", "D"],
      "correct_answer": 0,
      "explanation": "Why this is correct"
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
2. QUIZ QUESTIONS (4-6 multiple choice questions)

CONTENT REQUIREMENTS:
- 700-900 words of substantive material
- Weave in relevant concepts from context naturally
- Include clear definitions and examples
- Use consistent terminology from previous content

QUIZ REQUIREMENTS:
- 4-6 multiple choice questions with 4 options each
- Test understanding of new concepts AND connections to previous material
- Include explanations for correct answers

RETURN AS JSON:
{{
  "content": "Full educational content here...",
  "quiz_questions": [
    {{
      "question": "Question text?",
      "options": ["A", "B", "C", "D"], 
      "correct_answer": 0,
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
            max_tokens=7000
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

    async def generate_assignment_questions(self, description: str, number_of_questions: int, 
                                          difficulty_level: str, context_content: str = "", 
                                          total_marks: int = 100) -> Dict[str, Any]:
        """Generate assignment questions (Q&A format) based on description and topic context"""
        
        context_section = f"\n\nCONTEXT FROM PUBLISHED TOPICS:\n{context_content}" if context_content else ""
        
        prompt = f"""
        Create assignment questions based on this description: {description}
        
        Requirements:
        - {number_of_questions} questions total
        - Difficulty level: {difficulty_level}
        - Total marks: {total_marks}
        - Question format: Open-ended/essay style (not multiple choice)
        
        {context_section}
        
        Each question should:
        - Test deeper understanding and application
        - Require thoughtful, detailed answers
        - Be appropriate for the {difficulty_level} level
        - Have clear marking criteria
        - Allocate appropriate marks based on complexity
        
        Return as JSON in this format:
        {{
          "suggested_title": "Assignment title",
          "total_marks": {total_marks},
          "questions": [
            {{
              "question": "Question text here?",
              "marks": 20,
              "guidance": "What students should focus on in their answer",
              "marking_criteria": "Key points to look for when grading"
            }}
          ]
        }}
        """
        
        response = self.client.chat.completions.create(
            model=settings.azure_openai_deployment_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6,
            max_tokens=3000
        )
        
        content_response = response.choices[0].message.content.strip()
        
        try:
            assignment_data = json.loads(content_response)
        except json.JSONDecodeError:
            import re
            json_match = re.search(r'\{.*\}', content_response, re.DOTALL)
            if json_match:
                assignment_data = json.loads(json_match.group())
            else:
                raise ValueError("Could not extract valid JSON from AI response")
        
        if not self._validate_assignment_data(assignment_data):
            raise ValueError("Generated assignment data structure is invalid")
        
        return assignment_data

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
        
        if not isinstance(question['correct_answer'], int) or not (0 <= question['correct_answer'] <= 3):
            return False
        
        if not isinstance(question['question'], str) or len(question['question'].strip()) < 10:
            return False
        
        return True
    
    def _validate_assignment_data(self, assignment_data: Dict[str, Any]) -> bool:
        """Validate that assignment data has the required structure"""
        if not isinstance(assignment_data, dict):
            return False
        
        if 'questions' not in assignment_data or not isinstance(assignment_data['questions'], list):
            return False
        
        for question in assignment_data['questions']:
            if not isinstance(question, dict):
                return False
            
            required_fields = ['question', 'marks']
            for field in required_fields:
                if field not in question:
                    return False
            
            if not isinstance(question['marks'], int) or question['marks'] <= 0:
                return False
            
            if not isinstance(question['question'], str) or len(question['question'].strip()) < 10:
                return False
        
        return True

# Create global instance
azure_client = AzureOpenAIClient()