"""
Planning Module - Manages task decomposition and execution planning
"""

class Task:
    def __init__(self, id, description, dependencies=None, priority=1):
        self.id = id
        self.description = description
        self.dependencies = dependencies or []
        self.priority = priority
        self.status = 'pending'  # pending, in_progress, completed, failed
        self.result = None


class Planner:
    def __init__(self, memory_system):
        self.memory = memory_system
        self.tasks = {}
        self.execution_plan = []
    
    def create_plan(self, goal):
        """Create execution plan for a given goal"""
        # Store the original goal
        self.memory.store('current_goal', goal)
        
        # Break down the goal into subtasks
        tasks = self._decompose_goal(goal)
        
        # Organize tasks with dependencies and priorities
        self.execution_plan = self._organize_tasks(tasks)
        
        # Store plan in memory
        self.memory.store('execution_plan', self.execution_plan)
        
        return self.execution_plan
    
    def _decompose_goal(self, goal):
        """Break down complex goal into smaller tasks"""
        # This would use LLM to decompose the goal
        # For now, using simple rule-based decomposition
        
        if "improve architecture" in goal.lower():
            return [
                Task('1', 'Analyze current architecture limitations'),
                Task('2', 'Research best practices for agent architecture'),
                Task('3', 'Design improved architecture components'),
                Task('4', 'Create implementation roadmap'),
                Task('5', 'Prioritize implementation steps')
            ]
        
        elif "develop application" in goal.lower():
            return [
                Task('1', 'Define application requirements'),
                Task('2', 'Design system architecture'),
                Task('3', 'Set up development environment'),
                Task('4', 'Implement core functionality'),
                Task('5', 'Create tests and documentation')
            ]
        
        else:
            # Default decomposition
            return [
                Task('1', f'Analyze requirements for: {goal}'),
                Task('2', 'Create implementation plan'),
                Task('3', 'Execute implementation plan'),
                Task('4', 'Test and validate results')
            ]
    
    def _organize_tasks(self, tasks):
        """Organize tasks with proper dependencies and priorities"""
        # Set up dependencies (later tasks depend on earlier ones)
        for i in range(1, len(tasks)):
            tasks[i].dependencies.append(tasks[i-1].id)
        
        # Sort by priority (higher priority first)
        return sorted(tasks, key=lambda x: x.priority, reverse=True)
    
    def get_next_task(self):
        """Get the next task to execute"""
        for task in self.execution_plan:
            if task.status == 'pending':
                # Check if all dependencies are completed
                if self._dependencies_met(task):
                    return task
        return None
    
    def _dependencies_met(self, task):
        """Check if all dependencies for a task are completed"""
        for dep_id in task.dependencies:
            dep_task = self.tasks.get(dep_id)
            if dep_task and dep_task.status != 'completed':
                return False
        return True
    
    def update_task_status(self, task_id, status, result=None):
        """Update task status and store result"""
        if task_id in self.tasks:
            self.tasks[task_id].status = status
            if result:
                self.tasks[task_id].result = result
            
        # Update memory
        self.memory.store(f'task_status_{task_id}', status)
        
    def get_plan_status(self):
        """Get current status of the execution plan"""
        total = len(self.execution_plan)
        completed = len([t for t in self.execution_plan if t.status == 'completed'])
        pending = len([t for t in self.execution_plan if t.status == 'pending'])
        in_progress = len([t for t in self.execution_plan if t.status == 'in_progress'])
        failed = len([t for t in self.execution_plan if t.status == 'failed'])
        
        return {
            'total': total,
            'completed': completed,
            'pending': pending,
            'in_progress': in_progress,
            'failed': failed,
            'progress_percentage': (completed / total) * 100 if total > 0 else 0
        }