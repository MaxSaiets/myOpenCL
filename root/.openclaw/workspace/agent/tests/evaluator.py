"""
Iterative evaluation framework for the OpenClaw agent.
Runs test suites, scores results, generates reports, and tracks improvement.
"""

import json
import os
import sys
import time
import logging
from datetime import datetime
from typing import Optional

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)


class EvaluationReport:
    """Structured evaluation report."""

    def __init__(self):
        self.results: list[dict] = []
        self.overall_score: float = 0.0
        self.category_scores: dict[str, float] = {}
        self.difficulty_scores: dict[str, float] = {}
        self.regressions: list[dict] = []
        self.improvements: list[dict] = []
        self.timestamp: str = datetime.now().isoformat()
        self.duration_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            'overall_score': round(self.overall_score * 100, 1),
            'category_scores': {k: round(v * 100, 1) for k, v in self.category_scores.items()},
            'difficulty_scores': {k: round(v * 100, 1) for k, v in self.difficulty_scores.items()},
            'total_tests': len(self.results),
            'passed': sum(1 for r in self.results if r['score'] >= 0.7),
            'partial': sum(1 for r in self.results if 0.3 <= r['score'] < 0.7),
            'failed': sum(1 for r in self.results if r['score'] < 0.3),
            'regressions': self.regressions,
            'improvements': self.improvements,
            'timestamp': self.timestamp,
            'duration_seconds': round(self.duration_seconds, 1),
        }

    def to_text(self) -> str:
        """Generate text-based report."""
        d = self.to_dict()
        lines = [
            f"{'=' * 50}",
            f"  OpenClaw Evaluation Report",
            f"  {self.timestamp}",
            f"{'=' * 50}",
            f"",
            f"  Overall Score: {d['overall_score']}/100",
            f"  Tests: {d['total_tests']} total | {d['passed']} passed | {d['partial']} partial | {d['failed']} failed",
            f"  Duration: {d['duration_seconds']}s",
            f"",
            f"  Category Scores:",
        ]
        for cat, score in sorted(d['category_scores'].items()):
            bar = '#' * int(score / 5) + '.' * (20 - int(score / 5))
            lines.append(f"    {cat:20s} [{bar}] {score:5.1f}")

        lines.append(f"\n  Difficulty Scores:")
        for diff, score in sorted(d['difficulty_scores'].items()):
            lines.append(f"    {diff:20s} {score:5.1f}/100")

        if self.regressions:
            lines.append(f"\n  Regressions ({len(self.regressions)}):")
            for r in self.regressions:
                lines.append(f"    - {r['test_id']}: {r['prev_score']:.0%} -> {r['new_score']:.0%}")

        if self.improvements:
            lines.append(f"\n  Improvements ({len(self.improvements)}):")
            for i in self.improvements:
                lines.append(f"    + {i['test_id']}: {i['prev_score']:.0%} -> {i['new_score']:.0%}")

        lines.append(f"\n{'=' * 50}")
        return '\n'.join(lines)


