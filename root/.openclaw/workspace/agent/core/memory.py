"""
Memory management module.
Facade over SQLite-backed MemoryStore with backward-compatible markdown export.
Supports episodic/semantic/procedural memory types with embedding-based search.
"""

import json
import os
import logging
from datetime import datetime
from typing import Optional

from agent.core.memory_store import MemoryStore

logger = logging.getLogger(__name__)

# Category mapping from old flat categories to new typed categories
CATEGORY_TYPE_MAP = {
    'architecture_decisions': 'semantic',
    'user_preferences': 'semantic',
    'task_history': 'episodic',
    'system_configuration': 'semantic',
    'development_roadmap': 'procedural',
    'notes': 'episodic',
    'conversation_context': 'episodic',
    'conversation_history': 'episodic',
}


class MemorySystem:
    """Manages the agent's memory — SQLite-backed with markdown export."""

    def __init__(self, storage_path: str = 'MEMORY.md', llm_client=None):
        """
        Initialize the memory system.

        Args:
            storage_path: Path to MEMORY.md (kept for backward compat export).
            llm_client: LLMClient for embedding generation.
        """
        self.storage_path = storage_path
        self.llm_client = llm_client

        # SQLite store lives next to the markdown file
        db_dir = os.path.dirname(os.path.abspath(storage_path)) or '.'
        db_path = os.path.join(db_dir, 'memory.db')
        self.store = MemoryStore(db_path=db_path, llm_client=llm_client)

        # Legacy in-memory data for backward compat
        self.memory_data = {}
        self._load_legacy_memory()

    def _load_legacy_memory(self):
        """Load existing MEMORY.md into SQLite if DB is empty."""
        stats = self.store.get_stats()
        if stats['total_memories'] > 0:
            # DB already has data, load legacy for compat only
            self._load_markdown_to_dict()
            return

        # First run: migrate markdown to SQLite
        if os.path.exists(self.storage_path):
            self._load_markdown_to_dict()
            self._migrate_to_sqlite()
        else:
            self.memory_data = self._default_structure()

    def _default_structure(self) -> dict:
        return {
            'architecture_decisions': [],
            'user_preferences': {},
            'task_history': [],
            'system_configuration': {},
            'development_roadmap': [],
            'notes': [],
        }

    def _load_markdown_to_dict(self):
        """Parse MEMORY.md into self.memory_data dict."""
        try:
            if not os.path.exists(self.storage_path):
                self.memory_data = self._default_structure()
                return

            with open(self.storage_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()

            if content.startswith('{') and content.endswith('}'):
                self.memory_data = json.loads(content)
            else:
                self.memory_data = self._parse_markdown(content)
        except Exception as e:
            logger.warning(f"Error loading memory: {e}")
            self.memory_data = self._default_structure()

    def _parse_markdown(self, content: str) -> dict:
        """Parse markdown into structured data."""
        data = self._default_structure()
        lines = content.split('\n')
        current_section = None
        section_map = {
            '## Architecture Decisions': 'architecture_decisions',
            '## User Preferences': 'user_preferences',
            '## Task History': 'task_history',
            '## System Configuration': 'system_configuration',
            '## Development Roadmap': 'development_roadmap',
            '## Notes': 'notes',
        }
        for line in lines:
            if line.startswith('## '):
                current_section = section_map.get(line.strip())
                continue
            if current_section and line.strip():
                if current_section in ('user_preferences', 'system_configuration') and line.startswith('- '):
                    text = line[2:].strip()
                    if ': ' in text:
                        k, v = text.split(': ', 1)
                        data[current_section][k.lower().replace(' ', '_')] = v
                elif current_section in ('architecture_decisions', 'task_history') and line.startswith('- '):
                    text = line[2:].strip()
                    if ': ' in text:
                        k, v = text.split(': ', 1)
                        data[current_section].append({'field': k, 'value': v})
                elif current_section == 'development_roadmap':
                    item = line.strip()
                    status = 'completed' if item.startswith('[x]') else 'pending'
                    desc = item.lstrip('[x] ').lstrip('[ ] ').strip()
                    if desc:
                        data['development_roadmap'].append({'status': status, 'description': desc})
                elif current_section == 'notes':
                    data['notes'].append(line.strip())
        return data

    def _migrate_to_sqlite(self):
        """One-time migration from markdown to SQLite."""
        logger.info("Migrating MEMORY.md to SQLite...")
        for category, items in self.memory_data.items():
            mem_type = CATEGORY_TYPE_MAP.get(category, 'episodic')
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        content = f"{item.get('field', '')}: {item.get('value', '')}"
                        self.store.store(
                            content=content, category=mem_type,
                            key=f"{category}/{item.get('field', '')}",
                            importance=0.6 if mem_type == 'semantic' else 0.4,
                            metadata={'legacy_category': category},
                            compute_embedding=False,  # Skip for migration speed
                        )
                    elif isinstance(item, str):
                        self.store.store(
                            content=item, category=mem_type,
                            key=f"{category}/note",
                            importance=0.3,
                            metadata={'legacy_category': category},
                            compute_embedding=False,
                        )
            elif isinstance(items, dict):
                for k, v in items.items():
                    self.store.store(
                        content=f"{k}: {v}", category=mem_type,
                        key=f"{category}/{k}",
                        importance=0.6,
                        metadata={'legacy_category': category},
                        compute_embedding=False,
                    )
        logger.info(f"Migrated {self.store.get_stats()['total_memories']} memories to SQLite")

    # --- Public API (backward compatible) ---

    def store_memory(self, category: str, key=None, value=None, data=None) -> bool:
        """
        Store information in memory.

        Args:
            category: Category of memory.
            key: Key for the entry.
            value: Value to store.
            data: Complete data structure.
        """
        try:
            mem_type = CATEGORY_TYPE_MAP.get(category, 'episodic')
            importance = 0.6 if mem_type == 'semantic' else 0.4
            if mem_type == 'procedural':
                importance = 0.7

            if data and isinstance(data, dict):
                content = json.dumps(data, ensure_ascii=False, default=str)
            elif key and value is not None:
                content = f"{key}: {value}" if isinstance(value, str) else f"{key}: {json.dumps(value, default=str)}"
            else:
                content = str(value or key or '')

            self.store.store(
                content=content,
                category=mem_type,
                key=f"{category}/{key}" if key else category,
                importance=importance,
                metadata={'legacy_category': category},
            )

            # Update legacy dict for backward compat
            self._update_legacy(category, key, value, data)
            self._export_markdown()
            return True
        except Exception as e:
            logger.error(f"Error storing memory: {e}")
            return False

    def retrieve_memory(self, category, key=None, query=None):
        """Retrieve information from memory."""
        if query:
            return self._semantic_search(query)

        if key:
            result = self.store.retrieve_by_key(f"{category}/{key}")
            if result:
                return result['content']
            # Fallback to legacy
            if category in self.memory_data:
                if isinstance(self.memory_data[category], dict):
                    return self.memory_data[category].get(key)
                for entry in self.memory_data.get(category, []):
                    if isinstance(entry, dict) and entry.get('field') == key:
                        return entry.get('value')
            return None

        # Return entire category from legacy (for backward compat)
        return self.memory_data.get(category, [])

    def _semantic_search(self, query: str) -> dict:
        """Perform semantic search across memory."""
        results = self.store.search_semantic(query, limit=10)

        # Convert to legacy format
        matches = []
        for r in results:
            matches.append({
                'category': r.get('metadata', {}).get('legacy_category', r['category']),
                'field': r.get('key', ''),
                'value': r['content'],
                'relevance': r.get('relevance', 0.5),
            })

        return {
            'query': query,
            'matches': matches,
            'timestamp': datetime.now().isoformat(),
        }

    def get_relevant_memories(self, query: str, limit: int = 5) -> list:
        """Get memories relevant to a query."""
        results = self.store.search_semantic(query, limit=limit)
        return [
            {
                'category': r.get('metadata', {}).get('legacy_category', r['category']),
                'field': r.get('key', ''),
                'value': r['content'],
                'relevance': r.get('relevance', 0.5),
            }
            for r in results
        ]

    def update_roadmap_status(self, description: str, status: str) -> bool:
        """Update development roadmap item status."""
        try:
            roadmap = self.memory_data.get('development_roadmap', [])
            for item in roadmap:
                if description.lower() in item.get('description', '').lower():
                    item['status'] = status
                    self._export_markdown()
                    return True
            return False
        except Exception as e:
            logger.error(f"Error updating roadmap: {e}")
            return False

    def add_note(self, note_text: str) -> bool:
        """Add a note to memory."""
        return self.store_memory('notes', 'note', note_text)

    def get_status_report(self) -> dict:
        """Get comprehensive memory status."""
        db_stats = self.store.get_stats()
        return {
            'total_entries': db_stats['total_memories'],
            'by_category': db_stats['by_category'],
            'avg_importance': db_stats['avg_importance'],
            'avg_decay': db_stats['avg_decay'],
            'db_size_kb': db_stats['db_size_kb'],
            'last_updated': datetime.now().isoformat(),
            'roadmap_progress': self._calculate_roadmap_progress(),
        }

    def _calculate_roadmap_progress(self) -> dict:
        roadmap = self.memory_data.get('development_roadmap', [])
        if not roadmap:
            return {'total': 0, 'completed': 0, 'progress': 0}
        completed = sum(1 for item in roadmap if item.get('status') == 'completed')
        return {
            'total': len(roadmap),
            'completed': completed,
            'progress': (completed / len(roadmap)) * 100,
        }

    # --- Maintenance ---

    def run_maintenance(self):
        """Run periodic maintenance: decay + compression."""
        self.store.apply_decay(decay_rate=0.01)
        compressed = self.store.compress_old_memories()
        if compressed:
            logger.info(f"Compressed {compressed} old memories")

    # --- Legacy helpers ---

    def _update_legacy(self, category, key, value, data):
        """Update legacy in-memory dict."""
        if category not in self.memory_data:
            self.memory_data[category] = {} if category in ('user_preferences', 'system_configuration') else []
        if data:
            self.memory_data[category] = data
        elif isinstance(self.memory_data.get(category), dict):
            self.memory_data[category][key] = value
        elif isinstance(self.memory_data.get(category), list):
            self.memory_data[category].append({
                'field': key, 'value': value,
                'timestamp': datetime.now().isoformat(),
            })

    def _export_markdown(self):
        """Export current state to MEMORY.md for human readability."""
        try:
            lines = ['# Memory System\n']
            lines.append('## Architecture Decisions\n')
            for item in self.memory_data.get('architecture_decisions', []):
                lines.append(f"- {item.get('field', '')}: {item.get('value', '')}")
            lines.append('\n## User Preferences\n')
            for k, v in self.memory_data.get('user_preferences', {}).items():
                lines.append(f"- {k.replace('_', ' ').title()}: {v}")
            lines.append('\n## System Configuration\n')
            for k, v in self.memory_data.get('system_configuration', {}).items():
                lines.append(f"- {k.replace('_', ' ').title()}: {v}")
            lines.append('\n## Development Roadmap\n')
            for item in self.memory_data.get('development_roadmap', []):
                mark = '[x]' if item.get('status') == 'completed' else '[ ]'
                lines.append(f"{mark} {item.get('description', '')}")
            lines.append('')

            with open(self.storage_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
        except Exception as e:
            logger.warning(f"Error exporting markdown: {e}")
