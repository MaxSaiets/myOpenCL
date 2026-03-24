"""
Task completion validation module.
Verifies that tasks are actually complete by checking acceptance criteria.
"""

import json
import os
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class TaskValidator:
    """Validates task completion against acceptance criteria."""

    def __init__(self, model_router=None, memory_store=None):
        """
        Args:
            model_router: ModelRouter for LLM-based validation.
            memory_store: MemoryStore for storing evaluation scores.
        """
        self.model_router = model_router
        self.memory_store = memory_store

    def validate_completion(
        self,
        task_description: str,
        plan: dict,
        execution_results: dict,
        acceptance_criteria: list[str] = None,
    ) -> dict:
        """
        Validate that a task is truly complete.

        Args:
            task_description: Original task description.
            plan: The executed plan.
            execution_results: Results from execution.
            acceptance_criteria: List of testable criteria.

        Returns:
            dict with quality_score (0.0-1.0), criteria_met, issues, verdict.
        """
        criteria = acceptance_criteria or plan.get('acceptance_criteria', [])
        if not criteria:
            criteria = [f'Task "{task_description}" completed successfully']

        # Check each criterion
        criteria_results = []
        for criterion in criteria:
            result = self._check_criterion(criterion, execution_results)
            criteria_results.append(result)

        # Calculate quality score
        met_count = sum(1 for c in criteria_results if c['met'])
        total = len(criteria_results)
        base_score = met_count / total if total > 0 else 0.0

        # Adjust for retries and failures
        metrics = execution_results.get('metrics', {})
        retry_penalty = min(0.1 * metrics.get('steps_failed', 0), 0.3)
        quality_score = max(0.0, base_score - retry_penalty)

        # LLM-based holistic evaluation if available
        llm_assessment = None
        if self.model_router and quality_score > 0.3:
            llm_assessment = self._llm_evaluate(task_description, execution_results, criteria_results)
            if llm_assessment and 'score' in llm_assessment:
                # Blend: 60% criteria-based, 40% LLM assessment
                quality_score = 0.6 * quality_score + 0.4 * llm_assessment['score']

        quality_score = round(min(1.0, quality_score), 4)

        # Determine verdict
        if quality_score >= 0.8:
            verdict = 'passed'
        elif quality_score >= 0.5:
            verdict = 'partial'
        else:
            verdict = 'failed'

        result = {
            'quality_score': quality_score,
            'verdict': verdict,
            'criteria_met': met_count,
            'criteria_total': total,
            'criteria_results': criteria_results,
            'llm_assessment': llm_assessment,
            'issues': [c['reason'] for c in criteria_results if not c['met']],
            'timestamp': datetime.now().isoformat(),
        }

        # Store evaluation score
        if self.memory_store:
            self.memory_store.store_evaluation(
                task_id=plan.get('original_task', task_description)[:100],
                score=quality_score,
                category=verdict,
                details=result,
            )

        return result

    def _check_criterion(self, criterion: str, execution_results: dict) -> dict:
        """
        Check a single acceptance criterion against execution results.

        Returns:
            dict with met (bool), criterion, reason.
        """
        criterion_lower = criterion.lower()

        # File existence checks
        if 'file exists' in criterion_lower or 'file_exists' in criterion_lower:
            path = self._extract_path_from_criterion(criterion)
            if path:
                exists = os.path.exists(path)
                return {
                    'criterion': criterion,
                    'met': exists,
                    'reason': f"File {'exists' if exists else 'not found'}: {path}",
                }

        # Exit code checks
        if 'exit code' in criterion_lower or 'return code' in criterion_lower:
            step_results = execution_results.get('step_results', [])
            all_ok = all(
                sr.get('result', {}).get('success', False)
                for sr in step_results
            )
            return {
                'criterion': criterion,
                'met': all_ok,
                'reason': 'All steps returned success' if all_ok else 'Some steps failed',
            }

        # "completed successfully" — check overall status
        if 'completed' in criterion_lower or 'success' in criterion_lower:
            status = execution_results.get('status', '')
            ok = status == 'completed' or execution_results.get('metrics', {}).get('steps_failed', 1) == 0
            return {
                'criterion': criterion,
                'met': ok,
                'reason': f"Task status: {status}",
            }

        # Default: assume met if task succeeded overall
        overall = execution_results.get('status') == 'completed'
        return {
            'criterion': criterion,
            'met': overall,
            'reason': 'Assumed from overall task status',
        }

    def _llm_evaluate(self, task_description: str, execution_results: dict, criteria_results: list) -> Optional[dict]:
        """Use LLM for holistic task evaluation."""
        from agent.core.model_router import TaskType, Complexity

        step_summary = ''
        for sr in execution_results.get('step_results', [])[:10]:
            step = sr.get('step', {})
            result = sr.get('result', {})
            emoji = 'OK' if result.get('success') else 'FAIL'
            step_summary += f"  [{emoji}] {step.get('description', '?')}\n"

        criteria_summary = '\n'.join(
            f"  [{'MET' if c['met'] else 'NOT MET'}] {c['criterion']}"
            for c in criteria_results
        )

        prompt = f"""Evaluate task completion quality.

Task: {task_description}

Step Results:
{step_summary}

Acceptance Criteria:
{criteria_summary}

Rate the quality of completion from 0.0 to 1.0 and explain briefly.
Respond with ONLY valid JSON:
{{
  "score": 0.85,
  "explanation": "brief explanation"
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
                return json.loads(resp.content)
            except json.JSONDecodeError:
                pass
        return None

    def _extract_path_from_criterion(self, criterion: str) -> str:
        """Extract a file path from a criterion string."""
        import re
        match = re.search(r'(/[\w./\-]+\.\w+)', criterion)
        return match.group(1) if match else ''
