"""
Task execution module.
Handles tool calls and manages execution of planned steps.
"""

class Executor:
    """Manages the execution of tasks and tool calls."""
    
    def __init__(self, tool_registry, memory_system):
        """
        Initialize the executor with access to tools and memory.
        
        Args:
            tool_registry (dict): Registry of available tools
            memory_system: Reference to the memory system
        """
        self.tool_registry = tool_registry
        self.memory_system = memory_system
        self.execution_history = []
        self.active_executions = {}
        
    def execute_step(self, step, context=None):
        """
        Execute a single step from the plan.
        
        Args:
            step (dict): The step to execute
            context (dict, optional): Additional context for execution
            
        Returns:
            dict: Execution result with success status and output
        """
        step_id = step['id']
        
        # Record start of execution
        execution_record = {
            'step_id': step_id,
            'start_time': self._get_timestamp(),
            'status': 'in_progress',
            'attempt': 1,
            'tool_calls': []
        }
        
        self.active_executions[step_id] = execution_record
        
        try:
            # Prepare execution context
            execution_context = self._build_execution_context(step, context)
            
            # Execute the step using appropriate tools
            result = self._perform_execution(step, execution_context)
            
            # Update record with results
            execution_record['status'] = 'completed' if result['success'] else 'failed'
            execution_record['end_time'] = self._get_timestamp()
            execution_record['result'] = result
            execution_record['duration'] = self._calculate_duration(
                execution_record['start_time'], 
                execution_record['end_time']
            )
            
            # Add to execution history
            self.execution_history.append(execution_record.copy())
            del self.active_executions[step_id]
            
            return result
            
        except Exception as e:
            # Handle unexpected errors
            error_result = {
                'success': False,
                'error_type': 'execution_error',
                'error_message': str(e),
                'traceback': self._get_traceback()
            }
            
            execution_record['status'] = 'failed'
            execution_record['end_time'] = self._get_timestamp()
            execution_record['result'] = error_result
            execution_record['duration'] = self._calculate_duration(
                execution_record['start_time'], 
                execution_record['end_time']
            )
            
            self.execution_history.append(execution_record.copy())
            del self.active_executions[step_id]
            
            return error_result
    
    def _build_execution_context(self, step, additional_context=None):
        """
        Build the execution context for a step.
        
        Args:
            step (dict): The step being executed
            additional_context (dict, optional): Additional context to include
            
        Returns:
            dict: Complete execution context
        """
        context = {
            'step': step,
            'memory': self.memory_system.get_relevant_memories(step['description']),
            'recent_executions': self._get_recent_executions(),
            'system_status': self._get_system_status()
        }
        
        # Add additional context if provided
        if additional_context:
            context.update(additional_context)
            
        return context
    
    def _perform_execution(self, step, execution_context):
        """
        Perform the actual execution of a step.
        
        Args:
            step (dict): The step to execute
            execution_context (dict): Context for execution
            
        Returns:
            dict: Execution result
        """
        # Get required tools for this step
        required_tools = step.get('required_tools', ['default'])
        
        # Execute with each required tool
        tool_results = []
        for tool_name in required_tools:
            if tool_name in self.tool_registry:
                try:
                    # Call the tool with appropriate arguments
                    tool_result = self._call_tool(tool_name, step, execution_context)
                    tool_results.append(tool_result)
                    
                    # Record tool call in execution history
                    if 'active_executions' in self.__dict__:
                        current_step = self.active_executions.get(step['id'])
                        if current_step:
                            current_step['tool_calls'].append({
                                'tool': tool_name,
                                'success': tool_result['success'],
                                'timestamp': self._get_timestamp(),
                                'input': tool_result.get('input', {}),
                                'output': tool_result.get('output', None)
                            })
                except Exception as e:
                    tool_results.append({
                        'success': False,
                        'tool': tool_name,
                        'error': str(e)
                    })
            else:
                tool_results.append({
                    'success': False,
                    'tool': tool_name,
                    'error': f"Tool '{tool_name}' not found in registry"
                })
        
        # Consolidate results
        all_successful = all(result.get('success', False) for result in tool_results)
        
        return {
            'success': all_successful,
            'step_id': step['id'],
            'tool_results': tool_results,
            'output': self._consolidate_outputs(tool_results),
            'metrics': self._gather_metrics(tool_results)
        }
    
    def _call_tool(self, tool_name, step, context):
        """
        Call a specific tool with appropriate arguments.
        
        Args:
            tool_name (str): Name of the tool to call
            step (dict): The current step
            context (dict): Execution context
            
        Returns:
            dict: Result of the tool call
        """
        tool = self.tool_registry[tool_name]
        
        # Extract tool-specific arguments from context or step
        tool_args = self._extract_tool_arguments(tool_name, step, context)
        
        # Record the tool call
        tool_call_record = {
            'tool': tool_name,
            'input': tool_args.copy() if tool_args else {},
            'timestamp': self._get_timestamp()
        }
        
        try:
            # Execute the tool
            result = tool(**tool_args) if tool_args else tool()
            
            # Record successful completion
            tool_call_record['success'] = True
            tool_call_record['output'] = result
            tool_call_record['end_time'] = self._get_timestamp()
            
            return {
                'success': True,
                'tool': tool_name,
                'input': tool_args,
                'output': result
            }
            
        except Exception as e:
            # Record failure
            tool_call_record['success'] = False
            tool_call_record['error'] = str(e)
            tool_call_record['end_time'] = self._get_timestamp()
            
            return {
                'success': False,
                'tool': tool_name,
                'error': str(e)
            }
    
    def _extract_tool_arguments(self, tool_name, step, context):
        """
        Extract appropriate arguments for a tool call.
        
        Args:
            tool_name (str): Name of the tool
            step (dict): Current step
            context (dict): Execution context
            
        Returns:
            dict: Arguments for the tool call
        """
        # This would be more sophisticated in practice
        # For now, returning a basic set of arguments
        base_args = {
            'task': step['description'],
            'step_id': step['id']
        }
        
        # Add context-specific arguments based on tool type
        if tool_name == 'read':
            # Extract file paths from step description
            base_args['path'] = self._extract_file_path(step['description'])
            
        elif tool_name == 'write':
            # Extract content and path information
            base_args['path'] = self._extract_file_path(step['description'])
            base_args['content'] = self._extract_content(step['description'])
            
        elif tool_name == 'exec':
            # Extract command from step description
            base_args['command'] = self._extract_command(step['description'])
            
        return base_args
    
    def _extract_file_path(self, description):
        """
        Extract file path from a task description.
        
        Args:
            description (str): Task description
            
        Returns:
            str: Extracted file path, or None if not found
        """
        # Simplified path extraction
        # In practice, this would use more sophisticated NLP
        keywords = ['file', 'path', 'write to', 'read from']
        for keyword in keywords:
            if keyword in description.lower():
                # Simple heuristic to find what looks like a path
                parts = description.split(keyword)
                if len(parts) > 1:
                    # Look for something that resembles a path
                    possible_path = parts[1].strip().split()[0]
                    if '/' in possible_path or '.' in possible_path:
                        return possible_path
        return None
    
    def _extract_content(self, description):
        """
        Extract content to write from a task description.
        
        Args:
            description (str): Task description
            
        Returns:
            str: Extracted content, or None if not found
        """
        # Simplified content extraction
        # This would be more sophisticated in practice
        write_indicators = ['write', 'create', 'generate']
        for indicator in write_indicators:
            if indicator in description.lower():
                parts = description.split(indicator)
                if len(parts) > 1:
                    # Look for content after the indicator
                    content_part = parts[1].strip()
                    # Remove any file path references
                    if 'to file' in content_part:
                        content_part = content_part.split('to file')[0]
                    elif 'in' in content_part:
                        content_part = content_part.split('in')[0]
                    return content_part.strip()
        return None
    
    def _extract_command(self, description):
        """
        Extract command to execute from a task description.
        
        Args:
            description (str): Task description
            
        Returns:
            str: Extracted command, or None if not found
        """
        # Simplified command extraction
        exec_indicators = ['run', 'execute', 'command', 'shell']
        for indicator in exec_indicators:
            if indicator in description.lower():
                parts = description.split(indicator)
                if len(parts) > 1:
                    # Look for the command after the indicator
                    command_part = parts[1].strip()
                    # Remove any explanatory text
                    if 'and' in command_part:
                        command_part = command_part.split('and')[0]
                    elif 'then' in command_part:
                        command_part = command_part.split('then')[0]
                    return command_part.strip()
        return None
    
    def _consolidate_outputs(self, tool_results):
        """
        Consolidate outputs from multiple tools.
        
        Args:
            tool_results (list): List of tool execution results
            
        Returns:
            dict or str: Consolidated output
        """
        # For now, just return the outputs as-is
        # Future implementation would handle more sophisticated consolidation
        successful_outputs = [
            result['output'] for result in tool_results 
            if result.get('success', False) and 'output' in result
        ]
        
        if len(successful_outputs) == 1:
            return successful_outputs[0]
        elif successful_outputs:
            return successful_outputs
        else:
            return None
    
    def _gather_metrics(self, tool_results):
        """
        Gather execution metrics from tool results.
        
        Args:
            tool_results (list): List of tool execution results
            
        Returns:
            dict: Execution metrics
        """
        metrics = {
            'tool_calls': len(tool_results),
            'successful_calls': sum(1 for r in tool_results if r.get('success', False)),
            'failed_calls': sum(1 for r in tool_results if not r.get('success', False)),
            'execution_time': 0,  # Would be calculated in practice
            'resource_usage': {}  # Would be populated in practice
        }
        
        return metrics
    
    def _get_recent_executions(self, count=5):
        """
        Get recent execution history.
        
        Args:
            count (int): Number of recent executions to return
            
        Returns:
            list: Most recent execution records
        """
        return self.execution_history[-count:] if self.execution_history else []
    
    def _get_system_status(self):
        """
        Get current system status.
        
        Returns:
            dict: System status information
        """
        return {
            'active_executions': len(self.active_executions),
            'total_executions': len(self.execution_history),
            'success_rate': self._calculate_success_rate(),
            'system_time': self._get_timestamp()
        }
    
    def _calculate_success_rate(self):
        """
        Calculate overall execution success rate.
        
        Returns:
            float: Success rate as percentage
        """
        if not self.execution_history:
            return 0.0
            
        successful = sum(1 for exec in self.execution_history if exec['status'] == 'completed')
        return (successful / len(self.execution_history)) * 100
    
    def _get_timestamp(self):
        """
        Get current timestamp.
        
        Returns:
            str: ISO format timestamp
        """
        import datetime
        return datetime.datetime.now().isoformat()
    
    def _calculate_duration(self, start_time, end_time):
        """
        Calculate duration between two timestamps.
        
        Args:
            start_time (str): Start timestamp
            end_time (str): End timestamp
            
        Returns:
            float: Duration in seconds
        """
        from datetime import datetime
        start = datetime.fromisoformat(start_time)
        end = datetime.fromisoformat(end_time)
        return (end - start).total_seconds()
    
    def _get_traceback(self):
        """
        Get current traceback information.
        
        Returns:
            str: Traceback string
        """
        import traceback
        return traceback.format_exc()