"""
Continuous self-improvement engine.
Analyzes evaluation results, identifies weaknesses, proposes improvements.
"""

import json
import os
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class SelfImprover:
    """Analyzes evaluation results and proposes improvements."""

    def __init__(self, model_router=None, memory_store=None):
        """
        Args:
            model_router: ModelRouter for LLM analysis.
            memory_store: MemoryStore for reading evaluation history.
        """
        self.model_router = model_router
        self.memory_store = memory_store
        self.improvements_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            '..', 'improvements',
        )
        os.makedirs(self.improvements_dir, exist_ok=True)

    def analyze_evaluation(self, report_dict: dict) -> dict:
        """
        Analyze an evaluation report and propose improvements.

        Args:
            report_dict: Evaluation report as dict.

        Returns:
            Analysis with weaknesses, hypotheses, and proposals.
        """
        analysis = {
            'timestamp': datetime.now().isoformat(),
            'overall_score': report_dict.get('overall_score', 0),
            'weakest_categories': [],
            'hypotheses': [],
            'proposals': [],
        }

        # Find weakest categories
        cat_scores = report_dict.get('category_scores', {})
        if cat_scores:
            sorted_cats = sorted(cat_scores.items(), key=lambda x: x[1])
            analysis['weakest_categories'] = [
                {'category': cat, 'score': score}
                for cat, score in sorted_cats[:3]
                if score < 80
            ]

        # Find regressions
        regressions = report_dict.get('regressions', [])
        if regressions:
            analysis['regressions'] = regressions

        # Use LLM to generate hypotheses and proposals
        if self.model_router and analysis['weakest_categories']:
            llm_analysis = self._llm_analyze(report_dict, analysis)
            if llm_analysis:
                analysis['hypotheses'] = llm_analysis.get('hypotheses', [])
                analysis['proposals'] = llm_analysis.get('proposals', [])

        # Save analysis
        self._save_analysis(analysis)

        return analysis

    def _llm_analyze(self, report: dict, preliminary: dict) -> Optional[dict]:
        """Use LLM to generate improvement hypotheses."""
        from agent.core.model_router import TaskType, Complexity

        weak_cats = '\n'.join(
            f"  - {w['category']}: {w['score']}/100"
            for w in preliminary['weakest_categories']
        )

        failed_tests = [r for r in report.get('results', []) if r.get('score', 1) < 0.5]
        failed_summary = '\n'.join(
            f"  - {t['test_id']}: {t['description']} (score: {t.get('score', 0):.0%})"
            for t in failed_tests[:5]
        )

        prompt = f"""Analyze this AI agent evaluation and propose improvements.

Overall Score: {report.get('overall_score', 0)}/100

Weakest Categories:
{weak_cats}

Failed Tests:
{failed_summary}

For each weakness, provide:
1. A hypothesis about WHY it's failing
2. A specific, actionable proposal to fix it

Respond with ONLY valid JSON:
{{
  "hypotheses": [
    "Hypothesis about root cause"
  ],
  "proposals": [
    {{
      "target": "module/file to change",
      "change": "specific change description",
      "expected_impact": "what should improve",
      "priority": "high|medium|low"
    }}
  ]
}}"""

        resp = self.model_router.complete_routed(
            messages=[{'role': 'user', 'content': prompt}],
            task_type=TaskType.REFLECT,
            complexity=Complexity.MEDIUM,
            temperature=0.3,
            max_tokens=1000,
            response_format='json',
        )

        if resp.success and resp.content:
            try:
                return json.loads(resp.content)
            except json.JSONDecodeError:
                pass
        return None

    def _save_analysis(self, analysis: dict):
        """Save analysis to improvements directory."""
        filename = f"analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        path = os.path.join(self.improvements_dir, filename)
        with open(path, 'w') as f:
            json.dump(analysis, f, indent=2, default=str)
        logger.info(f"Improvement analysis saved to: {path}")

    def get_improvement_trend(self, limit: int = 10) -> list[dict]:
        """Get trend of evaluation scores over time."""
        if not self.memory_store:
            return []

        history = self.memory_store.get_evaluation_history(limit=limit * 20)
        if not history:
            return []

        # Group by date and average
        by_date = {}
        for h in history:
            date = h['created_at'][:10]
            by_date.setdefault(date, []).append(h['quality_score'])

        trend = []
        for date, scores in sorted(by_date.items())[-limit:]:
            trend.append({
                'date': date,
                'avg_score': round(sum(scores) / len(scores), 4),
                'count': len(scores),
            })
        return trend


def run_improvement_cycle(agent=None):
    """
    Run one full improvement cycle:
    1. Evaluate
    2. Analyze weaknesses
    3. Log proposals

    Args:
        agent: Agent instance (created if None).
    """
    logging.basicConfig(level=logging.INFO)

    from agent.tests.evaluator import AgentEvaluator

    if agent is None:
        from agent.core.agent import Agent
        agent = Agent()

    # Step 1: Evaluate
    print("Step 1: Running evaluation...")
    evaluator = AgentEvaluator(agent=agent)
    report = evaluator.run_evaluation()
    print(report.to_text())

    # Step 2: Analyze
    print("\nStep 2: Analyzing weaknesses...")
    improver = SelfImprover(
        model_router=agent.model_router,
        memory_store=agent.memory_system.store,
    )
    analysis = improver.analyze_evaluation(report.to_dict())

    # Step 3: Report
    print("\n=== Improvement Proposals ===")
    for h in analysis.get('hypotheses', []):
        print(f"  Hypothesis: {h}")
    for p in analysis.get('proposals', []):
        print(f"  [{p.get('priority', '?')}] {p.get('target', '?')}: {p.get('change', '?')}")
        print(f"         Expected: {p.get('expected_impact', '?')}")

    # Step 4: Trend
    trend = improver.get_improvement_trend()
    if trend:
        print("\n=== Score Trend ===")
        for t in trend:
            bar = '#' * int(t['avg_score'] * 20)
            print(f"  {t['date']} [{bar:20s}] {t['avg_score']:.0%} ({t['count']} tests)")

    return report, analysis


if __name__ == '__main__':
    run_improvement_cycle()
