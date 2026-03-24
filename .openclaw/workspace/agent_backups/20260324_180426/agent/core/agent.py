"""
Main agent class that orchestrates all components.
Integrates planner, executor, memory, and communicator.
"""

# Import standard libraries
import json
import os
from datetime import datetime
from typing import Dict, Any, Optional

class Agent:
    """Main agent class that coordinates all components."""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the agent with all components.
        
        Args:
            config_path (str, optional): Path to configuration file
        """
        # Initialize components
        self.memory_system = None
        self.planner = None
        self.executor = None
        self.communicator = None
        
        # Current state
        self.current_task = None
        self.current_plan = None
        self.is_running = False
        
        # Initialize the agent
        self._initialize(config_path)
    
    def _initialize(self, config_path: Optional[str] = None):
        """
        Initialize all agent components.
        
        Args:
            config_path (str, optional): Path to configuration file
        """
        # Load configuration
        config = self._load_configuration(config_path)
        
        # Initialize memory system first (needed by other components)
        memory_path = config.get('memory', {}).get('storage_path', 'MEMORY.md')
        self.memory_system = MemorySystem(memory_path)
        
        # Update memory with initialization
        self.memory_system.store_memory(
            'system_configuration',
            'initialized',
            True,
            {'timestamp': self._get_timestamp()}
        )
        
        # Initialize other components
        self.planner = Planner(self.memory_system)
        self.executor = Executor(self._get_tool_registry(), self.memory_system)
        self.communicator = Communicator(self.memory_system, config.get('personality'))
        
        # Update development roadmap status
        self.memory_system.update_roadmap_status('Implement memory system', 'completed')
        self.memory_system.update_roadmap_status('Create configuration structure', 'completed')
        self.memory_system.update_roadmap_status('Develop planning framework', 'in_progress')
        
        # Log initialization
        print("Agent initialization completed.")
        print(f"Memory system: {memory_path}")
        print(f"Components initialized: Planner, Executor, Communicator")
    
    def _load_configuration(self, config_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Load agent configuration.
        
        Args:
            config_path (str, optional): Path to configuration file
            
        Returns:
            dict: Configuration data
        """
        default_config = {
            'memory': {
                'storage_path': 'MEMORY.md'
            },
            'personality': {
                'tone': 'professional',
                'formality': 'medium',
                'verbosity': 'concise',
                'style': 'direct'
            },
            'planning': {
                'default_priority': 'medium',
                'max_steps': 50
            },
            'execution': {
                'max_retries': 3,
                'timeout_seconds': 300
            }
        }
        
        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
                # Merge with default config
                for key, value in default_config.items():
                    if key not in config:
                        config[key] = value
                return config
            except Exception as e:
                print(f"Error loading config from {config_path}: {e}")
                return default_config
        else:
            return default_config
    
    def _get_tool_registry(self) -> Dict[str, Any]:
        """
        Create registry of available tools.
        
        Returns:
            dict: Mapping of tool names to callable functions
        """
        # In a real implementation, this would register actual tools
        # For now, returning placeholder tools
        return {
            'read': self._placeholder_tool,
            'write': self._placeholder_tool,
            'exec': self._placeholder_tool,
            'web_search': self._placeholder_tool,
            'memory_search': self._placeholder_tool,
            'default': self._placeholder_tool
        }
    
    def _placeholder_tool(self, **kwargs) -> Dict[str, Any]:
        """
        Placeholder tool that simulates tool execution.
        
        Args:
            **kwargs: Tool arguments
            
        Returns:
            dict: Simulated tool result
        """
        return {
            'success': True,
            'output': f"Executed placeholder tool with args: {kwargs}"
        }
    
    def start_task(self, task_description: str) -> Dict[str, Any]:
        """
        Start processing a new task.
        
        Args:
            task_description (str): Description of the task to perform
            
        Returns:
            dict: Initial response with plan information
        """
        # Store task in memory
        self.current_task = task_description
        self.memory_system.store_memory(
            'task_history',
            'current_task',
            task_description,
            {'start_time': self._get_timestamp()}
        )
        
        # Create plan
        self.current_plan = self.planner.create_plan(task_description)
        
        # Validate plan
        validation = self.planner.validate_plan()
        if not validation['valid']:
            error_response = {
                'success': False,
                'error': 'plan_validation_failed',
                'messages': validation['messages']
            }
            return error_response
        
        # Get plan summary
        plan_summary = self.planner.get_plan_summary()
        
        # Format response
        response = {
            'success': True,
            'task': task_description,
            'plan': plan_summary,
            'status': 'planning_complete',
            'next_steps': self.planner.get_next_steps()
        }
        
        # Log the interaction
        self.communicator.log_interaction(
            task_description,
            f"Created plan for task: {task_description}",
            {'plan_steps': len(self.current_plan['steps'])}
        )
        
        return response
    
    def execute_task(self) -> Dict[str, Any]:
        """
        Execute the current plan step by step.
        
        Returns:
            dict: Final execution results
        """
        if not self.current_plan:
            return {
                'success': False,
                'error': 'no_current_plan',
                'message': 'No plan available to execute. Call start_task first.'
            }

        # Update plan status
        self.is_running = True
        results = {
            'task': self.current_plan['original_task'],
            'status': 'in_progress',
            'step_results': [],
            'final_output': None,
            'metrics': {
                'steps_completed': 0,
                'steps_failed': 0,
                'total_duration': 0
            }
        }

        start_time = datetime.now()

        try:
            # Execute steps in order
            while self.is_running:
                # Get next steps that can be executed
                ready_steps = self.planner.get_next_steps()
                
                if not ready_steps:
                    # No more steps ready for execution
                    break
                
                # Execute each ready step
                for step in ready_steps:
                    # Update communicator with current context
                    self.communicator.receive_message(
                        f"Executing step {step['order']}: {step['description']}",
                        {'role': 'system'}
                    )
                    
                    # Execute the step
                    step_result = self.executor.execute_step(step)
                    
                    # Record result
                    results['step_results'].append({
                        'step': step,
                        'result': step_result,
                        'timestamp': self._get_timestamp()
                    })
                    
                    # Update plan with execution status
                    status = 'completed' if step_result['success'] else 'failed'
                    self.planner.update_plan_status(
                        step['id'], 
                        status,
                        tool_results=step_result.get('tool_results', []),
                        output=step_result.get('output')
                    )
                    
                    # Update metrics
                    if step_result['success']:
                        results['metrics']['steps_completed'] += 1
                    else:
                        results['metrics']['steps_failed'] += 1
                        
                    # Check if we should continue on failure
                    if not step_result['success']:
                        # For now, continue with other steps
                        # In practice, this might depend on the error type
                        pass

            # Task completed
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            results['metrics']['total_duration'] = duration

            # Update final status
            plan_summary = self.planner.get_plan_summary()
            results['status'] = plan_summary['status']
            
            # Generate final output
            results['final_output'] = self._generate_final_output(results)

            # Update development roadmap if this was a development task
            self._update_roadmap_progress(self.current_task, results)

        except Exception as e:
            # Handle unexpected errors
            results['success'] = False
            results['error'] = 'execution_error'
            results['error_message'] = str(e)
            self.is_running = False

        finally:
            self.is_running = False

        return results
    
    def _generate_final_output(self, execution_results: Dict[str, Any]) -> str:
        """
        Generate final output from execution results.
        
        Args:
            execution_results (dict): Results from task execution
            
        Returns:
            str: Formatted final output
        """
        task = execution_results['task']
        status = execution_results['status']
        metrics = execution_results['metrics']
        
        # Create summary
        summary_lines = [
            f"Task: {task}",
            f"Status: {status}",
            f"Completed: {metrics['steps_completed']} steps",
            f"Failed: {metrics['steps_failed']} steps",
            f"Duration: {metrics['total_duration']:.2f} seconds"
        ]
        
        # Add details about results
        if execution_results['step_results']:
            summary_lines.append("")
            summary_lines.append("## Step Results")
            
            for result in execution_results['step_results']:
                step = result['step']
                step_result = result['result']
                status_emoji = "✅" if step_result['success'] else "❌"
                summary_lines.append(f"{status_emoji} Step {step['order']}: {step['description']}")
                
                # Add output if available
                if step_result.get('output'):
                    output = step_result['output']
                    if isinstance(output, str):
                        summary_lines.append(f"   Output: {output}")
                    elif isinstance(output, dict) and 'content' in output:
                        summary_lines.append(f"   Output: {output['content']}")
        
        return "\n".join(summary_lines)
    
    def _update_roadmap_progress(self, task: str, results: Dict[str, Any]):
        """
        Update development roadmap based on task completion.
        
        Args:
            task (str): Completed task description
            results (dict): Task execution results
        """
        # Check if this was a development task
        dev_tasks = [
            'implement memory system',
            'create configuration structure',
            'develop planning framework',
            'test with simple tasks'
        ]
        
        for dev_task in dev_tasks:
            if dev_task in task.lower() and results['status'] == 'completed':
                # Extract the specific development task from the roadmap
                roadmap = self.memory_system.retrieve_memory('development_roadmap')
                for item in roadmap:
                    if dev_task in item['description'].lower():
                        self.memory_system.update_roadmap_status(
                            item['description'], 
                            'completed'
                        )
                        break
                
                # Move to next task if available
                current_index = dev_tasks.index(dev_task)
                if current_index + 1 < len(dev_tasks):
                    next_task = dev_tasks[current_index + 1]
                    self.memory_system.update_roadmap_status(next_task, 'in_progress')
                
                break
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get current agent status.
        
        Returns:
            dict: Comprehensive status information
        """
        memory_status = self.memory_system.get_status_report()
        
        status = {
            'agent': {
                'is_running': self.is_running,
                'current_task': self.current_task,
                'current_plan_status': self.planner.get_plan_summary() if self.current_plan else None,
                'active_executions': len(self.executor.active_executions) if self.executor else 0
            },
            'memory': memory_status,
            'planning': {
                'current_plan_valid': self.planner.validate_plan() if self.current_plan else None
            },
            'execution': {
                'total_executions': len(self.executor.execution_history) if self.executor else 0,
                'success_rate': self.executor._calculate_success_rate() if self.executor else 0
            },
            'system': {
                'timestamp': self._get_timestamp()
            }
        }
        
        return status
    
    def _get_timestamp(self) -> str:
        """
        Get current timestamp.
        
        Returns:
            str: ISO format timestamp
        """
        return datetime.now().isoformat()

# Import components to make them available when agent is imported
from agent.core.planner import Planner
from agent.core.executor import Executor
from agent.core.memory import MemorySystem
from agent.core.communicator import Communicator