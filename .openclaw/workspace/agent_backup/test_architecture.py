#!/usr/bin/env python3
"""
Test script for the improved agent architecture
"""

import sys
import os

# Add the agent directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'agent'))

from core.memory import Memory
from core.planner import Planner
from core.executor import Executor

# Mock tools for testing
mock_tools = {
    'write': lambda args: {'success': True, 'message': f"Wrote to {args.get('path', 'unknown')}"},
    'read': lambda args: {'success': True, 'content': 'Mock file content', 'path': args.get('path')},
    'exec': lambda args: {'success': True, 'output': f"Executed: {args.get('command', 'unknown')}"},
    'web_search': lambda args: {'success': True, 'results': ['Result 1', 'Result 2']},
    'memory_search': lambda args: {'success': True, 'results': ['Memory result 1']},
}

def main():
    print("Testing Improved Agent Architecture")
    print("=" * 40)
    
    # Initialize memory system
    print("1. Initializing memory system...")
    memory = Memory()
    print("   Memory system initialized.")
    
    # Initialize planner
    print("2. Initializing planner...")
    planner = Planner(memory)
    print("   Planner initialized.")
    
    # Create a plan for a simple goal
    goal = "Create a simple Python script that prints 'Hello, World!'"
    print(f"3. Creating plan for goal: '{goal}'")
    plan = planner.create_plan(goal)
    print(f"   Plan created with {len(plan)} tasks:")
    for i, task in enumerate(plan, 1):
        print(f"     {i}. {task.description} (ID: {task.id})")
    
    # Initialize executor
    print("4. Initializing executor...")
    executor = Executor(mock_tools, memory, planner)
    print("   Executor initialized.")
    
    # Execute the plan
    print("5. Executing plan...")
    import asyncio
    results = asyncio.run(executor.execute_plan())
    
    # Print results
    print("6. Execution results:")
    print(f"   Overall status: {results['overall_status']}")
    print(f"   Completed tasks: {len(results['completed_tasks'])}")
    print(f"   Failed tasks: {len(results['failed_tasks'])}")
    print(f"   Execution time: {results.get('execution_time', 0):.2f} seconds")
    
    if results['completed_tasks']:
        print("\n   Completed task details:")
        for task_result in results['completed_tasks']:
            print(f"     - Task {task_result['task_id']}: {task_result.get('tool_used', 'unknown tool')}")
    
    if results['failed_tasks']:
        print("\n   Failed task details:")
        for task_result in results['failed_tasks']:
            print(f"     - Task {task_result['task_id']}: {task_result.get('error', 'unknown error')}")
    
    # Show memory contents
    print("\n7. Memory contents after execution:")
    context = memory.get_context()
    print(f"   Context keys: {list(context.keys())}")
    
    # Show plan status
    plan_status = planner.get_plan_status()
    print(f"   Plan progress: {plan_status['progress_percentage']:.1f}%")
    
    print("\nTest completed successfully!")

if __name__ == "__main__":
    main()