"""
Memory management module.
Handles persistent storage and retrieval of context, preferences, and knowledge.
"""

class MemorySystem:
    """Manages the agent's memory and knowledge storage."""
    
    def __init__(self, storage_path="MEMORY.md"):
        """
        Initialize the memory system.
        
        Args:
            storage_path (str): Path to the memory storage file
        """
        self.storage_path = storage_path
        self.memory_data = {}
        self._load_memory()
        
    def _load_memory(self):
        """Load memory data from storage file."""
        try:
            import json
            import os
            
            if os.path.exists(self.storage_path):
                with open(self.storage_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    
                    # Handle both JSON and markdown-formatted memory files
                    if content.startswith('{') and content.endswith('}'):
                        # JSON format
                        self.memory_data = json.loads(content)
                    else:
                        # Markdown format - needs parsing
                        self.memory_data = self._parse_markdown_memory(content)
            else:
                # Initialize with default structure
                self.memory_data = {
                    'architecture_decisions': [],
                    'user_preferences': {},
                    'task_history': [],
                    'system_configuration': {},
                    'development_roadmap': [],
                    'notes': []
                }
                
        except Exception as e:
            print(f"Error loading memory: {e}")
            # Initialize with default structure on error
            self.memory_data = {
                'architecture_decisions': [],
                'user_preferences': {},
                'task_history': [],
                'system_configuration': {},
                'development_roadmap': [],
                'notes': []
            }
    
    def _parse_markdown_memory(self, content):
        """
        Parse markdown-formatted memory content into structured data.
        
        Args:
            content (str): Markdown content to parse
            
        Returns:
            dict: Structured memory data
        """
        lines = content.split('\n')
        memory_data = {
            'architecture_decisions': [],
            'user_preferences': {},
            'task_history': [],
            'system_configuration': {},
            'development_roadmap': [],
            'notes': []
        }
        
        current_section = None
        section_mapping = {
            '## Architecture Decisions': 'architecture_decisions',
            '## User Preferences': 'user_preferences',
            '## Task History': 'task_history',
            '## System Configuration': 'system_configuration',
            '## Development Roadmap': 'development_roadmap',
            '## Notes': 'notes'
        }
        
        for line in lines:
            # Check for section headers
            if line.startswith('## '):
                current_section = section_mapping.get(line.strip())
                continue
                
            # Parse content based on current section
            if current_section and line.strip():
                if current_section == 'architecture_decisions' and line.startswith('- '):
                    # Parse architecture decision
                    decision_text = line[2:].strip()
                    if ': ' in decision_text:
                        key, value = decision_text.split(': ', 1)
                        memory_data['architecture_decisions'].append({
                            'field': key,
                            'value': value
                        })
                
                elif current_section == 'user_preferences' and line.startswith('- '):
                    # Parse user preference
                    pref_text = line[2:].strip()
                    if ': ' in pref_text:
                        key, value = pref_text.split(': ', 1)
                        memory_data['user_preferences'][key.lower().replace(' ', '_')] = value
                
                elif current_section == 'task_history' and line.startswith('- '):
                    # Parse task history item
                    task_text = line[2:].strip()
                    if ': ' in task_text:
                        key, value = task_text.split(': ', 1)
                        memory_data['task_history'].append({
                            'field': key,
                            'value': value
                        })
                
                elif current_section == 'system_configuration' and line.startswith('- '):
                    # Parse system configuration
                    config_text = line[2:].strip()
                    if ': ' in config_text:
                        key, value = config_text.split(': ', 1)
                        memory_data['system_configuration'][key.lower().replace(' ', '_')] = value
                
                elif current_section == 'development_roadmap' and line.startswith('1. '):
                    # Parse development roadmap item
                    roadmap_item = line[3:].strip()
                    memory_data['development_roadmap'].append({
                        'status': 'pending',
                        'description': roadmap_item
                    })
                
                elif current_section == 'notes':
                    # Collect notes
                    memory_data['notes'].append(line.strip())
        
        return memory_data
    
    def _save_memory(self):
        """Save memory data to storage file."""
        try:
            import json
            
            # Convert structured data back to markdown format for compatibility
            content = "# Memory System\n\n"
            
            # Architecture Decisions
            content += "## Architecture Decisions\n\n"
            for item in self.memory_data.get('architecture_decisions', []):
                content += f"- {item.get('field', '')}: {item.get('value', '')}\n"
            
            # User Preferences
            content += "\n## User Preferences\n\n"
            for key, value in self.memory_data.get('user_preferences', {}).items():
                formatted_key = key.replace('_', ' ').title()
                content += f"- {formatted_key}: {value}\n"
            
            # Task History
            content += "\n## Task History\n\n"
            for item in self.memory_data.get('task_history', []):
                content += f"- {item.get('field', '')}: {item.get('value', '')}\n"
            
            # System Configuration
            content += "\n## System Configuration\n\n"
            for key, value in self.memory_data.get('system_configuration', {}).items():
                formatted_key = key.replace('_', ' ').title()
                content += f"- {formatted_key}: {value}\n"
            
            # Development Roadmap
            content += "\n## Development Roadmap\n\n"
            for item in self.memory_data.get('development_roadmap', []):
                status_mark = "[x]" if item.get('status') == 'completed' else "[ ]"
                content += f"{status_mark} {item.get('description', '')}\n"
            
            # Notes
            content += "\n## Notes\n\n"
            for note in self.memory_data.get('notes', []):
                content += f"{note}\n"
            
            # Write to file
            with open(self.storage_path, 'w', encoding='utf-8') as f:
                f.write(content)
                
        except Exception as e:
            print(f"Error saving memory: {e}")
    
    def store_memory(self, category, key=None, value=None, data=None):
        """
        Store information in memory.
        
        Args:
            category (str): Category of memory to store
            key (str, optional): Key for the memory entry
            value (str, optional): Value to store
            data (dict, optional): Complete data structure to store
            
        Returns:
            bool: True if storage was successful
        """
        try:
            if data:
                # Store complete data structure
                self.memory_data[category] = data
            else:
                # Store key-value pair
                if category not in self.memory_data:
                    if category in ['user_preferences', 'system_configuration']:
                        self.memory_data[category] = {}
                    else:
                        self.memory_data[category] = []
                
                if category in ['user_preferences', 'system_configuration']:
                    self.memory_data[category][key] = value
                else:
                    # For list-type categories, add a new entry
                    self.memory_data[category].append({
                        'field': key,
                        'value': value,
                        'timestamp': self._get_timestamp()
                    })
            
            # Save to persistent storage
            self._save_memory()
            return True
            
        except Exception as e:
            print(f"Error storing memory: {e}")
            return False
    
    def retrieve_memory(self, category, key=None, query=None):
        """
        Retrieve information from memory.
        
        Args:
            category (str): Category of memory to retrieve
            key (str, optional): Specific key to retrieve
            query (str, optional): Search query for semantic retrieval
            
        Returns:
            dict or list or str: Retrieved memory data
        """
        if category not in self.memory_data:
            return None
            
        if query:
            # Perform semantic search
            return self._semantic_search(query)
            
        if key:
            # Retrieve specific key
            if category in ['user_preferences', 'system_configuration']:
                return self.memory_data[category].get(key)
            else:
                # Search for entry with matching field
                for entry in self.memory_data[category]:
                    if entry.get('field') == key:
                        return entry.get('value')
                return None
        
        # Return entire category
        return self.memory_data[category]
    
    def _semantic_search(self, query):
        """
        Perform semantic search across memory data.
        
        Args:
            query (str): Search query
            
        Returns:
            dict: Search results with relevance scores
        """
        # This would use a proper embedding-based search in practice
        # For now, using simple keyword matching
        query_words = query.lower().split()
        results = {
            'query': query,
            'matches': [],
            'timestamp': self._get_timestamp()
        }
        
        # Search through all memory categories
        for category, data in self.memory_data.items():
            if isinstance(data, list):
                # Search through list items
                for item in data:
                    if 'value' in item and isinstance(item['value'], str):
                        item_text = f"{item.get('field', '')} {item['value']}".lower()
                        score = self._calculate_match_score(item_text, query_words)
                        if score > 0.3:  # Threshold for relevance
                            results['matches'].append({
                                'category': category,
                                'field': item.get('field'),
                                'value': item['value'],
                                'relevance': score
                            })
            elif isinstance(data, dict):
                # Search through dictionary items
                for key, value in data.items():
                    if isinstance(value, str):
                        item_text = f"{key} {value}".lower()
                        score = self._calculate_match_score(item_text, query_words)
                        if score > 0.3:
                            results['matches'].append({
                                'category': category,
                                'field': key,
                                'value': value,
                                'relevance': score
                            })

        # Sort by relevance
        results['matches'].sort(key=lambda x: x['relevance'], reverse=True)
        return results
    
    def _calculate_match_score(self, text, query_words):
        """
        Calculate relevance score between text and query words.
        
        Args:
            text (str): Text to search in
            query_words (list): Words to search for
            
        Returns:
            float: Relevance score between 0 and 1
        """
        score = 0
        text_lower = text.lower()
        
        for word in query_words:
            if word in text_lower:
                # Add score for exact matches
                score += 1
                
                # Add bonus for whole word matches
                words_in_text = text_lower.split()
                if word in words_in_text:
                    score += 0.5
                    
        # Normalize score by query length
        return min(score / len(query_words), 1.0) if query_words else 0
    
    def update_roadmap_status(self, description, status):
        """
        Update the status of a development roadmap item.
        
        Args:
            description (str): Description of the roadmap item
            status (str): New status (pending, in_progress, completed)
            
        Returns:
            bool: True if update was successful
        """
        try:
            roadmap = self.memory_data.get('development_roadmap', [])
            for item in roadmap:
                if description.lower() in item.get('description', '').lower():
                    item['status'] = status
                    self._save_memory()
                    return True
            return False
        except Exception as e:
            print(f"Error updating roadmap: {e}")
            return False
    
    def get_relevant_memories(self, query, limit=5):
        """
        Get memories relevant to a query.
        
        Args:
            query (str): Query to find relevant memories for
            limit (int): Maximum number of memories to return
            
        Returns:
            list: Relevant memory entries
        """
        results = self._semantic_search(query)
        return results['matches'][:limit]
    
    def _get_timestamp(self):
        """
        Get current timestamp.
        
        Returns:
            str: ISO format timestamp
        """
        import datetime
        return datetime.datetime.now().isoformat()
    
    def add_note(self, note_text):
        """
        Add a note to memory.
        
        Args:
            note_text (str): Text of the note to add
            
        Returns:
            bool: True if addition was successful
        """
        try:
            if 'notes' not in self.memory_data:
                self.memory_data['notes'] = []
                
            self.memory_data['notes'].append({
                'text': note_text,
                'timestamp': self._get_timestamp()
            })
            
            self._save_memory()
            return True
            
        except Exception as e:
            print(f"Error adding note: {e}")
            return False
    
    def get_status_report(self):
        """
        Get a comprehensive status report of the memory system.
        
        Returns:
            dict: Status report with key metrics
        """
        return {
            'total_entries': sum(
                len(data) if isinstance(data, list) else 1 
                for data in self.memory_data.values()
            ),
            'category_count': len(self.memory_data),
            'last_updated': self._get_timestamp(),
            'memory_size': len(str(self.memory_data)),
            'roadmap_progress': self._calculate_roadmap_progress()
        }
    
    def _calculate_roadmap_progress(self):
        """
        Calculate progress on the development roadmap.
        
        Returns:
            dict: Progress metrics for the roadmap
        """
        roadmap = self.memory_data.get('development_roadmap', [])
        if not roadmap:
            return {'total': 0, 'completed': 0, 'progress': 0}
            
        completed = sum(1 for item in roadmap if item.get('status') == 'completed')
        total = len(roadmap)
        
        return {
            'total': total,
            'completed': completed,
            'progress': (completed / total) * 100
        }