"""
Unified LLM client for OpenClaw agent.
Supports: local smart-router, OpenRouter API, Google Gemini API.
Uses urllib.request (stdlib) — no external dependencies.
"""

import json
import os
import time
import logging
import hashlib
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Structured response from LLM API call."""
    content: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    success: bool = True
    error: Optional[str] = None

    @property
    def text(self):
        """Alias for content (backward compat)."""
        return self.content


@dataclass
class ModelConfig:
    """Configuration for a single model."""
    provider: str          # 'smart-router' | 'openrouter' | 'gemini'
    model_id: str          # e.g. 'auto', 'openrouter/hunter-alpha'
    api_base: str
    api_key_env: str       # env var name for API key ('' = no key needed)
    max_context: int = 200000
    max_output: int = 4096
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0


# --- Default model configurations ---
# Priority: smart-router (local, free, fast) > Gemini (free tier) > OpenRouter (paid)
MODELS = {
    # Smart-router on the server — routes to best available model
    'fast': ModelConfig(
        provider='smart-router',
        model_id='auto',
        api_base='http://localhost:9000/v1',
        api_key_env='',
        max_context=200000,
        max_output=8192,
        cost_per_1k_input=0.0,
        cost_per_1k_output=0.0,
    ),
    # Smart-router with hunter-alpha for reasoning tasks
    'reasoning': ModelConfig(
        provider='smart-router',
        model_id='openrouter/hunter-alpha',
        api_base='http://localhost:9000/v1',
        api_key_env='',
        max_context=1048576,
        max_output=65536,
        cost_per_1k_input=0.0,
        cost_per_1k_output=0.0,
    ),
    # Smart-router with healer-alpha for complex analysis
    'analysis': ModelConfig(
        provider='smart-router',
        model_id='openrouter/healer-alpha',
        api_base='http://localhost:9000/v1',
        api_key_env='',
        max_context=262144,
        max_output=65536,
        cost_per_1k_input=0.0,
        cost_per_1k_output=0.0,
    ),
    # Default — smart-router auto
    'default': ModelConfig(
        provider='smart-router',
        model_id='auto',
        api_base='http://localhost:9000/v1',
        api_key_env='',
        max_context=200000,
        max_output=8192,
        cost_per_1k_input=0.0,
        cost_per_1k_output=0.0,
    ),
    # Direct Gemini fallback (when smart-router is down)
    'gemini-direct': ModelConfig(
        provider='gemini',
        model_id='gemini-2.0-flash',
        api_base='https://generativelanguage.googleapis.com/v1beta',
        api_key_env='GEMINI_API_KEY',
        max_context=1048576,
        max_output=8192,
        cost_per_1k_input=0.0,
        cost_per_1k_output=0.0,
    ),
    # Direct OpenRouter fallback
    'openrouter-direct': ModelConfig(
        provider='openrouter',
        model_id='openrouter/auto',
        api_base='https://openrouter.ai/api/v1',
        api_key_env='OPENROUTER_API_KEY',
        max_context=200000,
        max_output=4096,
        cost_per_1k_input=0.003,
        cost_per_1k_output=0.012,
    ),
    # Embedding via smart-router (uses TF-IDF fallback if unavailable)
    'embed': ModelConfig(
        provider='embed-local',
        model_id='local-hash',
        api_base='',
        api_key_env='',
        max_context=2048,
        max_output=768,
        cost_per_1k_input=0.0,
        cost_per_1k_output=0.0,
    ),
}

# Fallback order when primary model fails
FALLBACK_CHAIN = ['fast', 'default', 'gemini-direct', 'openrouter-direct']


def _auto_load_keys():
    """Auto-load API keys from OpenClaw config files on the server."""
    import re
    config_paths = [
        '/root/.openclaw/agents/main/agent/models.json',
        '/root/.openclaw/agents/main/agent/auth-profiles.json',
    ]
    for path in config_paths:
        try:
            with open(path, 'r') as f:
                content = f.read()
            if not os.environ.get('OPENROUTER_API_KEY'):
                m = re.search(r'sk-or-v1-[a-f0-9]+', content)
                if m:
                    os.environ['OPENROUTER_API_KEY'] = m.group()
            if not os.environ.get('GEMINI_API_KEY'):
                m = re.search(r'AIzaSy[A-Za-z0-9_-]+', content)
                if m:
                    os.environ['GEMINI_API_KEY'] = m.group()
        except Exception:
            pass


class LLMClient:
    """Unified LLM client with multi-provider support and fallback."""

    def __init__(self, models: dict = None):
        _auto_load_keys()
        self.models = models or MODELS
        self._failure_counts: dict[str, int] = {}
        self._total_cost: float = 0.0
        self._total_calls: int = 0

    # --- Public API ---

    def complete(
        self,
        messages,
        model_key: str = 'default',
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: str = 'text',
        system: str = None,
    ) -> LLMResponse:
        """
        Send a chat completion request with automatic fallback.

        Args:
            messages: String or list of {role, content} dicts.
            model_key: Key into self.models (fast/reasoning/default).
            temperature: Sampling temperature.
            max_tokens: Max output tokens.
            response_format: 'text' or 'json'.
            system: Optional system message prepended to messages.

        Returns:
            LLMResponse with content and metadata.
        """
        # Auto-wrap string into messages list
        if isinstance(messages, str):
            messages = [{'role': 'user', 'content': messages}]

        if system:
            messages = [{'role': 'system', 'content': system}] + messages

        # Build ordered attempt list: requested model first, then fallbacks
        attempt_order = [model_key] + [k for k in FALLBACK_CHAIN if k != model_key]

        last_error = None
        for key in attempt_order:
            if key not in self.models:
                continue
            cfg = self.models[key]
            # Skip models with high recent failure rate
            if self._failure_counts.get(key, 0) > 5:
                logger.warning(f"Skipping {key}: too many recent failures")
                continue

            try:
                resp = self._call_provider(cfg, messages, temperature, min(max_tokens, cfg.max_output), response_format)
                # Reset failure count on success
                self._failure_counts[key] = 0
                self._total_calls += 1
                self._total_cost += resp.cost_usd
                return resp
            except Exception as e:
                self._failure_counts[key] = self._failure_counts.get(key, 0) + 1
                last_error = str(e)
                logger.warning(f"LLM call failed for {key}: {e}")
                continue

        return LLMResponse(
            content='',
            model='none',
            provider='none',
            success=False,
            error=f"All models failed. Last error: {last_error}",
        )

    def embed(self, text: str) -> list[float]:
        """
        Generate embedding vector for text.

        Uses a deterministic hash-based embedding as primary method.
        This is lightweight and works offline — no API needed.
        For semantic similarity it uses character n-gram hashing
        which provides reasonable similarity for keyword matching.

        Args:
            text: Text to embed.

        Returns:
            List of floats (256-dim vector), or empty list on failure.
        """
        try:
            return self._hash_embed(text, dims=256)
        except Exception as e:
            logger.warning(f"Embedding failed: {e}")
            return []

    def _hash_embed(self, text: str, dims: int = 256) -> list[float]:
        """
        Create a deterministic embedding using character n-gram hashing.
        Not as good as neural embeddings but works offline and is fast.
        """
        import math
        vector = [0.0] * dims
        text_lower = text.lower().strip()

        if not text_lower:
            return vector

        # Character n-grams (2, 3, 4)
        for n in [2, 3, 4]:
            for i in range(len(text_lower) - n + 1):
                ngram = text_lower[i:i+n]
                h = int(hashlib.md5(ngram.encode()).hexdigest(), 16)
                idx = h % dims
                vector[idx] += 1.0

        # Word-level hashing
        words = text_lower.split()
        for word in words:
            h = int(hashlib.sha256(word.encode()).hexdigest(), 16)
            idx = h % dims
            vector[idx] += 2.0  # Words get higher weight
            # Also hash word pairs
        for i in range(len(words) - 1):
            pair = words[i] + ' ' + words[i+1]
            h = int(hashlib.md5(pair.encode()).hexdigest(), 16)
            idx = h % dims
            vector[idx] += 1.5

        # L2 normalize
        norm = math.sqrt(sum(v*v for v in vector))
        if norm > 0:
            vector = [v / norm for v in vector]

        return vector

    def get_stats(self) -> dict:
        """Return usage statistics."""
        return {
            'total_calls': self._total_calls,
            'total_cost_usd': round(self._total_cost, 6),
            'failure_counts': dict(self._failure_counts),
        }

    # --- Provider implementations ---

    def _call_provider(
        self, cfg: ModelConfig, messages: list, temperature: float, max_tokens: int, response_format: str
    ) -> LLMResponse:
        if cfg.provider == 'smart-router':
            return self._call_openai_compat(cfg, messages, temperature, max_tokens, response_format)
        elif cfg.provider == 'openrouter':
            return self._call_openai_compat(cfg, messages, temperature, max_tokens, response_format, use_auth=True)
        elif cfg.provider == 'gemini':
            return self._call_gemini(cfg, messages, temperature, max_tokens, response_format)
        elif cfg.provider == 'embed-local':
            raise ValueError("Use embed() method directly for embeddings")
        else:
            raise ValueError(f"Unknown provider: {cfg.provider}")

    def _call_openai_compat(
        self, cfg: ModelConfig, messages: list, temperature: float, max_tokens: int,
        response_format: str, use_auth: bool = False
    ) -> LLMResponse:
        """Call any OpenAI-compatible API (smart-router, OpenRouter, etc.)."""
        url = f"{cfg.api_base}/chat/completions"
        payload = {
            'model': cfg.model_id,
            'messages': messages,
            'temperature': temperature,
            'max_tokens': max_tokens,
        }
        if response_format == 'json':
            payload['response_format'] = {'type': 'json_object'}

        req = Request(url, data=json.dumps(payload).encode(), method='POST')
        req.add_header('Content-Type', 'application/json')

        if use_auth:
            api_key = os.environ.get(cfg.api_key_env, '')
            if not api_key:
                raise ValueError(f"Missing env var: {cfg.api_key_env}")
            req.add_header('Authorization', f'Bearer {api_key}')
            req.add_header('HTTP-Referer', 'https://openclaw.dev')

        t0 = time.time()
        with urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
        latency = (time.time() - t0) * 1000

        choice = data['choices'][0]
        usage = data.get('usage', {})
        inp_tok = usage.get('prompt_tokens', 0)
        out_tok = usage.get('completion_tokens', 0)

        content = choice.get('message', {}).get('content', '')
        if not content:
            raise ValueError("Empty response from model")

        return LLMResponse(
            content=content,
            model=data.get('model', cfg.model_id),
            provider=cfg.provider,
            input_tokens=inp_tok,
            output_tokens=out_tok,
            cost_usd=(inp_tok * cfg.cost_per_1k_input + out_tok * cfg.cost_per_1k_output) / 1000,
            latency_ms=latency,
        )

    def _call_gemini(
        self, cfg: ModelConfig, messages: list, temperature: float, max_tokens: int, response_format: str
    ) -> LLMResponse:
        api_key = os.environ.get(cfg.api_key_env, '')
        if not api_key:
            raise ValueError(f"Missing env var: {cfg.api_key_env}")

        url = f"{cfg.api_base}/models/{cfg.model_id}:generateContent?key={api_key}"

        # Convert OpenAI-style messages to Gemini format
        contents = []
        system_instruction = None
        for msg in messages:
            role = msg['role']
            if role == 'system':
                system_instruction = msg['content']
            else:
                gemini_role = 'user' if role == 'user' else 'model'
                contents.append({
                    'role': gemini_role,
                    'parts': [{'text': msg['content']}],
                })

        payload = {
            'contents': contents,
            'generationConfig': {
                'temperature': temperature,
                'maxOutputTokens': max_tokens,
            },
        }
        if system_instruction:
            payload['systemInstruction'] = {'parts': [{'text': system_instruction}]}
        if response_format == 'json':
            payload['generationConfig']['responseMimeType'] = 'application/json'

        req = Request(url, data=json.dumps(payload).encode(), method='POST')
        req.add_header('Content-Type', 'application/json')

        t0 = time.time()
        with urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
        latency = (time.time() - t0) * 1000

        # Extract content
        candidates = data.get('candidates', [{}])
        content = ''
        if candidates:
            parts = candidates[0].get('content', {}).get('parts', [])
            content = parts[0].get('text', '') if parts else ''

        if not content:
            raise ValueError("Empty response from Gemini")

        usage = data.get('usageMetadata', {})
        inp_tok = usage.get('promptTokenCount', 0)
        out_tok = usage.get('candidatesTokenCount', 0)

        return LLMResponse(
            content=content,
            model=cfg.model_id,
            provider='gemini',
            input_tokens=inp_tok,
            output_tokens=out_tok,
            cost_usd=0.0,
            latency_ms=latency,
        )
