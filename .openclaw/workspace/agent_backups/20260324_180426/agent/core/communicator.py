"""
Communication module.
Handles user interaction and response formatting.
"""

class Communicator:
    """Manages communication with the user and response formatting."""
    
    def __init__(self, memory_system, personality=None):
        """
        Initialize the communicator with access to memory.
        
        Args:
            memory_system: Reference to the memory system
            personality (dict, optional): Personality configuration
        """
        self.memory_system = memory_system
        self.personality = personality or self._default_personality()
        self.conversation_history = []
        
    def _default_personality(self):
        """Define default personality traits."""
        return {
            'tone': 'professional',
            'formality': 'medium',
            'verbosity': 'concise',
            'style': 'direct',
            'response_structure': 'clear_sections',
            'technical_level': 'advanced'
        }
    
    def set_personality(self, personality_traits):
        """
        Update communicator personality traits.
        
        Args:
            personality_traits (dict): New personality configuration
        """
        self.personality.update(personality_traits)
    
    def receive_message(self, message, sender_info=None):
        """
        Process incoming message from user.
        
        Args:
            message (str): The message content
            sender_info (dict, optional): Information about the sender
            
        Returns:
            dict: Structured message data
        """
        # Store in conversation history
        message_data = {
            'content': message,
            'sender': sender_info or {'role': 'user'},
            'timestamp': self._get_timestamp(),
            'processed': False
        }
        
        self.conversation_history.append(message_data)
        
        # Update memory with interaction
        self.memory_system.store_memory(
            'conversation_context',
            'last_interaction',
            message,
            {'timestamp': message_data['timestamp']}
        )
        
        return message_data
    
    def format_response(self, content, response_type='general', context=None):
        """
        Format a response according to personality and context.
        
        Args:
            content (str or dict): Content to include in the response
            response_type (str): Type of response (general, error, status, etc.)
            context (dict, optional): Additional context for formatting
            
        Returns:
            str: Formatted response
        """
        # Determine formatting based on personality and response type
        formatter = getattr(self, f"_format_{response_type}_response", self._format_general_response)
        return formatter(content, context)
    
    def _format_general_response(self, content, context):
        """Format a general response."""
        if isinstance(content, dict):
            return self._format_structured_response(content)
        else:
            return self._apply_personality_formatting(str(content))
    
    def _format_structured_response(self, content):
        """Format a structured response with sections."""
        lines = []
        
        # Add main content if present
        if 'content' in content:
            lines.append(self._apply_personality_formatting(content['content']))
            lines.append("")  # Add spacing
        
        # Add sections if present
        if 'sections' in content:
            for section_title, section_content in content['sections'].items():
                lines.append(f"### {section_title}")
                if isinstance(section_content, list):
                    for item in section_content:
                        lines.append(f"- {item}")
                else:
                    lines.append(str(section_content))
                lines.append("")  # Add spacing
        
        # Add metadata if present
        if 'metadata' in content:
            lines.append("### Metadata")
            for key, value in content['metadata'].items():
                lines.append(f"- {key}: {value}")
            lines.append("")
        
        return "\n".join(lines).strip()
    
    def _format_error_response(self, content, context):
        """Format an error response."""
        error_msg = "I encountered an issue while processing your request:"
        
        if isinstance(content, dict):
            error_type = content.get('error_type', 'unknown')
            error_message = content.get('error_message', 'No details provided')
            
            details = [
                f"**Error Type:** {error_type}",
                f"**Message:** {error_message}"
            ]
            
            # Add traceback if available and appropriate
            if content.get('traceback') and self.personality.get('verbosity') == 'detailed':
                details.append(f"**Traceback:**\n```
{content['traceback']}\n```")
            
            return f"{error_msg}\n\n" + "\n".join(details)
        else:
            return f"{error_msg} {str(content)}"
    
    def _format_status_response(self, content, context):
        """Format a status response."""
        if not isinstance(content, dict):
            return self._apply_personality_formatting(str(content))
        
        lines = ["# System Status"]
        
        # Add overall status
        if 'status' in content:
            lines.append(f"**Status:** {content['status']}")
        
        # Add progress if available
        if 'progress' in content:
            lines.append(f"**Progress:** {content['progress']}%")
        
        # Add detailed metrics
        if 'metrics' in content:
            lines.append("")
            lines.append("## Metrics")
            for key, value in content['metrics'].items():
                lines.append(f"- {key.replace('_', ' ').title()}: {value}")
        
        # Add recent activity
        if 'recent_activity' in content:
            lines.append("")
            lines.append("## Recent Activity")
            for activity in content['recent_activity']:
                lines.append(f"- {activity}")
        
        return "\n".join(lines)
    
    def _apply_personality_formatting(self, text):
        """
        Apply personality-based formatting to text.
        
        Args:
            text (str): Text to format
            
        Returns:
            str: Formatted text
        """
        # Apply formatting based on personality traits
        formatted = text
        
        # Adjust verbosity
        if self.personality.get('verbosity') == 'concise':
            # Ensure no unnecessary verbosity
            formatted = self._ensure_concise(formatted)
        elif self.personality.get('verbosity') == 'detailed':
            # Add more detail if appropriate
            formatted = self._enhance_with_details(formatted)
        
        # Apply tone
        tone = self.personality.get('tone', 'professional')
        if tone == 'professional':
            formatted = self._apply_professional_tone(formatted)
        elif tone == 'friendly':
            formatted = self._apply_friendly_tone(formatted)
            
        # Apply formality
        formality = self.personality.get('formality', 'medium')
        if formality == 'formal':
            formatted = self._apply_formal_language(formatted)
        elif formality == 'casual':
            formatted = self._apply_casual_language(formatted)
            
        return formatted
    
    def _ensure_concise(self, text):
        """Ensure text is concise."""
        # This would use more sophisticated text processing in practice
        # For now, just ensure it's not overly verbose
        sentences = text.split('. ')
        if len(sentences) > 3:
            # Summarize if too many sentences
            return '. '.join(sentences[:3]) + "..."
        return text
    
    def _enhance_with_details(self, text):
        """Enhance text with additional details."""
        # This would add relevant details from memory
        # For now, just return as-is
        return text
    
    def _apply_professional_tone(self, text):
        """Apply professional tone to text."""
        # Ensure professional vocabulary
        replacements = {
            "I'll": "I will",
            "can't": "cannot",
            "don't": "do not",
            "won't": "will not"
        }
        
        for informal, formal in replacements.items():
            text = text.replace(informal, formal)
            
        return text
    
    def _apply_friendly_tone(self, text):
        """Apply friendly tone to text."""
        # Make language more approachable
        replacements = {
            "I will": "I'll",
            "cannot": "can't",
            "do not": "don't",
            "will not": "won't"
        }
        
        for formal, informal in replacements.items():
            text = text.replace(formal, informal)
            
        return text
    
    def _apply_formal_language(self, text):
        """Apply formal language patterns."""
        # Use more formal constructions
        if not text.startswith("Dear") and "you" in text.lower():
            text = "Respected user, " + text
            
        return text
    
    def _apply_casual_language(self, text):
        """Apply casual language patterns."""
        # Use more casual constructions
        casual_openings = ["Hey", "Hi", "Hello"]
        if not any(text.startswith(opening) for opening in casual_openings):
            text = "Hi there, " + text
            
        return text
    
    def generate_follow_up(self, context=None):
        """
        Generate appropriate follow-up question or statement.
        
        Args:
            context (dict, optional): Context for generating follow-up
            
        Returns:
            str: Follow-up message
        """
        # This would use more sophisticated logic in practice
        # For now, return a simple follow-up
        return "Is there anything else I can help you with?"
    
    def log_interaction(self, user_message, response, metrics=None):
        """
        Log an interaction for memory and learning.
        
        Args:
            user_message (str): The user's message
            response (str): The agent's response
            metrics (dict, optional): Performance metrics
        """
        interaction_data = {
            'user_message': user_message,
            'response': response,
            'timestamp': self._get_timestamp(),
            'metrics': metrics or {}
        }
        
        # Store in conversation history
        self.conversation_history.append(interaction_data)
        
        # Update memory system
        self.memory_system.store_memory(
            'conversation_history',
            'interaction',
            interaction_data['timestamp'],
            interaction_data
        )
        
        # Update task history
        self.memory_system.store_memory(
            'task_history',
            'last_interaction',
            user_message,
            {'timestamp': interaction_data['timestamp']}
        )
    
    def _get_timestamp(self):
        """
        Get current timestamp.
        
        Returns:
            str: ISO format timestamp
        """
        import datetime
        return datetime.datetime.now().isoformat()
    
    def get_interaction_summary(self):
        """
        Get a summary of recent interactions.
        
        Returns:
            dict: Summary of recent interactions
        """
        if not self.conversation_history:
            return {'total_interactions': 0, 'recent_messages': []}
            
        return {
            'total_interactions': len(self.conversation_history),
            'recent_messages': self.conversation_history[-5:],  # Last 5 messages
            'last_interaction_time': self.conversation_history[-1]['timestamp']
        }