"""
Task planning and decomposition module.
Uses LLM for intelligent task analysis, decomposition, and replanning.
"""

import json
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


# Available tools the LLM can choose from
AVAILABLE_TOOLS = ['read', 'write', 'exec', 'web_search', 'memory_search']


class Planner:
    """Handles LLM-powered task decomposition, planning, and replanning."""

    def __init__(self, memory_system, model_router=None):
        """
        Initialize the planner.

        Args:
            memory_system: Reference to the memory system for context retrieval.
            model_router: ModelRouter for intelligent LLM selection (optional).
        """
        self.memory_system = memory_system
        self.model_router = model_router
        self.current_plan = None

    def create_plan(self, task_description: str) -> dict:
        """
        Create a detailed execution plan using LLM analysis.

        Args:
            task_description: High-level description of the task.

        Returns:
            Structured plan with steps, dependencies, and priorities.
        """
        # Get relevant memories for context
        memories = self.memory_system.get_relevant_memories(task_description, limit=5)
        memory_context = self._format_memories(memories)

        # Use LLM to analyze and decompose
        if self.model_router:
            from agent.core.model_router import TaskType, Complexity
            complexity = self.model_router.estimate_complexity(task_description)
            plan_data = self._llm_create_plan(task_description, memory_context, complexity)
        else:
            plan_data = self._fallback_create_plan(task_description)

        # Build plan structure
        plan = {
            'original_task': task_description,
            'status': 'created',
            'steps': plan_data.get('steps', []),
            'dependencies': self._build_dependencies(plan_data.get('steps', [])),
            'priority': plan_data.get('priority', 'medium'),
            'estimated_cost': self._estimate_cost(plan_data.get('steps', [])),
            'acceptance_criteria': plan_data.get('acceptance_criteria', []),
            'created_at': self._get_timestamp(),
        }

        # Validate step IDs and assign orders
        for i, step in enumerate(plan['steps']):
            if 'id' not in step:
                step['id'] = f'step_{i + 1:03d}'
            if 'order' not in step:
                step['order'] = i + 1
            step.setdefault('status', 'pending')
            step.setdefault('type', 'execution')

        self.current_plan = plan
        return plan

    def _llm_create_plan(self, task_description: str, memory_context: str, complexity) -> dict:
        """Use LLM to create a plan."""
        from agent.core.model_router import TaskType

        system_prompt = f"""You are a task planning engine for an AI agent named Claw.
You decompose tasks into executable steps.

Available tools: {', '.join(AVAILABLE_TOOLS)}
- read: Read a file from disk
- write: Write content to a file
- exec: Execute a shell command (bash)
- web_search: Search the web for information
- memory_search: Search the agent's memory for relevant info

{memory_context}

Respond with ONLY valid JSON (no markdown, no explanation), in this exact format:
{{
  "steps": [
    {{
      "id": "step_001",
      "description": "What this step does",
      "required_tools": ["tool_name"],
      "estimated_time": 2,
      "depends_on": []
    }}
  ],
  "priority": "medium",
  "acceptance_criteria": [
    "Criterion that must be true when task is done"
  ]
}}

Rules:
- Each step must use exactly the tools needed from the available list
- depends_on contains step IDs this step requires to be completed first
- estimated_time is in minutes
- Break complex tasks into 3-10 steps. Simple tasks can be 1-2 steps.
- Be specific in descriptions — include file paths, commands, etc.
- acceptance_criteria: testable conditions that prove the task is complete"""

        user_prompt = f"Create an execution plan for this task:\n\n{task_description}"

        resp = self.model_router.complete_routed(
            messages=[{'role': 'user', 'content': user_prompt}],
            task_type=TaskType.PLAN,
            complexity=complexity,
            system=system_prompt,
            temperature=0.3,
            max_tokens=4096,
            response_format='json',
        )

        if resp.success and resp.content:
            try:
                data = json.loads(resp.content)
                return data
            except json.JSONDecodeError:
                # Try to extract JSON from response
                content = resp.content
                start = content.find('{')
                end = content.rfind('}') + 1
                if start >= 0 and end > start:
                    try:
                        return json.loads(content[start:end])
                    except json.JSONDecodeError:
                        pass
                logger.warning("Failed to parse LLM plan response as JSON")

        return self._fallback_create_plan(task_description)

    def _fallback_create_plan(self, task_description: str) -> dict:
        """Create a basic plan without LLM (fallback)."""
        return {
            'steps': [
                {
                    'id': 'step_001',
                    'description': task_description,
                    'required_tools': ['exec'],
                    'estimated_time': 5,
                    'depends_on': [],
                }
            ],
            'priority': 'medium',
            'acceptance_criteria': [f'Task "{task_description}" is completed'],
        }

    def replan(self, completed_steps: list, failed_step: dict, error_context: str) -> dict:
        """
        Generate a new plan from current state after a failure.

        Args:
            completed_steps: Steps that were successfully completed.
            failed_step: The step that failed.
            error_context: Description of what went wrong.

        Returns:
            New plan dict with remaining steps.
        """
        if not self.model_router:
            return self._fallback_replan(failed_step)

        from agent.core.model_router import TaskType, Complexity

        completed_desc = '\n'.join(
            f"  [DONE] {s['description']}" for s in completed_steps
        )
        system_prompt = f"""You are a replanning engine. A task partially completed but a step failed.
Create a new plan for the REMAINING work only.

Available tools: {', '.join(AVAILABLE_TOOLS)}

Respond with ONLY valid JSON in the same format as a plan:
{{
  "steps": [...],
  "priority": "high",
  "acceptance_criteria": [...]
}}"""

        user_prompt = f"""Original task: {self.current_plan['original_task']}

Completed steps:
{completed_desc}

Failed step: {failed_step['description']}
Error: {error_context}

Create a new plan to complete the remaining work, working around the failure."""

        resp = self.model_router.complete_routed(
            messages=[{'role': 'user', 'content': user_prompt}],
            task_type=TaskType.REPLAN,
            complexity=Complexity.MEDIUM,
            system=system_prompt,
            temperature=0.3,
            max_tokens=4096,
            response_format='json',
        )

        if resp.success and resp.content:
            try:
                data = json.loads(resp.content)
                # Re-number steps starting after completed ones
                offset = len(completed_steps) + 1
                for i, step in enumerate(data.get('steps', [])):
                    step['id'] = f'step_{offset + i:03d}'
                    step['order'] = offset + i
                    step.setdefault('status', 'pending')
                    step.setdefault('type', 'execution')

                # Update current plan
                self.current_plan['steps'] = completed_steps + data['steps']
                self.current_plan['dependencies'] = self._build_dependencies(self.current_plan['steps'])
                self.current_plan['status'] = 'in_progress'
                self.current_plan['acceptance_criteria'] = data.get(
                    'acceptance_criteria', self.current_plan.get('acceptance_criteria', [])
                )
                return self.current_plan
            except json.JSONDecodeError:
                logger.warning("Failed to parse replan response")

        return self._fallback_replan(failed_step)

    def _fallback_replan(self, failed_step: dict) -> dict:
        """Simple replan: retry the failed step."""
        if self.current_plan:
            for step in self.current_plan['steps']:
                if step['id'] == failed_step['id']:
                    step['status'] = 'pending'
                    step['retry_count'] = step.get('retry_count', 0) + 1
            return self.current_plan
        return {'steps': [], 'status': 'failed'}

    def _build_dependencies(self, steps: list) -> dict:
        """Build dependency map from step data."""
        deps = {}
        for step in steps:
            step_id = step.get('id', '')
            explicit_deps = step.get('depends_on', [])
            if explicit_deps:
                deps[step_id] = explicit_deps
            else:
                # Default: sequential dependency
                idx = steps.index(step)
                if idx > 0:
                    deps[step_id] = [steps[idx - 1]['id']]
                else:
                    deps[step_id] = []
        return deps

    def _format_memories(self, memories: list) -> str:
        """Format memories as context for LLM."""
        if not memories:
            return ''
        lines = ['Relevant context from memory:']
        for m in memories[:5]:
            if isinstance(m, dict):
                lines.append(f"- {m.get('field', '')}: {m.get('value', '')}")
            else:
                lines.append(f"- {m}")
        return '\n'.join(lines)

    def _estimate_cost(self, steps: list) -> dict:
        """Estimate resource cost of executing the plan."""
        total_time = sum(step.get('estimated_time', 5) for step in steps)
        return {
            'time_minutes': total_time,
            'complexity': len(steps),
            'tool_requirements': self._count_tool_requirements(steps),
        }

    def _count_tool_requirements(self, steps: list) -> dict:
        """Count total tool requirements across all steps."""
        counts = {}
        for step in steps:
            for tool in step.get('required_tools', []):
                counts[tool] = counts.get(tool, 0) + 1
        return counts

    def _get_timestamp(self) -> str:
        return datetime.now().isoformat()

    # --- Status management (preserved from original) ---

    def update_plan_status(self, step_id: str, status: str, **kwargs):
        """Update the status of a specific step."""
        if self.current_plan:
            for step in self.current_plan['steps']:
                if step['id'] == step_id:
                    step['status'] = status
                    step['updated_at'] = self._get_timestamp()
                    for key, value in kwargs.items():
                        step[key] = value
                    self._update_overall_status()
                    break

    def _update_overall_status(self):
        """Update overall plan status based on step completion."""
        if not self.current_plan or not self.current_plan['steps']:
            return
        completed = sum(1 for s in self.current_plan['steps'] if s['status'] == 'completed')
        total = len(self.current_plan['steps'])
        if completed == 0:
            self.current_plan['status'] = 'pending'
        elif completed == total:
            self.current_plan['status'] = 'completed'
        else:
            self.current_plan['status'] = 'in_progress'
        self.current_plan['progress'] = (completed / total) * 100

    def get_next_steps(self) -> list:
        """Get steps ready for execution (all dependencies met)."""
        if not self.current_plan:
            return []
        ready = []
        for step in self.current_plan['steps']:
            if step['status'] == 'pending' and self._dependencies_satisfied(step['id']):
                ready.append(step)
        return ready

    def _dependencies_satisfied(self, step_id: str) -> bool:
        """Check if all dependencies for a step have been completed."""
        deps = self.current_plan.get('dependencies', {}).get(step_id, [])
        if not deps:
            return True
        completed_ids = {s['id'] for s in self.current_plan['steps'] if s['status'] == 'completed'}
        return all(d in completed_ids for d in deps)

    def get_plan_summary(self) -> Optional[dict]:
        """Get a concise summary of the current plan."""
        if not self.current_plan:
            return None
        return {
            'task': self.current_plan['original_task'],
            'status': self.current_plan['status'],
            'progress': self.current_plan.get('progress', 0),
            'total_steps': len(self.current_plan['steps']),
            'completed_steps': sum(1 for s in self.current_plan['steps'] if s['status'] == 'completed'),
            'estimated_time': self.current_plan.get('estimated_cost', {}).get('time_minutes', 0),
            'priority': self.current_plan.get('priority', 'medium'),
            'acceptance_criteria': self.current_plan.get('acceptance_criteria', []),
        }

    def validate_plan(self) -> dict:
        """Validate the current plan for correctness."""
        if not self.current_plan:
            return {'valid': False, 'messages': ['No plan exists to validate']}
        messages = []
        if self._has_circular_dependencies():
            messages.append('Circular dependencies detected')
        step_ids = [s['id'] for s in self.current_plan['steps']]
        if len(step_ids) != len(set(step_ids)):
            messages.append('Duplicate step IDs found')
        all_ids = set(step_ids)
        for sid, deps in self.current_plan.get('dependencies', {}).items():
            for d in deps:
                if d not in all_ids:
                    messages.append(f'Step {sid} references non-existent dependency {d}')
        return {'valid': len(messages) == 0, 'messages': messages}

    def _has_circular_dependencies(self) -> bool:
        """Detect circular dependencies using DFS."""
        visited = set()
        rec_stack = set()

        def has_cycle(node):
            if node not in visited:
                visited.add(node)
                rec_stack.add(node)
                for neighbor in self.current_plan.get('dependencies', {}).get(node, []):
                    if neighbor not in visited and has_cycle(neighbor):
                        return True
                    elif neighbor in rec_stack:
                        return True
                rec_stack.remove(node)
            return False

        for node in self.current_plan.get('dependencies', {}):
            if has_cycle(node):
                return True
        return False
