"""
Memory Module - Manages context and knowledge storage
"""
import json
import os
from datetime import datetime
from typing import Dict, Any, List, Optional

class Memory:
    def __init__(self, storage_path: str = "memory/MEMORY.md"):
        self.storage_path = storage_path
        self.memory_data = self._load_memory()
    
    def _load_memory(self) -> Dict[str, Any]:
        """Load memory from file or create new memory structure"""
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                # Parse the content - assuming simple key=value or JSON-like structure
                memory_data = {"content": content, "last_updated": datetime.now().isoformat()}
                
                return memory_data
            except Exception as e:
                print(f"Error loading memory: {e}")
        
        # Initialize with empty memory
        return {
            "content": "",
            "context": {},
            "user_preferences": {},
            "conversation_history": [],
            "knowledge_base": {},
            "last_updated": datetime.now().isoformat()
        }
    
    def store(self, key: str, value: Any) -> bool:
        """Store information in memory"""
        try:
            # Update in-memory data
            if '.' in key:
                # Handle dot notation for nested keys
                parts = key.split('.')
                current = self.memory_data
                for part in parts[:-1]:
                    if part not in current:
                        current[part] = {}
                    current = current[part]
                current[parts[-1]] = value
            else:
                self.memory_data[key] = value
            
            # Update last modified time
            self.memory_data['last_updated'] = datetime.now().isoformat()
            
            # Save to file
            self._save_memory()
            
            return True
        except Exception as e:
            print(f"Error storing memory: {e}")
            return False
    
    def retrieve(self, key: str) -> Optional[Any]:
        """Retrieve information from memory"""
        try:
            if '.' in key:
                # Handle dot notation for nested keys
                parts = key.split('.')
                current = self.memory_data
                for part in parts:
                    if isinstance(current, dict) and part in current:
                        current = current[part]
                    else:
                        return None
                return current
            else:
                return self.memory_data.get(key)
        except Exception as e:
            print(f"Error retrieving memory: {e}")
            return None
    
    def search(self, query: str) -> List[Dict[str, Any]]:
        """Search memory for relevant information"""
        results = []
        
        # Simple text search in memory content
        if query.lower() in str(self.memory_data.get('content', '')).lower():
            results.append({
                'key': 'content',
                'value': self.memory_data['content'],
                'score': 1.0
            })
        
        # Search in conversation history
        history = self.memory_data.get('conversation_history', [])
        for i, entry in enumerate(history):
            if isinstance(entry, str) and query.lower() in entry.lower():
                results.append({
                    'key': f'conversation_history[{i}]',
                    'value': entry,
                    'score': 0.8
                })
            elif isinstance(entry, dict) and 'message' in entry:
                if query.lower() in entry['message'].lower():
                    results.append({
                        'key': f'conversation_history[{i}].message',
                        'value': entry['message'],
                        'score': 0.8
                    })
        
        # Sort by score
        results.sort(key=lambda x: x['score'], reverse=True)
        return results
    
    def _save_memory(self) -> bool:
        """Save memory to persistent storage"""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
            
            # Save as JSON for structured data
            with open(self.storage_path, 'w', encoding='utf-8') as f:
                json.dump(self.memory_data, f, indent=2, ensure_ascii=False)
            
            return True
        except Exception as e:
            print(f"Error saving memory: {e}")
            return False
    
    def get_context(self) -> Dict[str, Any]:
        """Get current context from memory"""
        return self.memory_data.get('context', {})
    
    def update_context(self, context: Dict[str, Any]) -> bool:
        """Update conversation context"""
        try:
            if 'context' not in self.memory_data:
                self.memory_data['context'] = {}
            
            self.memory_data['context'].update(context)
            self.memory_data['last_updated'] = datetime.now().isoformat()
            
            return self._save_memory()
        except Exception as e:
            print(f"Error updating context: {e}")
            return False
    
    def clear_memory(self) -> bool:
        """Clear all memory (except persistent configuration)"""
        # Preserve storage path and basic structure
        default_data = {
            "content": "",
            "context": {},
            "user_preferences": {},
            "conversation_history": [],
            "knowledge_base": {},
            "last_updated": datetime.now().isoformat()
        }
        
        self.memory_data = default_data
        return self._save_memory()