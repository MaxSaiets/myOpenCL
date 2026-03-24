"""
Task execution module with reflection loop.
Executes plan steps, reflects on results, triggers replanning when needed.
"""

import json
import logging
import traceback
from datetime import datetime

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


class Executor:
    """Manages task execution with reflection and adaptive behavior."""

    def __init__(self, tool_registry: dict, memory_system, model_router=None):
        """
        Initialize the executor.

        Args:
            tool_registry: Registry of available tools {name: callable}.
            memory_system: Reference to the memory system.
            model_router: ModelRouter for LLM-based reflection (optional).
        """
        self.tool_registry = tool_registry
        self.memory_system = memory_system
        self.model_router = model_router
        self.execution_history = []
        self.active_executions = {}

    def execute_step(self, step: dict, context: dict = None) -> dict:
        """
        Execute a single plan step with reflection.

        Args:
            step: The step dict from the plan.
            context: Additional execution context.

        Returns:
            Execution result dict.
        """
        step_id = step['id']
        record = {
            'step_id': step_id,
            'start_time': self._now(),
            'status': 'in_progress',
            'attempt': 1,
            'tool_calls': [],
        }
        self.active_executions[step_id] = record

        try:
            exec_context = self._build_execution_context(step, context)
            result = self._perform_execution(step, exec_context)

            # Reflection: evaluate the result
            reflection = self._reflect_on_step(step, result)
            result['reflection'] = reflection

            record['status'] = 'completed' if result['success'] else 'failed'
            record['end_time'] = self._now()
            record['result'] = result
            record['duration'] = self._duration(record['start_time'], record['end_time'])
            record['reflection'] = reflection

            self.execution_history.append(record.copy())
            self.active_executions.pop(step_id, None)

            # Store execution in memory as episodic
            self._store_execution_memory(step, result, reflection)

            return result

        except Exception as e:
            error_result = {
                'success': False,
                'error_type': 'execution_error',
                'error_message': str(e),
                'traceback': traceback.format_exc(),
            }
            record['status'] = 'failed'
            record['end_time'] = self._now()
            record['result'] = error_result
            record['duration'] = self._duration(record['start_time'], record['end_time'])
            self.execution_history.append(record.copy())
            self.active_executions.pop(step_id, None)
            return error_result

    def _reflect_on_step(self, step: dict, result: dict) -> dict:
        """
        Use LLM to evaluate step result and decide next action.

        Returns:
            dict with keys: goal_achieved, plan_valid, action (continue/retry/replan).
        """
        if not self.model_router:
            # No LLM available — use simple heuristic
            return {
                'goal_achieved': 'yes' if result['success'] else 'no',
                'plan_valid': 'yes',
                'action': 'continue' if result['success'] else 'retry',
            }

        from agent.core.model_router import TaskType, Complexity

        # Build a concise summary of the result
        output_summary = ''
        if result.get('output'):
            out = result['output']
            if isinstance(out, dict):
                output_summary = json.dumps(out, default=str)[:500]
            elif isinstance(out, str):
                output_summary = out[:500]
            elif isinstance(out, list):
                output_summary = json.dumps(out, default=str)[:500]

        prompt = f"""You are evaluating the result of a task step.

Step: {step['description']}
Success: {result['success']}
Output: {output_summary}
Errors: {result.get('error_message', 'none')}

Evaluate and respond with ONLY valid JSON:
{{
  "goal_achieved": "yes|partially|no",
  "plan_valid": "yes|needs_adjustment",
  "action": "continue|retry|replan",
  "reason": "brief explanation"
}}"""

        resp = self.model_router.complete_routed(
            messages=[{'role': 'user', 'content': prompt}],
            task_type=TaskType.REFLECT,
            complexity=Complexity.SIMPLE,
            temperature=0.1,
            max_tokens=200,
            response_format='json',
        )

        if resp.success and resp.content:
            try:
                reflection = json.loads(resp.content)
                return reflection
            except json.JSONDecodeError:
                pass

        # Fallback
        return {
            'goal_achieved': 'yes' if result['success'] else 'no',
            'plan_valid': 'yes',
            'action': 'continue' if result['success'] else 'retry',
        }

    def _perform_execution(self, step: dict, context: dict) -> dict:
        """Execute step using required tools."""
        required_tools = step.get('required_tools', ['default'])
        tool_results = []

        for tool_name in required_tools:
            tool = self.tool_registry.get(tool_name, self.tool_registry.get('default'))
            if not tool:
                tool_results.append({
                    'success': False, 'tool': tool_name,
                    'error': f"Tool '{tool_name}' not found",
                })
                continue

            try:
                args = self._extract_tool_arguments(tool_name, step, context)
                result = tool(**args) if args else tool()
                tool_results.append({
                    'success': result.get('success', True),
                    'tool': tool_name,
                    'output': result,
                })
                # Record in active execution
                if step['id'] in self.active_executions:
                    self.active_executions[step['id']]['tool_calls'].append({
                        'tool': tool_name,
                        'success': result.get('success', True),
                        'timestamp': self._now(),
                    })
            except Exception as e:
                tool_results.append({
                    'success': False, 'tool': tool_name, 'error': str(e),
                })

        all_ok = all(r.get('success', False) for r in tool_results)
        return {
            'success': all_ok,
            'step_id': step['id'],
            'tool_results': tool_results,
            'output': self._consolidate_outputs(tool_results),
            'metrics': {
                'tool_calls': len(tool_results),
                'successful_calls': sum(1 for r in tool_results if r.get('success')),
                'failed_calls': sum(1 for r in tool_results if not r.get('success')),
            },
        }

    def _extract_tool_arguments(self, tool_name: str, step: dict, context: dict) -> dict:
        """Extract arguments for a tool call from step description."""
        desc = step.get('description', '')
        args = {}

        if tool_name == 'read':
            path = self._extract_path(desc)
            if path:
                args['path'] = path
        elif tool_name == 'write':
            path = self._extract_path(desc)
            if path:
                args['path'] = path
            args['content'] = step.get('content', desc)
        elif tool_name in ('exec', 'default'):
            cmd = step.get('command', desc)
            args['command'] = cmd
        elif tool_name == 'web_search':
            args['query'] = step.get('query', desc)
        elif tool_name == 'memory_search':
            args['query'] = step.get('query', desc)

        return args

    def _extract_path(self, description: str) -> str:
        """Extract file path from description using heuristics."""
        import re
        # Match common path patterns
        patterns = [
            r'(/[\w./\-]+\.\w+)',          # /path/to/file.ext
            r'(~/[\w./\-]+)',               # ~/path/to/file
            r'(\./[\w./\-]+)',              # ./relative/path
        ]
        for pattern in patterns:
            match = re.search(pattern, description)
            if match:
                return match.group(1)
        return ''

    def _consolidate_outputs(self, tool_results: list):
        """Consolidate outputs from multiple tool calls."""
        outputs = [r['output'] for r in tool_results if r.get('success') and 'output' in r]
        if len(outputs) == 1:
            return outputs[0]
        elif outputs:
            return outputs
        return None

    def _store_execution_memory(self, step: dict, result: dict, reflection: dict):
        """Store execution as episodic memory."""
        try:
            content = f"Executed: {step['description']} | Success: {result['success']} | Action: {reflection.get('action', 'unknown')}"
            self.memory_system.store_memory(
                'task_history', 'execution',
                content, {'step_id': step['id'], 'timestamp': self._now()},
            )
        except Exception:
            pass  # Don't let memory errors break execution

    def _build_execution_context(self, step: dict, additional: dict = None) -> dict:
        """Build execution context with memory and recent history."""
        ctx = {
            'step': step,
            'memory': self.memory_system.get_relevant_memories(step.get('description', ''), limit=3),
            'recent_executions': self.execution_history[-5:],
        }
        if additional:
            ctx.update(additional)
        return ctx

    # --- Utilities ---

    def _calculate_success_rate(self) -> float:
        if not self.execution_history:
            return 0.0
        ok = sum(1 for e in self.execution_history if e['status'] == 'completed')
        return (ok / len(self.execution_history)) * 100

    def _now(self) -> str:
        return datetime.now().isoformat()

    def _duration(self, start: str, end: str) -> float:
        s = datetime.fromisoformat(start)
        e = datetime.fromisoformat(end)
        return (e - s).total_seconds()
