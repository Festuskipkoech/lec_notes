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
    
    async def generate_subtopic_content(self, topic_title: str, subtopic_title: str, level: str, 
                                      previous_concepts: List[str] = None, upcoming_concepts: List[str] = None) -> str:
        context = ""
        if previous_concepts:
            context += f"Previously covered concepts: {', '.join(previous_concepts)}\n"
        if upcoming_concepts:
            context += f"Upcoming concepts: {', '.join(upcoming_concepts)}\n"
        
        prompt = f"""
        Generate comprehensive educational notes for:
        Topic: {topic_title}
        Subtopic: {subtopic_title}
        Education Level: {level}
        
        {context}
        
        Requirements:
        - Create detailed, engaging content appropriate for {level}
        - Include examples and explanations
        - Build on previous concepts if mentioned
        - Prepare for upcoming concepts if mentioned
        - Use clear structure with headings and bullet points
        - Length: 500-800 words
        """
        
        response = self.client.chat.completions.create(
            model=settings.azure_openai_deployment_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        
        return response.choices[0].message.content
    

    async def suggest_improvements(self, content: str, improvement_request: str) -> Dict[str, Any]:
        print(f"🔮 DEBUG: [AZURE] suggest_improvements called")
        print(f"🔮 DEBUG: [AZURE] Content length: {len(content)}")
        print(f"🔮 DEBUG: [AZURE] Improvement request: '{improvement_request}'")
        
        prompt = f"""
        Review this educational content and provide specific improvement suggestions:
        
        Content: {content}
        
        Specific improvement request: {improvement_request}
        
        Provide:
        1. General suggestions for improvement
        2. Specific recommended changes (as a list)
        
        Format your response as JSON with keys: "suggestions" and "recommended_changes"
        """
        
        try:
            print(f"🔮 DEBUG: [AZURE] Making OpenAI API call...")
            
            response = self.client.chat.completions.create(
                model=settings.azure_openai_deployment_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5
            )
            
            raw_content = response.choices[0].message.content
            print(f"🔮 DEBUG: [AZURE] Raw API response: {raw_content}")
            
            import json
            try:
                parsed_response = json.loads(raw_content)
                print(f"🔮 DEBUG: [AZURE] Successfully parsed JSON: {parsed_response}")
                return parsed_response
            except json.JSONDecodeError as json_error:
                print(f"🔮 DEBUG: [AZURE] JSON parsing failed: {json_error}")
                print(f"🔮 DEBUG: [AZURE] Falling back to string response")
                return {
                    "suggestions": raw_content,
                    "recommended_changes": ["Review the suggestions above"]
                }
        except Exception as api_error:
            print(f"💥 DEBUG: [AZURE] API call failed: {api_error}")
            return {
                "suggestions": f"Error: {str(api_error)}",
                "recommended_changes": []
            }

azure_client = AzureOpenAIClient()