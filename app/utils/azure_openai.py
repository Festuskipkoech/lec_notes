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
                                    previous_subtopics_content: List[str] = None, 
                                    upcoming_concepts: List[str] = None) -> str:
        # Extract key concepts from previous subtopics
        must_reference_concepts = []
        if previous_subtopics_content:
            must_reference_concepts = self._extract_key_concepts_from_content(previous_subtopics_content)
        
        # Build coherence requirements
        coherence_requirements = self._build_coherence_requirements(
            previous_subtopics_content, must_reference_concepts, upcoming_concepts
        )
        
        prompt = f"""
    Generate comprehensive educational content for:
    Topic: {topic_title}
    Subtopic: {subtopic_title}
    Education Level: {level}

    {coherence_requirements}

    MANDATORY STRUCTURE:
    1. **Building on Previous Learning** (if this is not the first subtopic)
    - Reference at least 2 specific concepts from earlier subtopics using EXACT terminology
    - Begin with: "Building on our exploration of [specific previous concept]..."

    2. **Core Content for {subtopic_title}**
    - Detailed, engaging content appropriate for {level}
    - Include examples and explanations
    - Use consistent terminology established in previous subtopics

    3. **Connections and Applications**
    - Show explicit connections to previously covered material
    - Use phrases like "As we learned when discussing..." or "This builds directly on the concept of..."

    4. **Preparing for Future Learning**
    - End with: "This foundation prepares us for understanding [next concept]..."
    - Set up concepts for upcoming subtopics

    Length: 600-900 words
    """
        
        response = self.client.chat.completions.create(
            model=settings.azure_openai_deployment_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6  # Slightly lower temperature for more consistency
        )
        
        generated_content = response.choices[0].message.content
        
        # Second pass for coherence enhancement if we have previous content
        if previous_subtopics_content:
            enhanced_content = await self._enhance_coherence(
                generated_content, previous_subtopics_content, must_reference_concepts
            )
            return enhanced_content
        
        return generated_content

    # ADD these new helper methods:
    def _extract_key_concepts_from_content(self, previous_contents: List[str]) -> List[str]:
        """Extract key concepts that should be referenced"""
        if not previous_contents:
            return []
        
        # Take the most recent 2 subtopics for concept extraction
        recent_content = "\n\n".join(previous_contents[-2:])
        
        extraction_prompt = f"""
    Analyze this educational content and extract the 5-8 most important concepts, terms, or ideas that future subtopics should reference:

    {recent_content[:2000]}  # Limit content to avoid token issues

    Return ONLY a comma-separated list of key concepts/terms. No explanations.
    Example: graph theory, nodes, edges, centrality measures, PageRank
    """
        
        response = self.client.chat.completions.create(
            model=settings.azure_openai_deployment_name,
            messages=[{"role": "user", "content": extraction_prompt}],
            temperature=0.3,
            max_tokens=150
        )
        
        concepts_text = response.choices[0].message.content.strip()
        concepts = [concept.strip() for concept in concepts_text.split(",") if concept.strip()]
        return concepts[:8]  # Limit to top 8 concepts

    def _build_coherence_requirements(self, previous_contents: List[str], 
                                    must_reference_concepts: List[str], 
                                    upcoming_concepts: List[str]) -> str:
        """Build specific coherence requirements for the prompt"""
        if not previous_contents:
            return "This is the first subtopic, so focus on establishing foundational concepts clearly."
        
        requirements = f"""
    COHERENCE REQUIREMENTS - THESE ARE MANDATORY:
    1. You MUST reference at least 2 of these concepts from previous subtopics: {', '.join(must_reference_concepts[:6])}
    2. You MUST use the EXACT terminology from previous content (not synonyms)
    3. You MUST start the main content with a connection to previous learning
    4. You MUST include specific examples that build on earlier material

    Previous context summary:
    {self._summarize_previous_content(previous_contents)}
    """
        
        if upcoming_concepts:
            requirements += f"\n5. Prepare foundation for these upcoming concepts: {', '.join(upcoming_concepts)}"
        
        return requirements

    def _summarize_previous_content(self, previous_contents: List[str]) -> str:
        """Create a brief summary of previous content for context"""
        if not previous_contents:
            return ""
        
        # Take key points from recent subtopics
        recent_content = "\n\n".join(previous_contents[-2:])[:1500]  # Limit length
        
        return f"Key points from recent subtopics:\n{recent_content}"

    async def _enhance_coherence(self, generated_content: str, previous_contents: List[str], 
                            key_concepts: List[str]) -> str:
        """Second pass to enhance coherence and connections"""
        
        enhancement_prompt = f"""
    Review and enhance this educational content to strengthen connections to previous learning:

    GENERATED CONTENT:
    {generated_content}

    KEY CONCEPTS FROM PREVIOUS SUBTOPICS THAT SHOULD BE REFERENCED:
    {', '.join(key_concepts)}

    ENHANCEMENT REQUIREMENTS:
    1. Add more specific references to previous concepts using exact terminology
    2. Strengthen the connections between new content and what came before
    3. Add phrases like "As we learned when discussing...", "Building on the concept of...", "This extends our understanding of..."
    4. Ensure terminology consistency
    5. Make the educational progression more explicit

    Return the enhanced version that creates stronger coherence with previous learning.
    """
        
        response = self.client.chat.completions.create(
            model=settings.azure_openai_deployment_name,
            messages=[{"role": "user", "content": enhancement_prompt}],
            temperature=0.4,
            max_tokens=1200
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