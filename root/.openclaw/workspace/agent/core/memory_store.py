"""
SQLite-backed memory storage with embedding support.
Replaces flat markdown files with proper database storage.
Zero external dependencies — uses Python stdlib sqlite3.
"""

import json
import math
import os
import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL CHECK(category IN ('episodic', 'semantic', 'procedural')),
    key TEXT,
    content TEXT NOT NULL,
    embedding_json TEXT,
    importance REAL NOT NULL DEFAULT 0.5,
    access_count INTEGER NOT NULL DEFAULT 0,
    decay_factor REAL NOT NULL DEFAULT 1.0,
    created_at TEXT NOT NULL,
    last_accessed TEXT NOT NULL,
    metadata_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);
CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance DESC);
CREATE INDEX IF NOT EXISTS idx_memories_key ON memories(key);

CREATE TABLE IF NOT EXISTS evaluation_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT,
    quality_score REAL NOT NULL,
    category TEXT,
    details_json TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_eval_scores_task ON evaluation_scores(task_id);
"""

MAX_MEMORIES = 10000  # Hard cap for 2GB RAM server


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class MemoryStore:
    """SQLite-backed memory storage with vector search."""

    def __init__(self, db_path: str = 'memory.db', llm_client=None):
        """
        Args:
            db_path: Path to SQLite database file.
            llm_client: LLMClient instance for embedding generation.
        """
        self.db_path = db_path
        self.llm_client = llm_client
        self._conn = None
        self._init_db()

    def _init_db(self):
        """Initialize the database and create tables."""
        self._conn = sqlite3.connect(self.db_path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(DB_SCHEMA)
        self._conn.commit()

    def close(self):
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    # --- Core CRUD ---

    def store(
        self,
        content: str,
        category: str = 'episodic',
        key: str = None,
        importance: float = 0.5,
        metadata: dict = None,
        compute_embedding: bool = True,
    ) -> int:
        """
        Store a memory entry.

        Args:
            content: The text content to store.
            category: 'episodic', 'semantic', or 'procedural'.
            key: Optional key for easy retrieval.
            importance: 0.0 to 1.0 importance score.
            metadata: Additional metadata dict.
            compute_embedding: Whether to compute and store embedding.

        Returns:
            Row ID of the inserted memory.
        """
        # Enforce memory cap
        count = self._conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        if count >= MAX_MEMORIES:
            self._evict_oldest()

        # Compute embedding
        embedding_json = None
        if compute_embedding and self.llm_client:
            embedding = self.llm_client.embed(content[:2000])  # Truncate for embedding
            if embedding:
                embedding_json = json.dumps(embedding)

        now = datetime.now().isoformat()
        cursor = self._conn.execute(
            """INSERT INTO memories
               (category, key, content, embedding_json, importance, access_count,
                decay_factor, created_at, last_accessed, metadata_json)
               VALUES (?, ?, ?, ?, ?, 0, 1.0, ?, ?, ?)""",
            (category, key, content, embedding_json, importance, now, now,
             json.dumps(metadata) if metadata else None),
        )
        self._conn.commit()
        return cursor.lastrowid

    def retrieve_by_key(self, key: str) -> Optional[dict]:
        """Retrieve a memory by exact key match."""
        row = self._conn.execute(
            "SELECT * FROM memories WHERE key = ? ORDER BY created_at DESC LIMIT 1",
            (key,),
        ).fetchone()
        if row:
            self._touch(row[0])
            return self._row_to_dict(row)
        return None

    def retrieve_by_category(self, category: str, limit: int = 20) -> list[dict]:
        """Retrieve all memories in a category."""
        rows = self._conn.execute(
            "SELECT * FROM memories WHERE category = ? ORDER BY importance DESC, created_at DESC LIMIT ?",
            (category, limit),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def search_semantic(self, query: str, limit: int = 10, min_similarity: float = 0.3) -> list[dict]:
        """
        Semantic search using embedding similarity.

        Args:
            query: Search query text.
            limit: Max results to return.
            min_similarity: Minimum cosine similarity threshold.

        Returns:
            List of matching memories sorted by relevance.
        """
        # Compute query embedding
        if not self.llm_client:
            return self.search_keyword(query, limit)

        query_embedding = self.llm_client.embed(query)
        if not query_embedding:
            return self.search_keyword(query, limit)

        # Load all embeddings and compare
        rows = self._conn.execute(
            "SELECT * FROM memories WHERE embedding_json IS NOT NULL"
        ).fetchall()

        scored = []
        for row in rows:
            mem = self._row_to_dict(row)
            stored_embedding = json.loads(row[4]) if row[4] else None
            if stored_embedding:
                sim = cosine_similarity(query_embedding, stored_embedding)
                # Apply decay factor
                effective_sim = sim * mem['decay_factor']
                if effective_sim >= min_similarity:
                    mem['relevance'] = round(effective_sim, 4)
                    scored.append(mem)

        scored.sort(key=lambda x: x['relevance'], reverse=True)

        # Touch accessed memories
        for mem in scored[:limit]:
            self._touch(mem['id'])

        return scored[:limit]

    def search_keyword(self, query: str, limit: int = 10) -> list[dict]:
        """Fallback keyword search when embeddings unavailable."""
        words = query.lower().split()
        rows = self._conn.execute("SELECT * FROM memories").fetchall()

        scored = []
        for row in rows:
            mem = self._row_to_dict(row)
            text = f"{mem.get('key', '')} {mem['content']}".lower()
            score = 0
            for word in words:
                if word in text:
                    score += 1
                    if word in text.split():
                        score += 0.5
            if words:
                score = min(score / len(words), 1.0) * mem['decay_factor']
            if score > 0.3:
                mem['relevance'] = round(score, 4)
                scored.append(mem)

        scored.sort(key=lambda x: x['relevance'], reverse=True)
        return scored[:limit]

    # --- Memory maintenance ---

    def apply_decay(self, decay_rate: float = 0.01):
        """
        Apply time-based decay to all memories.
        Procedural memories don't decay.
        """
        self._conn.execute(
            """UPDATE memories
               SET decay_factor = MAX(0.1, decay_factor - ?)
               WHERE category != 'procedural'
               AND decay_factor > 0.1""",
            (decay_rate,),
        )
        self._conn.commit()

    def compress_old_memories(self, days_threshold: int = 7, min_group_size: int = 3):
        """
        Compress old episodic memories into semantic summaries.

        Args:
            days_threshold: Age in days before memories are eligible for compression.
            min_group_size: Minimum memories in a group to trigger compression.

        Returns:
            Number of memories compressed.
        """
        if not self.llm_client:
            return 0

        cutoff = (datetime.now() - timedelta(days=days_threshold)).isoformat()
        rows = self._conn.execute(
            """SELECT * FROM memories
               WHERE category = 'episodic'
               AND created_at < ?
               AND access_count < 3
               ORDER BY created_at""",
            (cutoff,),
        ).fetchall()

        if len(rows) < min_group_size:
            return 0

        # Group into batches of 10 for summarization
        compressed = 0
        for i in range(0, len(rows), 10):
            batch = rows[i:i + 10]
            if len(batch) < min_group_size:
                break

            contents = [self._row_to_dict(r)['content'] for r in batch]
            summary_text = '\n'.join(f"- {c}" for c in contents)

            # LLM summarize
            from agent.core.model_router import TaskType
            resp = self.llm_client.complete(
                messages=[{'role': 'user', 'content': f"Summarize these events into 1-2 concise sentences:\n\n{summary_text}"}],
                model_key='fast',
                temperature=0.3,
                max_tokens=200,
            )

            if resp.success and resp.content:
                # Store summary as semantic memory
                self.store(
                    content=resp.content.strip(),
                    category='semantic',
                    key=f"compressed_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                    importance=0.6,
                    metadata={'source': 'compression', 'original_count': len(batch)},
                )
                # Delete originals
                ids = [r[0] for r in batch]
                placeholders = ','.join('?' * len(ids))
                self._conn.execute(f"DELETE FROM memories WHERE id IN ({placeholders})", ids)
                self._conn.commit()
                compressed += len(batch)

        return compressed

    def _evict_oldest(self, count: int = 100):
        """Remove oldest, least accessed memories to stay under cap."""
        self._conn.execute(
            """DELETE FROM memories WHERE id IN (
                SELECT id FROM memories
                WHERE category = 'episodic'
                ORDER BY (importance * decay_factor * (1 + access_count)) ASC
                LIMIT ?
            )""",
            (count,),
        )
        self._conn.commit()

    def _touch(self, memory_id: int):
        """Update access count and timestamp."""
        self._conn.execute(
            "UPDATE memories SET access_count = access_count + 1, last_accessed = ? WHERE id = ?",
            (datetime.now().isoformat(), memory_id),
        )
        self._conn.commit()

    def _row_to_dict(self, row) -> dict:
        """Convert a database row to a dict."""
        return {
            'id': row[0],
            'category': row[1],
            'key': row[2],
            'content': row[3],
            'importance': row[5],
            'access_count': row[6],
            'decay_factor': row[7],
            'created_at': row[8],
            'last_accessed': row[9],
            'metadata': json.loads(row[10]) if row[10] else {},
        }

    # --- Evaluation scores ---

    def store_evaluation(self, task_id: str, score: float, category: str = None, details: dict = None):
        """Store a task evaluation score."""
        self._conn.execute(
            """INSERT INTO evaluation_scores (task_id, quality_score, category, details_json, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (task_id, score, category, json.dumps(details) if details else None, datetime.now().isoformat()),
        )
        self._conn.commit()

    def get_evaluation_history(self, limit: int = 50) -> list[dict]:
        """Get recent evaluation scores."""
        rows = self._conn.execute(
            "SELECT * FROM evaluation_scores ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {
                'id': r[0], 'task_id': r[1], 'quality_score': r[2],
                'category': r[3], 'details': json.loads(r[4]) if r[4] else {},
                'created_at': r[5],
            }
            for r in rows
        ]

    def get_average_score(self, category: str = None, days: int = 7) -> float:
        """Get average quality score for recent evaluations."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        if category:
            row = self._conn.execute(
                "SELECT AVG(quality_score) FROM evaluation_scores WHERE category = ? AND created_at > ?",
                (category, cutoff),
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT AVG(quality_score) FROM evaluation_scores WHERE created_at > ?",
                (cutoff,),
            ).fetchone()
        return round(row[0], 4) if row and row[0] else 0.0

    # --- Stats ---

    def get_stats(self) -> dict:
        """Get memory store statistics."""
        total = self._conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        by_cat = self._conn.execute(
            "SELECT category, COUNT(*) FROM memories GROUP BY category"
        ).fetchall()
        avg_importance = self._conn.execute(
            "SELECT AVG(importance) FROM memories"
        ).fetchone()[0]
        avg_decay = self._conn.execute(
            "SELECT AVG(decay_factor) FROM memories"
        ).fetchone()[0]

        return {
            'total_memories': total,
            'by_category': {r[0]: r[1] for r in by_cat},
            'avg_importance': round(avg_importance, 4) if avg_importance else 0,
            'avg_decay': round(avg_decay, 4) if avg_decay else 0,
            'db_size_kb': os.path.getsize(self.db_path) // 1024 if os.path.exists(self.db_path) else 0,
        }
