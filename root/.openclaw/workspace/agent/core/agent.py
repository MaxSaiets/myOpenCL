"""
Main agent class that orchestrates all components.
Integrates LLM client, model router, planner, executor, memory, validator, and communicator.
"""

import json
import os
import logging
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class Agent:
    """Main agent class that coordinates all components with LLM-powered intelligence."""

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the agent with all components.

        Args:
            config_path: Path to configuration JSON file.
        """
        self.memory_system = None
        self.planner = None
        self.executor = None
        self.communicator = None
        self.llm_client = None
        self.model_router = None
        self.validator = None

        self.current_task = None
        self.current_plan = None
        self.is_running = False

        self._initialize(config_path)

    def _initialize(self, config_path: Optional[str] = None):
        """Initialize all agent components in dependency order."""
        config = self._load_configuration(config_path)

        # 1. LLM Client (foundation — everything depends on this)
        from agent.core.llm_client import LLMClient
        self.llm_client = LLMClient()

        # 2. Model Router (depends on LLM client)
        from agent.core.model_router import ModelRouter
        self.model_router = ModelRouter(self.llm_client)

        # 3. Memory System (depends on LLM client for embeddings)
        from agent.core.memory import MemorySystem
        memory_path = config.get('memory', {}).get('storage_path', 'MEMORY.md')
        self.memory_system = MemorySystem(memory_path, llm_client=self.llm_client)

        # 4. Planner (depends on memory + model router)
        from agent.core.planner import Planner
        self.planner = Planner(self.memory_system, model_router=self.model_router)

        # 5. Executor (depends on tools + memory + model router)
        from agent.tools import get_tool_registry
        tool_registry = get_tool_registry(memory_system=self.memory_system)
        from agent.core.executor import Executor
        self.executor = Executor(tool_registry, self.memory_system, model_router=self.model_router)

        # 6. Validator (depends on model router + memory store)
        from agent.core.validator import TaskValidator
        self.validator = TaskValidator(
            model_router=self.model_router,
            memory_store=self.memory_system.store,
        )

        # 7. Communicator (depends on memory)
        from agent.core.communicator import Communicator
        self.communicator = Communicator(self.memory_system, config.get('personality'))

        # Log initialization
        logger.info("Agent initialized with LLM client, model router, validator")
        self.memory_system.store_memory(
            'system_configuration', 'initialized', True,
            {'timestamp': datetime.now().isoformat()},
        )

    def _load_configuration(self, config_path: Optional[str] = None) -> Dict[str, Any]:
        """Load agent configuration."""
        default_config = {
            'memory': {'storage_path': 'MEMORY.md'},
            'personality': {
                'tone': 'professional',
                'formality': 'medium',
                'verbosity': 'concise',
                'style': 'direct',
            },
            'planning': {'default_priority': 'medium', 'max_steps': 50},
            'execution': {'max_retries': 3, 'timeout_seconds': 300},
        }

        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
                for key, value in default_config.items():
                    config.setdefault(key, value)
                return config
            except Exception as e:
                logger.warning(f"Error loading config: {e}")
                return default_config
        return default_config

    def start_task(self, task_description: str) -> Dict[str, Any]:
        """
        Start processing a new task.

        Args:
            task_description: Natural language task description.

        Returns:
            Response dict with plan information.
        """
        self.current_task = task_description
        self.memory_system.store_memory(
            'task_history', 'current_task', task_description,
            {'start_time': datetime.now().isoformat()},
        )

        # Create LLM-powered plan
        self.current_plan = self.planner.create_plan(task_description)

        # Validate plan
        validation = self.planner.validate_plan()
        if not validation['valid']:
            return {
                'success': False,
                'error': 'plan_validation_failed',
                'messages': validation['messages'],
            }

        summary = self.planner.get_plan_summary()
        response = {
            'success': True,
            'task': task_description,
            'plan': summary,
            'status': 'planning_complete',
            'next_steps': self.planner.get_next_steps(),
        }

        self.communicator.log_interaction(
            task_description,
            f"Created plan: {len(self.current_plan['steps'])} steps",
            {'plan_steps': len(self.current_plan['steps'])},
        )

        return response

    def execute_task(self) -> Dict[str, Any]:
        """
        Execute the current plan with reflection and replanning.

        Returns:
            Final execution results with validation.
        """
        if not self.current_plan:
            return {
                'success': False,
                'error': 'no_current_plan',
                'message': 'No plan available. Call start_task first.',
            }

        self.is_running = True
        results = {
            'task': self.current_plan['original_task'],
            'status': 'in_progress',
            'step_results': [],
            'final_output': None,
            'validation': None,
            'metrics': {'steps_completed': 0, 'steps_failed': 0, 'total_duration': 0, 'replans': 0},
        }

        start_time = datetime.now()
        max_retries_per_step = 3

        try:
            while self.is_running:
                ready_steps = self.planner.get_next_steps()
                if not ready_steps:
                    break

                for step in ready_steps:
                    self.communicator.receive_message(
                        f"Executing step {step['order']}: {step['description']}",
                        {'role': 'system'},
                    )

                    # Execute with retry and reflection
                    step_result = self._execute_with_reflection(step, max_retries_per_step)

                    results['step_results'].append({
                        'step': step,
                        'result': step_result,
                        'timestamp': datetime.now().isoformat(),
                    })

                    status = 'completed' if step_result['success'] else 'failed'
                    self.planner.update_plan_status(
                        step['id'], status,
                        tool_results=step_result.get('tool_results', []),
                        output=step_result.get('output'),
                    )

                    if step_result['success']:
                        results['metrics']['steps_completed'] += 1
                    else:
                        results['metrics']['steps_failed'] += 1
                        # Check reflection for replan
                        reflection = step_result.get('reflection', {})
                        if reflection.get('action') == 'replan':
                            completed = [s for s in self.current_plan['steps'] if s['status'] == 'completed']
                            error_ctx = step_result.get('error_message', str(step_result.get('output', '')))
                            self.planner.replan(completed, step, error_ctx)
                            results['metrics']['replans'] += 1
                            break  # Re-enter the while loop to get new steps

            # Compute final results
            end_time = datetime.now()
            results['metrics']['total_duration'] = (end_time - start_time).total_seconds()

            plan_summary = self.planner.get_plan_summary()
            results['status'] = plan_summary['status'] if plan_summary else 'unknown'
            results['final_output'] = self._generate_final_output(results)

            # Validate completion
            results['validation'] = self.validator.validate_completion(
                task_description=self.current_plan['original_task'],
                plan=self.current_plan,
                execution_results=results,
            )

        except Exception as e:
            results['success'] = False
            results['error'] = 'execution_error'
            results['error_message'] = str(e)
            logger.error(f"Task execution error: {e}", exc_info=True)
        finally:
            self.is_running = False

        return results

    def _execute_with_reflection(self, step: dict, max_retries: int) -> dict:
        """Execute a step with retry based on reflection."""
        for attempt in range(1, max_retries + 1):
            result = self.executor.execute_step(step)
            reflection = result.get('reflection', {})

            if result['success'] or reflection.get('action') != 'retry':
                return result

            if attempt < max_retries:
                logger.info(f"Retrying step {step['id']} (attempt {attempt + 1}/{max_retries})")

        return result  # Return last attempt result

    def _generate_final_output(self, execution_results: Dict[str, Any]) -> str:
        """Generate formatted final output."""
        task = execution_results.get('task', '')
        status = execution_results.get('status', '')
        metrics = execution_results.get('metrics', {})
        validation = execution_results.get('validation', {})

        lines = [
            f"Task: {task}",
            f"Status: {status}",
            f"Completed: {metrics.get('steps_completed', 0)} steps",
            f"Failed: {metrics.get('steps_failed', 0)} steps",
            f"Replans: {metrics.get('replans', 0)}",
            f"Duration: {metrics.get('total_duration', 0):.2f}s",
        ]

        if validation:
            lines.append(f"Quality: {validation.get('quality_score', 0):.0%} ({validation.get('verdict', '?')})")
            issues = validation.get('issues', [])
            if issues:
                lines.append("Issues:")
                for issue in issues:
                    lines.append(f"  - {issue}")

        lines.append("")
        lines.append("## Steps")
        for sr in execution_results.get('step_results', []):
            step = sr.get('step', {})
            result = sr.get('result', {})
            emoji = 'OK' if result.get('success') else 'FAIL'
            lines.append(f"  [{emoji}] Step {step.get('order', '?')}: {step.get('description', '?')}")

        return "\n".join(lines)

    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive agent status."""
        return {
            'agent': {
                'is_running': self.is_running,
                'current_task': self.current_task,
                'current_plan': self.planner.get_plan_summary() if self.current_plan else None,
            },
            'memory': self.memory_system.get_status_report(),
            'llm': self.llm_client.get_stats() if self.llm_client else {},
            'routing': self.model_router.get_stats() if self.model_router else {},
            'execution': {
                'total': len(self.executor.execution_history) if self.executor else 0,
                'success_rate': self.executor._calculate_success_rate() if self.executor else 0,
            },
            'timestamp': datetime.now().isoformat(),
        }
