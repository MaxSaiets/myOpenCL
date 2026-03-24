"""
Real tool implementations for the OpenClaw agent.
Each tool performs actual operations (filesystem, subprocess, web, memory).
"""

import os
import shutil
import subprocess
import json
import logging
from typing import Dict, Any, Callable
from urllib.request import Request, urlopen
from urllib.error import HTTPError

logger = logging.getLogger(__name__)

# Safety: workspace root for path operations
WORKSPACE_ROOT = os.environ.get('OPENCLAW_WORKSPACE', '/root')
MAX_READ_BYTES = 100 * 1024  # 100KB

# Commands that are never allowed
COMMAND_BLACKLIST = [
    'rm -rf /',
    'mkfs',
    'dd if=/dev/zero',
    ':(){:|:&};:',
    'chmod -R 777 /',
    '> /dev/sda',
]


def _safe_path(path: str) -> str:
    """Resolve path and verify it's within allowed directories."""
    resolved = os.path.realpath(os.path.expanduser(path))
    allowed_roots = [
        os.path.realpath(WORKSPACE_ROOT),
        '/tmp',
        '/root/.openclaw',
        '/root/projects',
        '/root/scripts',
    ]
    if not any(resolved.startswith(root) for root in allowed_roots):
        raise PermissionError(f"Access denied: {resolved} is outside allowed directories")
    return resolved


def read(path: str) -> Dict[str, Any]:
    """
    Read content from a file.

    Args:
        path: Path to the file to read.

    Returns:
        dict with success, content, path, size_bytes.
    """
    try:
        safe = _safe_path(path)
        size = os.path.getsize(safe)
        with open(safe, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read(MAX_READ_BYTES)
        truncated = size > MAX_READ_BYTES
        return {
            'success': True,
            'content': content,
            'path': safe,
            'size_bytes': size,
            'truncated': truncated,
        }
    except Exception as e:
        return {'success': False, 'error': str(e), 'path': path}


def write(path: str, content: str) -> Dict[str, Any]:
    """
    Write content to a file. Creates backup of existing file.

    Args:
        path: Destination file path.
        content: Content to write.

    Returns:
        dict with success, path, bytes_written.
    """
    try:
        safe = _safe_path(path)
        # Create parent directories
        os.makedirs(os.path.dirname(safe), exist_ok=True)
        # Backup existing file
        if os.path.exists(safe):
            shutil.copy2(safe, safe + '.bak')
        with open(safe, 'w', encoding='utf-8') as f:
            written = f.write(content)
        return {
            'success': True,
            'path': safe,
            'bytes_written': written,
        }
    except Exception as e:
        return {'success': False, 'error': str(e), 'path': path}


def exec_cmd(command: str) -> Dict[str, Any]:
    """
    Execute a shell command with safety checks.

    Args:
        command: Shell command to execute.

    Returns:
        dict with success, command, output, return_code.
    """
    # Safety check
    cmd_lower = command.lower().strip()
    for blocked in COMMAND_BLACKLIST:
        if blocked in cmd_lower:
            return {
                'success': False,
                'command': command,
                'error': f"Blocked dangerous command pattern: {blocked}",
                'return_code': -1,
            }

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=WORKSPACE_ROOT,
        )
        return {
            'success': result.returncode == 0,
            'command': command,
            'output': result.stdout[-4096:] if result.stdout else '',
            'stderr': result.stderr[-2048:] if result.stderr else '',
            'return_code': result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            'success': False,
            'command': command,
            'error': 'Command timed out after 60 seconds',
            'return_code': -1,
        }
    except Exception as e:
        return {
            'success': False,
            'command': command,
            'error': str(e),
            'return_code': -1,
        }


def web_search(query: str) -> Dict[str, Any]:
    """
    Perform a web search via OpenRouter or Brave Search API.

    Args:
        query: Search query string.

    Returns:
        dict with success, query, results.
    """
    # Try Brave Search first
    brave_key = os.environ.get('BRAVE_API_KEY', '')
    if brave_key:
        try:
            from urllib.parse import quote_plus
            url = f"https://api.search.brave.com/res/v1/web/search?q={quote_plus(query)}&count=5"
            req = Request(url)
            req.add_header('X-Subscription-Token', brave_key)
            req.add_header('Accept', 'application/json')
            with urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
            results = []
            for item in data.get('web', {}).get('results', [])[:5]:
                results.append({
                    'title': item.get('title', ''),
                    'url': item.get('url', ''),
                    'snippet': item.get('description', ''),
                })
            return {'success': True, 'query': query, 'results': results}
        except Exception as e:
            logger.warning(f"Brave search failed: {e}")

    # Fallback: use web_fetch on DuckDuckGo lite
    try:
        from urllib.parse import quote_plus
        url = f"https://lite.duckduckgo.com/lite/?q={quote_plus(query)}"
        req = Request(url)
        req.add_header('User-Agent', 'OpenClaw/1.0')
        with urlopen(req, timeout=15) as resp:
            html = resp.read().decode('utf-8', errors='replace')
        # Extract basic results from HTML
        results = []
        snippets = html.split('<td class="result-snippet">')
        links = html.split('<a rel="nofollow" href="')
        for i in range(1, min(len(snippets), 6)):
            snippet_text = snippets[i].split('</td>')[0].strip() if i < len(snippets) else ''
            link_url = links[i].split('"')[0] if i < len(links) else ''
            results.append({
                'title': f"Result {i}",
                'url': link_url,
                'snippet': snippet_text[:300],
            })
        return {'success': bool(results), 'query': query, 'results': results}
    except Exception as e:
        return {'success': False, 'query': query, 'error': str(e), 'results': []}


def memory_search(query: str, memory_system=None) -> Dict[str, Any]:
    """
    Search through the agent's memory system.

    Args:
        query: Search query.
        memory_system: Reference to MemorySystem instance (injected at runtime).

    Returns:
        dict with success, query, results.
    """
    if memory_system is None:
        return {
            'success': False,
            'query': query,
            'error': 'Memory system not initialized',
            'results': [],
        }

    try:
        results = memory_system.get_relevant_memories(query, limit=10)
        return {
            'success': True,
            'query': query,
            'results': results,
        }
    except Exception as e:
        return {
            'success': False,
            'query': query,
            'error': str(e),
            'results': [],
        }


def get_tool_registry(memory_system=None) -> Dict[str, Callable]:
    """
    Get the registry of available tools.

    Args:
        memory_system: Optional MemorySystem instance for memory_search.

    Returns:
        dict: Mapping of tool names to callable functions.
    """
    def _memory_search_bound(query: str, **kwargs) -> Dict[str, Any]:
        return memory_search(query, memory_system=memory_system)

    return {
        'read': read,
        'write': write,
        'exec': exec_cmd,
        'web_search': web_search,
        'memory_search': _memory_search_bound,
        'default': exec_cmd,
    }


# Expose for backward compatibility
tool_registry = get_tool_registry()
