"""
Intelligent model routing based on task type and complexity.
Selects the optimal LLM for each operation to balance cost and quality.
"""

import logging
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class TaskType(Enum):
    """Types of tasks that require different model capabilities."""
    CLASSIFY = 'classify'        # Simple classification, tool selection
    PLAN = 'plan'                # Task decomposition, planning
    EXECUTE = 'execute'          # Code generation, complex analysis
    SUMMARIZE = 'summarize'      # Memory compression, summarization
    COMMUNICATE = 'communicate'  # User-facing responses
    EMBED = 'embed'              # Embedding generation
    REFLECT = 'reflect'          # Step evaluation, reflection
    REPLAN = 'replan'            # Dynamic replanning after failure


class Complexity(Enum):
    """Task complexity levels."""
    SIMPLE = 'simple'
    MEDIUM = 'medium'
    COMPLEX = 'complex'


# Maps (task_type, complexity) -> model_key from llm_client.MODELS
ROUTING_TABLE = {
    # CLASSIFY — always use fast model
    (TaskType.CLASSIFY, Complexity.SIMPLE): 'fast',
    (TaskType.CLASSIFY, Complexity.MEDIUM): 'fast',
    (TaskType.CLASSIFY, Complexity.COMPLEX): 'fast',

    # PLAN — use reasoning for complex, fast for simple
    (TaskType.PLAN, Complexity.SIMPLE): 'fast',
    (TaskType.PLAN, Complexity.MEDIUM): 'default',
    (TaskType.PLAN, Complexity.COMPLEX): 'reasoning',

    # EXECUTE — use reasoning for complex
    (TaskType.EXECUTE, Complexity.SIMPLE): 'fast',
    (TaskType.EXECUTE, Complexity.MEDIUM): 'default',
    (TaskType.EXECUTE, Complexity.COMPLEX): 'reasoning',

    # SUMMARIZE — always fast (bulk operation)
    (TaskType.SUMMARIZE, Complexity.SIMPLE): 'fast',
    (TaskType.SUMMARIZE, Complexity.MEDIUM): 'fast',
    (TaskType.SUMMARIZE, Complexity.COMPLEX): 'fast',

    # COMMUNICATE — default for quality
    (TaskType.COMMUNICATE, Complexity.SIMPLE): 'fast',
    (TaskType.COMMUNICATE, Complexity.MEDIUM): 'default',
    (TaskType.COMMUNICATE, Complexity.COMPLEX): 'default',

    # REFLECT — fast for simple, default for complex
    (TaskType.REFLECT, Complexity.SIMPLE): 'fast',
    (TaskType.REFLECT, Complexity.MEDIUM): 'fast',
    (TaskType.REFLECT, Complexity.COMPLEX): 'default',

    # REPLAN — needs reasoning
    (TaskType.REPLAN, Complexity.SIMPLE): 'fast',
    (TaskType.REPLAN, Complexity.MEDIUM): 'default',
    (TaskType.REPLAN, Complexity.COMPLEX): 'reasoning',

    # EMBED — always embed model
    (TaskType.EMBED, Complexity.SIMPLE): 'embed',
    (TaskType.EMBED, Complexity.MEDIUM): 'embed',
    (TaskType.EMBED, Complexity.COMPLEX): 'embed',
}


class ModelRouter:
    """Routes tasks to appropriate LLM models based on type and complexity."""

    def __init__(self, llm_client):
        """
        Args:
            llm_client: LLMClient instance for making API calls.
        """
        self.llm_client = llm_client
        self._routing_log: list[dict] = []
        self._cost_by_type: dict[str, float] = {}

    def route(self, task_type: TaskType, complexity: Complexity = Complexity.MEDIUM) -> str:
        """
        Get the model key for a given task type and complexity.

        Args:
            task_type: The type of task to route.
            complexity: The estimated complexity.

        Returns:
            Model key string (e.g., 'fast', 'reasoning', 'default').
        """
        key = ROUTING_TABLE.get((task_type, complexity), 'default')
        self._routing_log.append({
            'task_type': task_type.value,
            'complexity': complexity.value,
            'model_key': key,
        })
        return key

    def estimate_complexity(self, task_description: str) -> Complexity:
        """
        Use a fast LLM call to classify task complexity.

        Args:
            task_description: Natural language task description.

        Returns:
            Complexity enum value.
        """
        prompt = f"""Classify the complexity of this task as exactly one word: simple, medium, or complex.

Task: {task_description}

Rules:
- simple: single action, no dependencies, straightforward (e.g., read a file, run a command)
- medium: 2-5 steps, some dependencies, moderate reasoning needed
- complex: 6+ steps, multiple dependencies, requires deep analysis or code generation

Respond with ONLY one word: simple, medium, or complex."""

        resp = self.llm_client.complete(
            messages=[{'role': 'user', 'content': prompt}],
            model_key='fast',
            temperature=0.0,
            max_tokens=10,
        )

        if resp.success:
            word = resp.content.strip().lower()
            for c in Complexity:
                if c.value in word:
                    return c

        return Complexity.MEDIUM  # default fallback

    def complete_routed(
        self,
        messages: list[dict],
        task_type: TaskType,
        complexity: Complexity = None,
        task_description: str = None,
        **kwargs,
    ):
        """
        Complete a request using the appropriate model for the task type.

        Args:
            messages: Chat messages.
            task_type: Type of task for routing.
            complexity: Pre-determined complexity (auto-estimated if None and task_description given).
            task_description: Used for auto complexity estimation.
            **kwargs: Additional args passed to llm_client.complete().

        Returns:
            LLMResponse from the selected model.
        """
        if complexity is None and task_description:
            complexity = self.estimate_complexity(task_description)
        elif complexity is None:
            complexity = Complexity.MEDIUM

        model_key = self.route(task_type, complexity)
        logger.info(f"Routing {task_type.value}/{complexity.value} -> {model_key}")

        resp = self.llm_client.complete(messages=messages, model_key=model_key, **kwargs)

        # Track cost by type
        type_key = task_type.value
        self._cost_by_type[type_key] = self._cost_by_type.get(type_key, 0.0) + resp.cost_usd

        return resp

    def get_stats(self) -> dict:
        """Return routing statistics."""
        return {
            'total_routed': len(self._routing_log),
            'cost_by_type': dict(self._cost_by_type),
            'recent_routes': self._routing_log[-10:],
        }
