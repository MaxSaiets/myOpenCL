"""
Task planning and decomposition module.
Handles breaking down complex tasks into executable steps.
"""

class Planner:
    """Handles task decomposition and planning."""
    
    def __init__(self, memory_system):
        """
        Initialize the planner with access to memory system.
        
        Args:
            memory_system: Reference to the memory system for context retrieval
        """
        self.memory_system = memory_system
        self.current_plan = None
        
    def create_plan(self, task_description):
        """
        Create a detailed execution plan for a given task.
        
        Args:
            task_description (str): High-level description of the task to plan
            
        Returns:
            dict: Structured plan with steps, dependencies, and priorities
        """
        # Extract key elements from task description
        task_elements = self._analyze_task(task_description)
        
        # Break down into subtasks
        subtasks = self._decompose_task(task_elements)
        
        # Establish dependencies and order
        ordered_steps = self._sequence_steps(subtasks)
        
        # Create final plan structure
        plan = {
            'original_task': task_description,
            'status': 'created',
            'steps': ordered_steps,
            'dependencies': self._identify_dependencies(ordered_steps),
            'priority': self._determine_priority(task_elements),
            'estimated_cost': self._estimate_cost(ordered_steps),
            'created_at': self._get_timestamp()
        }
        
        self.current_plan = plan
        return plan
    
    def _analyze_task(self, task_description):
        """
        Analyze task description to extract key elements.
        
        Args:
            task_description (str): Task to analyze
            
        Returns:
            dict: Extracted task elements (goals, constraints, requirements)
        """
        # This would use language processing to extract key elements
        # For now, returning a simplified structure
        return {
            'goals': [task_description],
            'constraints': [],
            'requirements': []
        }
    
    def _decompose_task(self, task_elements):
        """
        Break down task into smaller, manageable subtasks.
        
        Args:
            task_elements (dict): Analyzed task elements
            
        Returns:
            list: Sequence of subtasks
        """
        # Simplified decomposition - in practice, this would be more sophisticated
        return [
            {
                'id': f'step_{i+1:03d}',
                'description': goal,
                'type': 'execution',
                'status': 'pending',
                'required_tools': self._identify_required_tools(goal),
                'estimated_time': self._estimate_time(goal)
            }
            for i, goal in enumerate(task_elements['goals'])
        ]
    
    def _sequence_steps(self, subtasks):
        """
        Order subtasks based on dependencies and priorities.
        
        Args:
            subtasks (list): List of subtasks to sequence
            
        Returns:
            list: Ordered list of subtasks
        """
        # Simple sequential ordering for now
        # Future implementation would handle parallelization and dependencies
        for i, task in enumerate(subtasks):
            task['order'] = i + 1
        
        return subtasks
    
    def _identify_dependencies(self, ordered_steps):
        """
        Identify dependencies between steps.
        
        Args:
            ordered_steps (list): Ordered list of steps
            
        Returns:
            dict: Mapping of step IDs to their dependencies
        """
        dependencies = {}
        for i, step in enumerate(ordered_steps):
            step_id = step['id']
            if i > 0:
                # Simple sequential dependency
                dependencies[step_id] = [ordered_steps[i-1]['id']]
            else:
                dependencies[step_id] = []
        return dependencies
    
    def _determine_priority(self, task_elements):
        """
        Determine overall task priority.
        
        Args:
            task_elements (dict): Analyzed task elements
            
        Returns:
            str: Priority level (low, medium, high, critical)
        """
        # Simplified priority determination
        return 'medium'
    
    def _estimate_cost(self, ordered_steps):
        """
        Estimate resource cost of executing the plan.
        
        Args:
            ordered_steps (list): List of steps to execute
            
        Returns:
            dict: Cost estimates (time, computational resources, etc.)
        """
        total_time = sum(step.get('estimated_time', 1) for step in ordered_steps)
        
        return {
            'time_minutes': total_time,
            'complexity': len(ordered_steps),
            'tool_requirements': self._count_tool_requirements(ordered_steps)
        }
    
    def _identify_required_tools(self, goal_description):
        """
        Identify tools needed to accomplish a goal.
        
        Args:
            goal_description (str): Description of the goal
            
        Returns:
            list: Required tools for this step
        """
        # This would use more sophisticated analysis in practice
        # For now, returning a basic set
        return ['executor']
    
    def _estimate_time(self, goal_description):
        """
        Estimate time required to complete a step.
        
        Args:
            goal_description (str): Description of the goal
            
        Returns:
            int: Estimated time in minutes
        """
        # Simplified time estimation
        return 5
    
    def _count_tool_requirements(self, ordered_steps):
        """
        Count total tool requirements across all steps.
        
        Args:
            ordered_steps (list): List of steps to execute
            
        Returns:
            dict: Count of each required tool
        """
        tool_counts = {}
        for step in ordered_steps:
            for tool in step.get('required_tools', []):
                tool_counts[tool] = tool_counts.get(tool, 0) + 1
        return tool_counts
    
    def _get_timestamp(self):
        """
        Get current timestamp.
        
        Returns:
            str: ISO format timestamp
        """
        import datetime
        return datetime.datetime.now().isoformat()
    
    def update_plan_status(self, step_id, status, **kwargs):
        """
        Update the status of a specific step in the current plan.
        
        Args:
            step_id (str): ID of the step to update
            status (str): New status (pending, in_progress, completed, failed)
            **kwargs: Additional metadata to store with the update
        """
        if self.current_plan:
            for step in self.current_plan['steps']:
                if step['id'] == step_id:
                    step['status'] = status
                    step['updated_at'] = self._get_timestamp()
                    
                    # Add any additional metadata
                    for key, value in kwargs.items():
                        step[key] = value
                    
                    # Update overall plan status if needed
                    self._update_overall_status()
                    break
    
    def _update_overall_status(self):
        """
        Update the overall status of the plan based on step completion.
        """
        if not self.current_plan or not self.current_plan['steps']:
            return
            
        completed_steps = sum(1 for step in self.current_plan['steps'] if step['status'] == 'completed')
        total_steps = len(self.current_plan['steps'])
        
        if completed_steps == 0:
            self.current_plan['status'] = 'pending'
        elif completed_steps == total_steps:
            self.current_plan['status'] = 'completed'
        else:
            self.current_plan['status'] = 'in_progress'
            
        # Add progress percentage
        self.current_plan['progress'] = (completed_steps / total_steps) * 100
    
    def get_next_steps(self):
        """
        Get the next steps that can be executed (all dependencies met).
        
        Returns:
            list: Steps ready for execution
        """
        if not self.current_plan:
            return []
            
        ready_steps = []
        for step in self.current_plan['steps']:
            if step['status'] == 'pending' and self._dependencies_satisfied(step['id']):
                ready_steps.append(step)
                
        return ready_steps
    
    def _dependencies_satisfied(self, step_id):
        """
        Check if all dependencies for a step have been completed.
        
        Args:
            step_id (str): ID of the step to check
            
        Returns:
            bool: True if all dependencies are satisfied
        """
        dependencies = self.current_plan['dependencies'].get(step_id, [])
        if not dependencies:
            return True
            
        # Check if all dependency steps are completed
        completed_ids = {step['id'] for step in self.current_plan['steps'] if step['status'] == 'completed'}
        return all(dep_id in completed_ids for dep_id in dependencies)
    
    def get_plan_summary(self):
        """
        Get a concise summary of the current plan.
        
        Returns:
            dict: Summary information about the plan
        """
        if not self.current_plan:
            return None
            
        return {
            'task': self.current_plan['original_task'],
            'status': self.current_plan['status'],
            'progress': self.current_plan.get('progress', 0),
            'total_steps': len(self.current_plan['steps']),
            'completed_steps': sum(1 for step in self.current_plan['steps'] if step['status'] == 'completed'),
            'estimated_time': self.current_plan['estimated_cost']['time_minutes'],
            'priority': self.current_plan['priority']
        }
    
    def validate_plan(self):
        """
        Validate the current plan for correctness and completeness.
        
        Returns:
            dict: Validation results with success flag and messages
        """
        if not self.current_plan:
            return {
                'valid': False,
                'messages': ['No plan exists to validate']
            }
            
        messages = []
        
        # Check for circular dependencies
        if self._has_circular_dependencies():
            messages.append('Circular dependencies detected in plan')
            
        # Verify all steps have unique IDs
        step_ids = [step['id'] for step in self.current_plan['steps']]
        if len(step_ids) != len(set(step_ids)):
            messages.append('Duplicate step IDs found in plan')
            
        # Check that all dependency references are valid
        all_ids = set(step_ids)
        for step_id, deps in self.current_plan['dependencies'].items():
            for dep_id in deps:
                if dep_id not in all_ids:
                    messages.append(f'Step {step_id} references non-existent dependency {dep_id}')
                    
        return {
            'valid': len(messages) == 0,
            'messages': messages
        }
    
    def _has_circular_dependencies(self):
        """
        Detect circular dependencies in the plan.
        
        Returns:
            bool: True if circular dependencies exist
        """
        # Simple cycle detection using DFS
        visited = set()
        rec_stack = set()
        
        def has_cycle(node):
            if node not in visited:
                visited.add(node)
                rec_stack.add(node)
                
                # Check all neighbors (dependencies)
                for neighbor in self.current_plan['dependencies'].get(node, []):
                    if neighbor not in visited and has_cycle(neighbor):
                        return True
                    elif neighbor in rec_stack:
                        return True
                        
                rec_stack.remove(node)
                
            return False
            
        # Check each node
        for node in self.current_plan['dependencies']:
            if has_cycle(node):
                return True
                
        return False