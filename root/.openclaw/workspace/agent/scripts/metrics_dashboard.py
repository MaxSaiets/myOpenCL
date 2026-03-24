#!/usr/bin/env python3
"""
Metrics dashboard for OpenClaw agent.
Reads evaluation history and memory stats, outputs a text-based dashboard.
"""

import json
import os
import sys

# Add parent paths for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_eval_history():
    """Load evaluation history."""
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'tests', 'evaluation_history.json',
    )
    if os.path.exists(path):
        with open(path, 'r') as f:
            return json.load(f)
    return []


def load_memory_stats():
    """Load memory store stats."""
    try:
        from agent.core.memory_store import MemoryStore
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            '..', 'memory.db',
        )
        if os.path.exists(db_path):
            store = MemoryStore(db_path)
            stats = store.get_stats()
            store.close()
            return stats
    except Exception:
        pass
    return {}


def render_dashboard():
    """Render the full dashboard."""
    history = load_eval_history()
    mem_stats = load_memory_stats()

    lines = []
    lines.append('=' * 60)
    lines.append('  OpenClaw Agent — Metrics Dashboard')
    lines.append('=' * 60)

    # Latest evaluation
    if history:
        latest = history[-1]
        lines.append(f"\n  Latest Evaluation: {latest.get('timestamp', '?')}")
        lines.append(f"  Overall Score:     {latest.get('overall_score', 0):.1f}/100")
        lines.append(f"  Tests:             {latest.get('total_tests', 0)} total | "
                     f"{latest.get('passed', 0)} passed | "
                     f"{latest.get('partial', 0)} partial | "
                     f"{latest.get('failed', 0)} failed")
        lines.append(f"  Duration:          {latest.get('duration_seconds', 0):.1f}s")

        # Category scores
        lines.append(f"\n  Category Scores:")
        for cat, score in sorted(latest.get('category_scores', {}).items()):
            bar_len = int(score / 5)
            bar = '#' * bar_len + '.' * (20 - bar_len)
            lines.append(f"    {cat:22s} [{bar}] {score:5.1f}")

        # Difficulty scores
        lines.append(f"\n  Difficulty Scores:")
        for diff, score in sorted(latest.get('difficulty_scores', {}).items()):
            lines.append(f"    {diff:22s} {score:5.1f}/100")
    else:
        lines.append("\n  No evaluations yet. Run: python -m agent.tests.evaluator")

    # Score trend
    if len(history) > 1:
        lines.append(f"\n  Score Trend (last {min(len(history), 10)} runs):")
        for entry in history[-10:]:
            score = entry.get('overall_score', 0)
            bar_len = int(score / 5)
            bar = '#' * bar_len + '.' * (20 - bar_len)
            ts = entry.get('timestamp', '?')[:16]
            lines.append(f"    {ts}  [{bar}] {score:5.1f}")

        # Trend direction
        scores = [e.get('overall_score', 0) for e in history[-5:]]
        if len(scores) >= 2:
            if scores[-1] > scores[0] + 5:
                trend = 'Improving ↑'
            elif scores[-1] < scores[0] - 5:
                trend = 'Declining ↓'
            else:
                trend = 'Stable →'
            lines.append(f"\n  Trend: {trend}")

    # Memory stats
    if mem_stats:
        lines.append(f"\n  Memory Store:")
        lines.append(f"    Total memories:  {mem_stats.get('total_memories', 0)}")
        by_cat = mem_stats.get('by_category', {})
        for cat, count in by_cat.items():
            lines.append(f"      {cat}: {count}")
        lines.append(f"    Avg importance:  {mem_stats.get('avg_importance', 0):.3f}")
        lines.append(f"    Avg decay:       {mem_stats.get('avg_decay', 0):.3f}")
        lines.append(f"    DB size:         {mem_stats.get('db_size_kb', 0)} KB")

    # Regressions from latest
    if history:
        latest = history[-1]
        regs = latest.get('regressions', [])
        imps = latest.get('improvements', [])
        if regs:
            lines.append(f"\n  Regressions ({len(regs)}):")
            for r in regs:
                lines.append(f"    - {r['test_id']}: {r['prev_score']:.0%} -> {r['new_score']:.0%}")
        if imps:
            lines.append(f"\n  Improvements ({len(imps)}):")
            for i in imps:
                lines.append(f"    + {i['test_id']}: {i['prev_score']:.0%} -> {i['new_score']:.0%}")

    lines.append(f"\n{'=' * 60}")
    return '\n'.join(lines)


if __name__ == '__main__':
    print(render_dashboard())
