from openai import AzureOpenAI
from app.config import settings
from typing import List, Dict, Any

class AzureOpenAIClient:
    def __init__(self):
        self.client = AzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version
        )
    
    async def generate_subtopic_plan(self, topic_description: str, level: str, num_subtopics: int = None) -> List[str]:
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
                                                   upcoming_concepts: List[str] = None) -> str:
        """
        Generate high-quality educational content using vector-retrieved context.
        This is our main content generation method with the integrated prompting approach.
        """
        
        # System prompt - Educational framework & teaching philosophy
        system_content = f"""You are a master educator creating a comprehensive course on "{topic_title}" for {level} learners.

Your expertise:
- Progressive concept building that flows naturally
- Rich, memorable examples and applications  
- Conceptual clarity without oversimplification
- Consistent terminology throughout the course

Your teaching philosophy:
- Each concept builds naturally on established understanding
- Use precise, consistent terminology 
- Provide concrete examples before abstract concepts
- Connect new ideas to previously covered foundations
- Maintain student engagement through relevant applications"""

        # Context injection + Generation prompt combined
        upcoming_text = f"\nUpcoming concepts in this course: {', '.join(upcoming_concepts)}" if upcoming_concepts else ""
        
        user_content = f"""{formatted_context}

{upcoming_text}

CREATE COMPREHENSIVE EDUCATIONAL CONTENT FOR: {subtopic_title}

Content requirements:
- 700-900 words of substantive, engaging material
- Begin by naturally connecting to relevant previous concepts (don't force it)
- Introduce new concepts with clear, memorable definitions
- Include concrete, relatable examples that illustrate the concepts
- Show practical applications where appropriate
- Use consistent terminology established in previous lessons
- Maintain logical flow that prepares students for upcoming concepts

Structure your response with clear headings and smooth transitions between ideas."""

        # Combined messages for integrated prompt approach
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content}
        ]
        
        response = self.client.chat.completions.create(
            model=settings.azure_openai_deployment_name,
            messages=messages,
            temperature=0.6,  # Balanced creativity and consistency
            max_tokens=1200   # Ensure we get full, comprehensive content
        )
        
        return response.choices[0].message.content

    async def consult_in_conversation(self, messages: List[Dict[str, str]], 
                                    improvement_request: str) -> Dict[str, Any]:
        """Get AI consultation within conversation context"""
        
        user_prompt = f"""Please review the content we just generated and provide specific improvement suggestions based on this request: {improvement_request}

    Provide:
    1. General suggestions for improvement
    2. Specific recommended changes (as a list)

    Format your response as JSON with keys: "suggestions" and "recommended_changes\""""
        
        conversation_messages = messages + [{"role": "user", "content": user_prompt}]
        
        try:
            response = self.client.chat.completions.create(
                model=settings.azure_openai_deployment_name,
                messages=conversation_messages,
                temperature=0.5,
                max_tokens=800
            )
            
            raw_content = response.choices[0].message.content
            
            import json
            try:
                parsed_response = json.loads(raw_content)
                return parsed_response
            except json.JSONDecodeError:
                return {
                    "suggestions": raw_content,
                    "recommended_changes": ["Review the suggestions above"]
                }
        except Exception as api_error:
            return {
                "suggestions": f"Error: {str(api_error)}",
                "recommended_changes": []
            }

azure_client = AzureOpenAIClient()