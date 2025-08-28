from langgraph.graph import StateGraph
from app.langgraph.state import GenerationState
from app.langgraph.nodes import GenerationNodes
from app.langgraph.checkpointer import get_checkpointer
from typing import Dict, Any


class NotesGenerationWorkflow:

    
    def __init__(self):
        self.workflow = None
        self.checkpointer = get_checkpointer()
        self._build_workflow()
    
    def _build_workflow(self):
        """Build the LangGraph workflow with all nodes and edges"""
        workflow = StateGraph(GenerationState)
        
        # Add all workflow nodes
        workflow.add_node("generate", GenerationNodes.generate_content_node)
        workflow.add_node("edit", GenerationNodes.edit_content_node)
        workflow.add_node("consult", GenerationNodes.consult_ai_node)
        workflow.add_node("publish", GenerationNodes.publish_subtopic_node)
        workflow.add_node("next", GenerationNodes.next_subtopic_node)
        
        # Set entry point
        workflow.set_entry_point("generate")
        
        # Define routing logic
        def route_action(state: GenerationState) -> str:
            """Route to appropriate node based on state action"""
            action = state.action
            valid_actions = ["edit", "consult", "publish", "next", "generate"]
            
            if action in valid_actions:
                return action
            else:
                # Default to generate if action is invalid
                return "generate"
        
        # Add conditional edges for all nodes
        action_routes = {
            "edit": "edit",
            "consult": "consult", 
            "publish": "publish",
            "next": "next",
            "generate": "generate"
        }
        
        # Each node can route to any other node based on action
        for node in ["generate", "edit", "consult", "publish", "next"]:
            workflow.add_conditional_edges(
                node,
                route_action,
                action_routes
            )
        
        # Compile workflow with checkpointer
        self.workflow = workflow.compile(checkpointer=self.checkpointer)
    
    async def run_workflow(self, state: GenerationState, thread_id: str) -> GenerationState:
        """
        Execute workflow with given state and thread ID.
        
        Args:
            state: Current generation state
            thread_id: Unique thread identifier for checkpointing
            
        Returns:
            Updated generation state after workflow execution
        """
        try:
            config = {"configurable": {"thread_id": thread_id}}
            
            # Execute workflow step
            result = await self.workflow.ainvoke(state, config=config)
            
            return result
            
        except Exception as e:
            import traceback
            error_details = f"Workflow execution failed: {str(e)}\nTraceback: {traceback.format_exc()}"
            print(error_details)  # Add logging
            state.error_message = error_details
            return state
    
    async def get_workflow_state(self, thread_id: str) -> Dict[str, Any]:
        """
        Get current workflow state for a thread.
        
        Args:
            thread_id: Thread identifier
            
        Returns:
            Current state information or None if not found
        """
        try:
            config = {"configurable": {"thread_id": thread_id}}
            checkpoint = await self.checkpointer.aget_tuple(config)
            
            if checkpoint:
                return {
                    "thread_id": thread_id,
                    "checkpoint_id": checkpoint.config["configurable"].get("checkpoint_id"),
                    "state": checkpoint.checkpoint,
                    "metadata": checkpoint.metadata
                }
            return None
            
        except Exception as e:
            return {"error": f"Failed to get workflow state: {str(e)}"}
    
    async def resume_workflow(self, thread_id: str, action: str = "generate") -> GenerationState:
        """
        Resume workflow from last checkpoint.
        
        Args:
            thread_id: Thread identifier
            action: Action to perform on resume
            
        Returns:
            Updated generation state
        """
        try:
            config = {"configurable": {"thread_id": thread_id}}
            
            # Get current state
            checkpoint = await self.checkpointer.aget_tuple(config)
            if not checkpoint:
                raise ValueError(f"No checkpoint found for thread {thread_id}")
            
            # Create state from checkpoint and set new action
            state = checkpoint.checkpoint.get("state", GenerationState())
            state.action = action
            
            # Continue workflow
            result = await self.workflow.ainvoke(state, config=config)
            return result
            
        except Exception as e:
            # Create error state
            error_state = GenerationState(
                session_id=0,
                topic_id=0,
                topic_title="",
                topic_description="",
                level="",
                subtopic_titles=[],
                current_subtopic_index=0,
                total_subtopics=0,
                error_message=f"Failed to resume workflow: {str(e)}"
            )
            return error_state
    
    async def cancel_workflow(self, thread_id: str) -> bool:
        """
        Cancel a workflow and clean up its checkpoints.
        
        Args:
            thread_id: Thread identifier
            
        Returns:
            True if successfully cancelled, False otherwise
        """
        try:
            return await self.checkpointer.delete_thread(thread_id)
        except Exception:
            return False
    
    def get_workflow_info(self) -> Dict[str, Any]:
        """Get information about the workflow configuration"""
        return {
            "checkpointer_type": type(self.checkpointer).__name__,
            "checkpointer_info": self.checkpointer.get_connection_info(),
            "workflow_compiled": self.workflow is not None,
            "available_nodes": ["generate", "edit", "consult", "publish", "next"],
            "entry_point": "generate"
        }


# Create global workflow instance
notes_workflow = NotesGenerationWorkflow()