class AgentEvaluator:
    """Runs evaluation suites and generates reports."""

    def __init__(self, agent=None):
        """
        Args:
            agent: Agent instance to evaluate. Created if not provided.
        """
        self.agent = agent
        self.history_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'evaluation_history.json',
        )

    def run_evaluation(self, test_suite_path: str = None, tests: list = None) -> EvaluationReport:
        """
        Run a full evaluation suite.

        Args:
            test_suite_path: Path to test_cases.json.
            tests: Direct list of test dicts (alternative to file path).

        Returns:
            EvaluationReport with scores and analysis.
        """
        if tests is None:
            if test_suite_path is None:
                test_suite_path = os.path.join(
                    os.path.dirname(os.path.abspath(__file__)),
                    'test_cases.json',
                )
            with open(test_suite_path, 'r') as f:
                tests = json.load(f)

        # Ensure agent is initialized
        if self.agent is None:
            from agent.core.agent import Agent
            self.agent = Agent()

        report = EvaluationReport()
        start_time = time.time()

        for test in tests:
            logger.info(f"Running test: {test['id']} - {test['description']}")
            try:
                result = self._run_single_test(test)
                report.results.append(result)
                logger.info(f"  Score: {result['score']:.0%}")
            except Exception as e:
                logger.error(f"  Error: {e}")
                report.results.append({
                    'test_id': test['id'],
                    'description': test['description'],
                    'category': test.get('category', 'unknown'),
                    'difficulty': test.get('difficulty', 'unknown'),
                    'score': 0.0,
                    'error': str(e),
                    'details': {},
                })

        report.duration_seconds = time.time() - start_time

        # Calculate scores
        self._calculate_scores(report)

        # Compare with previous run
        self._detect_regressions(report)

        # Save to history
        self._save_history(report)

        return report

    def _run_single_test(self, test: dict) -> dict:
        """Run a single test case and score it."""
        test_id = test['id']
        task_input = test['input']
        expected = test.get('expected', {})

        # Execute the task
        plan_response = self.agent.start_task(task_input)
        if not plan_response.get('success'):
            return {
                'test_id': test_id,
                'description': test['description'],
                'category': test.get('category', 'unknown'),
                'difficulty': test.get('difficulty', 'unknown'),
                'score': 0.0,
                'details': {'error': 'Planning failed', 'plan_response': plan_response},
            }

        exec_result = self.agent.execute_task()
        score = self._score_result(test, exec_result, expected)

        return {
            'test_id': test_id,
            'description': test['description'],
            'category': test.get('category', 'unknown'),
            'difficulty': test.get('difficulty', 'unknown'),
            'score': score,
            'details': {
                'status': exec_result.get('status'),
                'steps_completed': exec_result.get('metrics', {}).get('steps_completed', 0),
                'steps_failed': exec_result.get('metrics', {}).get('steps_failed', 0),
                'validation': exec_result.get('validation', {}),
            },
        }

    def _score_result(self, test: dict, exec_result: dict, expected: dict) -> float:
        """Score a test result against expected outcomes."""
        checks = []

        # Check execution success
        status = exec_result.get('status', '')
        if status == 'completed':
            checks.append(1.0)
        elif status == 'in_progress':
            checks.append(0.5)
        else:
            checks.append(0.0)

        # Check file existence
        if 'file_exists' in expected:
            exists = os.path.exists(expected['file_exists'])
            checks.append(1.0 if exists else 0.0)

        # Check file content
        if 'file_contains' in expected and 'file_exists' in expected:
            try:
                with open(expected['file_exists'], 'r') as f:
                    content = f.read()
                checks.append(1.0 if expected['file_contains'] in content else 0.0)
            except Exception:
                checks.append(0.0)

        # Check output contains
        if 'output_contains' in expected:
            output = json.dumps(exec_result, default=str)
            checks.append(1.0 if expected['output_contains'] in output else 0.0)

        # Check no crash (error recovery tests)
        if 'no_crash' in expected:
            checks.append(1.0)  # If we got here, it didn't crash

        if 'handles_error' in expected:
            # Task should complete even if a step fails
            has_result = exec_result.get('final_output') is not None
            checks.append(1.0 if has_result else 0.0)

        # Check minimum steps
        if 'min_steps' in expected:
            plan = self.agent.current_plan or {}
            actual = len(plan.get('steps', []))
            checks.append(1.0 if actual >= expected['min_steps'] else 0.5)

        # Use validation score if available
        validation = exec_result.get('validation', {})
        if validation and 'quality_score' in validation:
            checks.append(validation['quality_score'])

        return sum(checks) / len(checks) if checks else 0.0

    def _calculate_scores(self, report: EvaluationReport):
        """Calculate aggregate scores."""
        if not report.results:
            return

        # Overall
        report.overall_score = sum(r['score'] for r in report.results) / len(report.results)

        # By category
        categories = {}
        for r in report.results:
            cat = r.get('category', 'unknown')
            categories.setdefault(cat, []).append(r['score'])
        report.category_scores = {k: sum(v) / len(v) for k, v in categories.items()}

        # By difficulty
        difficulties = {}
        for r in report.results:
            diff = r.get('difficulty', 'unknown')
            difficulties.setdefault(diff, []).append(r['score'])
        report.difficulty_scores = {k: sum(v) / len(v) for k, v in difficulties.items()}

    def _detect_regressions(self, report: EvaluationReport):
        """Compare with previous evaluation to detect regressions."""
        prev = self._load_last_history()
        if not prev:
            return

        prev_scores = {r['test_id']: r['score'] for r in prev.get('results', [])}

        for r in report.results:
            tid = r['test_id']
            if tid in prev_scores:
                prev_score = prev_scores[tid]
                new_score = r['score']
                if new_score < prev_score - 0.1:
                    report.regressions.append({
                        'test_id': tid,
                        'prev_score': prev_score,
                        'new_score': new_score,
                    })
                elif new_score > prev_score + 0.1:
                    report.improvements.append({
                        'test_id': tid,
                        'prev_score': prev_score,
                        'new_score': new_score,
                    })

    def _save_history(self, report: EvaluationReport):
        """Save evaluation results to history file."""
        history = []
        if os.path.exists(self.history_path):
            try:
                with open(self.history_path, 'r') as f:
                    history = json.load(f)
            except Exception:
                history = []

        entry = report.to_dict()
        entry['results'] = report.results
        history.append(entry)

        # Keep last 50 evaluations
        history = history[-50:]

        with open(self.history_path, 'w') as f:
            json.dump(history, f, indent=2, default=str)

    def _load_last_history(self) -> Optional[dict]:
        """Load the most recent evaluation from history."""
        if not os.path.exists(self.history_path):
            return None
        try:
            with open(self.history_path, 'r') as f:
                history = json.load(f)
            return history[-1] if history else None
        except Exception:
            return None


def main():
    """CLI entry point for running evaluations."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    )

    evaluator = AgentEvaluator()
    print("Starting evaluation...")
    report = evaluator.run_evaluation()
    print(report.to_text())

    # Save text report
    report_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        'last_report.txt',
    )
    with open(report_path, 'w') as f:
        f.write(report.to_text())
    print(f"\nReport saved to: {report_path}")


if __name__ == '__main__':
    main()
