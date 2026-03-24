"""
Executor Module - Manages tool execution and task processing
"""
from typing import Dict, Any, Optional
import asyncio
import json

class Executor:
    def __init__(self, tools: Dict[str, Any], memory_system: 'Memory', planner: 'Planner'):
        self.tools = tools
        self.memory = memory_system
        self.planner = planner
        self.running_tasks = {}
    
    async def execute_task(self, task: 'Task') -> Dict[str, Any]:
        """Execute a single task using appropriate tools"""
        try:
            # Update task status
            self.planner.update_task_status(task.id, 'in_progress')
            
            # Store task execution context
            execution_context = {
                'task_id': task.id,
                'task_description': task.description,
                'start_time': asyncio.get_event_loop().time(),
                'status': 'in_progress'
            }
            self.memory.store(f'execution_context_{task.id}', execution_context)
            
            # Select appropriate tool based on task description
            tool_name, tool_args = self._select_tool(task)
            
            if tool_name:
                # Execute the tool
                result = await self._execute_tool(tool_name, tool_args)
                
                # Update execution context
                execution_context['result'] = result
                execution_context['status'] = 'completed'
                execution_context['end_time'] = asyncio.get_event_loop().time()
                
                # Store final context
                self.memory.store(f'execution_context_{task.id}', execution_context)
                
                # Update task status
                self.planner.update_task_status(task.id, 'completed', result)
                
                return {
                    'success': True,
                    'result': result,
                    'task_id': task.id,
                    'tool_used': tool_name
                }
            else:
                error_msg = f"No appropriate tool found for task: {task.description}"
                
                # Update execution context with error
                execution_context['error'] = error_msg
                execution_context['status'] = 'failed'
                execution_context['end_time'] = asyncio.get_event_loop().time()
                
                # Store final context
                self.memory.store(f'execution_context_{task.id}', execution_context)
                
                # Update task status
                self.planner.update_task_status(task.id, 'failed', {'error': error_msg})
                
                return {
                    'success': False,
                    'error': error_msg,
                    'task_id': task.id
                }
                
        except Exception as e:
            error_msg = f"Error executing task {task.id}: {str(e)}"
            
            # Update execution context with error
            execution_context = {
                'task_id': task.id,
                'task_description': task.description,
                'status': 'failed',
                'error': error_msg,
                'end_time': asyncio.get_event_loop().time()
            }
            
            # Store final context
            self.memory.store(f'execution_context_{task.id}', execution_context)
            
            # Update task status
            self.planner.update_task_status(task.id, 'failed', {'error': error_msg})
            
            return {
                'success': False,
                'error': error_msg,
                'task_id': task.id
            }
    
    def _select_tool(self, task: 'Task') -> tuple:
        """Select the most appropriate tool for a task"""
        description = task.description.lower()
        
        # Map tasks to tools based on keywords
        if 'write' in description or 'create' in description or 'save' in description:
            if 'code' in description or 'file' in description or '.py' in description:
                return 'write', {'path': self._extract_path(description), 'content': ''}
            
        elif 'read' in description or 'load' in description:
            return 'read', {'path': self._extract_path(description)}
            
        elif 'execute' in description or 'run' in description or 'shell' in description:
            return 'exec', {'command': self._extract_command(description)}
            
        elif 'search' in description or 'find' in description:
            if 'web' in description:
                return 'web_search', {'query': description}
            elif 'memory' in description:
                return 'memory_search', {'query': description}
            
        elif 'analyze' in description:
            if 'image' in description:
                return 'image', {}
            elif 'pdf' in description:
                return 'pdf', {}
            
        elif 'generate' in description:
            if 'image' in description:
                return 'image_generate', {}
            elif 'speech' in description or 'tts' in description:
                return 'tts', {'text': ''}
                
        elif 'spawn' in description or 'agent' in description or 'subagent' in description:
            return 'sessions_spawn', {'task': description}
            
        elif 'status' in description and 'session' in description:
            return 'session_status', {}
            
        # Default to no tool
        return None, {}
    
    def _extract_path(self, description: str) -> str:
        """Extract file path from task description"""
        # Simple path extraction - in reality, this would be more sophisticated
        keywords = ['file', 'path', 'save', 'create', 'write']
        
        # Look for .py, .txt, .md extensions as hints
        for ext in ['.py', '.txt', '.md', '.json', '.yaml']:
            if ext in description:
                parts = description.split(ext)
                if len(parts) > 1:
                    return parts[0].strip() + ext
        
        # Default paths based on task type
        if 'config' in description:
            return 'config/app_config.py'
        elif 'main' in description or 'app' in description:
            return 'main.py'
        elif 'requirements' in description:
            return 'requirements.txt'
        
        return 'output.txt'
    
    def _extract_command(self, description: str) -> str:
        """Extract command from task description"""
        # Look for common command patterns
        if 'pip install' in description:
            return 'pip install -r requirements.txt'
        elif 'start server' in description:
            return 'python main.py'
        elif 'test' in description:
            return 'python -m pytest'
        
        return 'echo "No specific command identified"'
    
    async def _execute_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool with given arguments"""
        try:
            # In a real implementation, this would call the actual tool API
            # For now, we'll simulate tool execution
            
            # Store the tool call in memory
            tool_call = {
                'tool': tool_name,
                'arguments': tool_args,
                'timestamp': asyncio.get_event_loop().time()
            }
            
            self.memory.store(f'last_tool_call', tool_call)
            
            # Simulate different tool behaviors
            if tool_name == 'write':
                return {
                    'success': True,
                    'message': f"Successfully wrote to {tool_args.get('path', 'unknown path')}",
                    'path': tool_args.get('path')
                }
            
            elif tool_name == 'read':
                return {
                    'success': True,
                    'message': f"Successfully read from {tool_args.get('path', 'unknown path')}",
                    'path': tool_args.get('path'),
                    'content': 'File content would be here'
                }
            
            elif tool_name == 'exec':
                return {
                    'success': True,
                    'message': f"Command executed: {tool_args.get('command', 'unknown command')}",
                    'command': tool_args.get('command'),
                    'output': 'Command output would be here'
                }
            
            elif tool_name == 'web_search':
                return {
                    'success': True,
                    'message': f"Web search completed for: {tool_args.get('query', 'unknown query')}",
                    'query': tool_args.get('query'),
                    'results': ['Search result 1', 'Search result 2']
                }
            
            elif tool_name == 'memory_search':
                return {
                    'success': True,
                    'message': f"Memory search completed for: {tool_args.get('query', 'unknown query')}",
                    'query': tool_args.get('query'),
                    'results': ['Memory result 1', 'Memory result 2']
                }
            
            else:
                return {
                    'success': True,
                    'message': f"Tool executed: {tool_name}",
                    'tool': tool_name,
                    'result': 'Tool executed successfully'
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'tool': tool_name
            }
    
    async def execute_plan(self) -> Dict[str, Any]:
        """Execute the entire plan task by task"""
        plan_status = self.planner.get_plan_status()
        results = {
            'plan_total_tasks': plan_status['total'],
            'completed_tasks': [],
            'failed_tasks': [],
            'overall_status': 'completed',
            'start_time': asyncio.get_event_loop().time()
        }
        
        while True:
            # Get next task to execute
            next_task = self.planner.get_next_task()
            
            if not next_task:
                break
            
            # Execute the task
            result = await self.execute_task(next_task)
            
            # Store result
            if result['success']:
                results['completed_tasks'].append(result)
            else:
                results['failed_tasks'].append(result)
                results['overall_status'] = 'failed'
            
        
        results['end_time'] = asyncio.get_event_loop().time()
        results['execution_time'] = results['end_time'] - results['start_time']
        
        # Store results in memory
        self.memory.store('execution_results', results)
        
        return results