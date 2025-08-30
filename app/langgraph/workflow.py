from langgraph.graph import StateGraph, END
from app.langgraph.state import GenerationState
from app.langgraph.nodes import GenerationNodes
from app.langgraph.checkpointer import get_postgres_checkpointer  
import traceback
import logging
import asyncio

logger = logging.getLogger(__name__)

class NotesGenerationWorkflow:
    def __init__(self):
        self.workflow = None
        self.checkpointer = None
        self._compiled_workflow = None
        self._build_workflow()
    
    async def _get_or_create_checkpointer(self):
        """Get checkpointer with connection health management"""
        try:
            self.checkpointer = await get_postgres_checkpointer()
            return self.checkpointer
        except Exception as e:
            logger.error(f"Failed to get checkpointer: {e}")
            raise Exception(f"Database connection failed: {str(e)}")
    
    def _build_workflow(self):
        """Build the LangGraph workflow with dynamic entry point"""
        workflow = StateGraph(GenerationState)
        
        # Add nodes
        workflow.add_node("generate", GenerationNodes.generate_content_node)
        workflow.add_node("edit", GenerationNodes.edit_content_node)
        workflow.add_node("consult", GenerationNodes.consult_ai_node)
        workflow.add_node("publish", GenerationNodes.publish_subtopic_node)
        workflow.add_node("next", GenerationNodes.next_subtopic_node)
        
        # Add a router node as entry point
        workflow.add_node("router", self._router_node)
        
        # Set router as entry point
        workflow.set_entry_point("router")
        
        def route_action(state: GenerationState):
            """Enhanced routing with proper termination logic and debugging"""
            action = getattr(state, 'action', None)
            
            print(f"🚦 DEBUG: [ROUTING] Entry point - action: '{action}'")
            print(f"🚦 DEBUG: [ROUTING] Current subtopic: {getattr(state, 'current_subtopic_index', 'None')}/{getattr(state, 'total_subtopics', 'None')}")
            
            # Check for completion first
            if (hasattr(state, 'current_subtopic_index') and 
                hasattr(state, 'total_subtopics') and
                state.current_subtopic_index >= state.total_subtopics):
                print("🚦 DEBUG: [ROUTING] All subtopics completed, ending workflow")
                return END
            
            # Route based on action
            if action == "generate":
                print("🚦 DEBUG: [ROUTING] Routing to 'generate'")
                return "generate"
            elif action == "edit":
                print("🚦 DEBUG: [ROUTING] Routing to 'edit'")
                return "edit"
            elif action == "consult":
                print("🚦 DEBUG: [ROUTING] Routing to 'consult' ⭐")
                return "consult"
            elif action == "publish":
                print("🚦 DEBUG: [ROUTING] Routing to 'publish'")
                return "publish"
            elif action == "next":
                print("🚦 DEBUG: [ROUTING] Routing to 'next'")
                return "next"
            elif action == "complete" or action is None:
                print("🚦 DEBUG: [ROUTING] Ending workflow")
                return END
            else:
                print(f"🚦 DEBUG: [ROUTING] Unknown action '{action}', ending workflow")
                return END
        
        # All destinations for routing
        all_destinations = {
            "edit": "edit",
            "consult": "consult", 
            "publish": "publish",
            "next": "next",
            "generate": "generate",
            END: END
        }
        
        # Router routes to appropriate action
        workflow.add_conditional_edges("router", route_action, all_destinations)
        
        # Each node can only end the workflow (since they set action=None)
        for node_name in ["generate", "edit", "consult", "publish", "next"]:
            workflow.add_edge(node_name, END)
        
        self._workflow_graph = workflow
        print("🔧 DEBUG: Workflow built with router entry point")

    @staticmethod
    async def _router_node(state: GenerationState) -> GenerationState:
        """Router node that preserves the action for routing"""
        print(f"🎯 DEBUG: [ROUTER] Received action: '{state.action}'")
        # Don't modify the state, just pass it through for routing
        return state
    async def _compile_workflow_if_needed(self):
        """Compile workflow with fresh checkpointer if needed"""
        try:
            checkpointer = await self._get_or_create_checkpointer()
            
            if self._compiled_workflow is None:
                logger.info("Compiling workflow with checkpointer...")
                self._compiled_workflow = self._workflow_graph.compile(checkpointer=checkpointer)
                logger.info("Workflow compiled successfully")
            
            return self._compiled_workflow
            
        except Exception as e:
            logger.error(f"Failed to compile workflow: {e}")
            self._compiled_workflow = None
            raise

    async def run_workflow(self, state: GenerationState, thread_id: str):
        """Execute workflow with proper recursion handling and debugging"""
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                compiled_workflow = await self._compile_workflow_if_needed()
                
                config = {
                    "configurable": {"thread_id": thread_id},
                    "recursion_limit": 50,
                }
                                
                print(f"🔄 DEBUG: [WORKFLOW] Starting execution with initial action: '{state.action}'")
                print(f"🔄 DEBUG: [WORKFLOW] Thread ID: {thread_id}")
                
                logger.info(f"[WORKFLOW] Executing workflow for thread {thread_id}, attempt {retry_count + 1}")
                logger.info(f"[WORKFLOW] Initial state action: '{state.action}'")
                logger.info(f"[WORKFLOW] Current subtopic: {state.current_subtopic_index}/{state.total_subtopics}")
                
                result = await compiled_workflow.ainvoke(state.dict(), config=config)
                
                logger.info(f"[WORKFLOW] Completed successfully for thread {thread_id}")
                logger.info(f"[WORKFLOW] Final action: '{result.get('action', 'None')}'")
                                
                print(f"🏁 DEBUG: [WORKFLOW] Execution completed")
                print(f"🏁 DEBUG: [WORKFLOW] Final result keys: {list(result.keys()) if isinstance(result, dict) else 'Not a dict'}")
                return GenerationState(**result)
                
            except Exception as e:
                retry_count += 1
                error_msg = str(e)
                
                logger.error(f"[WORKFLOW] Error on attempt {retry_count}: {error_msg}")
                full_traceback = traceback.format_exc()
                logger.error(f"[WORKFLOW] Full traceback:\n{full_traceback}")
                
                # Handle KeyError specifically - this indicates routing issues
                if "KeyError:" in error_msg:
                    missing_key = error_msg.split("KeyError: ")[-1].strip("'\"")
                    logger.error(f"[WORKFLOW] Missing routing destination: '{missing_key}'")
                    logger.error("[WORKFLOW] This indicates a node is trying to route to a destination not defined in its conditional_edges")
                    
                    # Don't retry KeyError - it's a configuration issue
                    raise Exception(
                        f"Workflow configuration error: Node is trying to route to '{missing_key}' "
                        f"but this destination is not defined in the conditional edges. "
                        f"Check your GenerationNodes to ensure they set valid action values."
                    )
                
                # Handle recursion errors
                if "recursion limit" in error_msg.lower():
                    logger.error("[WORKFLOW] Infinite loop detected")
                    raise Exception(
                        f"Workflow infinite loop. Check that your nodes properly update the 'action' field. "
                        f"Current state: {state.dict()}"
                    )
                
                # Handle connection errors
                connection_errors = [
                    "connection is closed", "connection was closed", 
                    "database connection", "connection timeout", "connection refused"
                ]
                
                if any(conn_error in error_msg.lower() for conn_error in connection_errors):
                    if retry_count < max_retries:
                        self._compiled_workflow = None
                        self.checkpointer = None
                        logger.info(f"[WORKFLOW] Retrying after connection error (attempt {retry_count + 1}/{max_retries})")
                        await asyncio.sleep(2 ** retry_count)
                        continue
                    else:
                        raise Exception(f"Database connection failed after {max_retries} attempts: {error_msg}")
                else:
                    # Other errors, don't retry
                    raise Exception(f"Workflow execution failed: {error_msg}")
                                

        raise Exception("Workflow execution failed after all retry attempts")

    async def start_generation(self, state: GenerationState, thread_id: str):
        """Start initial generation with proper action management"""
        initial_state = state.dict()
        initial_state['action'] = 'generate'
        
        logger.info("[START] Starting initial generation workflow")
        return await self.run_workflow(GenerationState(**initial_state), thread_id)

    async def continue_with_action(self, thread_id: str, action: str, **kwargs):
        """Continue workflow with specific action"""
        try:
            compiled_workflow = await self._compile_workflow_if_needed()
            config = {"configurable": {"thread_id": thread_id}}
            
            # Get current state
            current_state = compiled_workflow.get_state(config)
            if not current_state or not current_state.values:
                raise Exception("No workflow state found for thread")
            
            # Update state with new action
            updated_values = current_state.values.copy()
            updated_values['action'] = action
            
            # Add any additional data
            for key, value in kwargs.items():
                updated_values[key] = value
            
            logger.info(f"[CONTINUE] Continuing workflow with action: '{action}'")
            result = await compiled_workflow.ainvoke(updated_values, config=config)
            
            return GenerationState(**result)
            
        except Exception as e:
            logger.error(f"[CONTINUE] Failed to continue workflow: {e}")
            raise

# Create global workflow instance
notes_workflow = NotesGenerationWorkflow()

# Debug helper
def debug_node_action(node_name, input_action, output_action):
    """Helper to debug node transitions"""
    logger.info(f"[NODE-{node_name.upper()}] Input action: '{input_action}' -> Output action: '{output_action}'")