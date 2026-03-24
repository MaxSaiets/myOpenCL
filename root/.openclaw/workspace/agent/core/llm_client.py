"""
Unified LLM client for OpenClaw agent.
Supports: local smart-router, OpenRouter API, Google Gemini API.
Uses urllib.request (stdlib) вЂ” no external dependencies.

Features:
  - Smart-router as primary (routes to Gemini/Groq/Cerebras/GitHub/OpenRouter)
  - Automatic retry with exponential backoff on 429/503
  - Fallback chain: smart-router в†’ Gemini direct в†’ OpenRouter direct
  - Hash-based local embeddings (no API needed)
  - Request deduplication for identical prompts within TTL
"""

import json
import os
import time
import logging
import hashlib
import math
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# --- Retry configuration ---
MAX_RETRIES = 3              # Max retries per provider on 429/503
RETRY_BASE_DELAY = 2.0       # Base delay in seconds (doubles each retry)
RETRY_MAX_DELAY = 30.0       # Max delay between retries
DEDUP_TTL = 5.0              # Seconds to cache identical requests


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
    # Smart-router on the server вЂ” routes to best available model
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
    # Default вЂ” smart-router auto
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
    # Embedding вЂ” local hash-based (no API needed)
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
    """Unified LLM client with multi-provider support, retry, and fallback."""

    def __init__(self, models: dict = None):
        _auto_load_keys()
        self.models = models or MODELS
        self._failure_counts: dict[str, int] = {}
        self._cooldowns: dict[str, float] = {}  # key -> timestamp when cooldown ends
        self._total_cost: float = 0.0
        self._total_calls: int = 0
        self._total_retries: int = 0
        self._dedup_cache: dict[str, tuple] = {}  # hash -> (response, timestamp)

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
        Send a chat completion request with automatic retry and fallback.

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

        # Check dedup cache for identical recent requests
        cache_key = self._make_cache_key(messages, model_key, temperature)
        cached = self._check_cache(cache_key)
        if cached:
            return cached

        # Build ordered attempt list: requested model first, then fallbacks
        attempt_order = [model_key] + [k for k in FALLBACK_CHAIN if k != model_key]

        last_error = None
        for key in attempt_order:
            if key not in self.models:
                continue
            cfg = self.models[key]

            # Skip models in cooldown
            if self._in_cooldown(key):
                logger.debug(f"Skipping {key}: in cooldown")
                continue

            # Skip models with too many consecutive failures
            if self._failure_counts.get(key, 0) > 10:
                logger.warning(f"Skipping {key}: too many recent failures ({self._failure_counts[key]})")
                continue

            # Try with retries for transient errors (429, 503)
            for attempt in range(MAX_RETRIES + 1):
                try:
                    resp = self._call_provider(
                        cfg, messages, temperature,
                        min(max_tokens, cfg.max_output), response_format
                    )
                    # Success вЂ” reset failure count, cache result
                    self._failure_counts[key] = 0
                    self._total_calls += 1
                    self._total_cost += resp.cost_usd
                    self._cache_response(cache_key, resp)
                    return resp

                except HTTPError as e:
                    error_code = e.code
                    error_body = ''
                    try:
                        error_body = e.read().decode('utf-8', errors='replace')[:500]
                    except Exception:
                        pass

                    last_error = f"HTTP {error_code}: {error_body[:200]}"

                    if error_code in (429, 503) and attempt < MAX_RETRIES:
                        # Retry with exponential backoff
                        delay = min(RETRY_BASE_DELAY * (2 ** attempt), RETRY_MAX_DELAY)
                        # Check Retry-After header
                        retry_after = e.headers.get('Retry-After') if hasattr(e, 'headers') else None
                        if retry_after:
                            try:
                                delay = max(delay, float(retry_after))
                            except ValueError:
                                pass
                        logger.info(f"Retry {attempt+1}/{MAX_RETRIES} for {key} after {delay:.1f}s (HTTP {error_code})")
                        self._total_retries += 1
                        time.sleep(delay)
                        continue
                    else:
                        # Non-retryable or exhausted retries
                        self._failure_counts[key] = self._failure_counts.get(key, 0) + 1
                        if error_code in (429, 503):
                            # Set cooldown for this model
                            self._set_cooldown(key, 60)  # 60s cooldown
                        logger.warning(f"LLM call failed for {key}: HTTP {error_code}")
                        break

                except (URLError, TimeoutError, ConnectionError) as e:
                    last_error = str(e)
                    self._failure_counts[key] = self._failure_counts.get(key, 0) + 1
                    if attempt < MAX_RETRIES:
                        delay = RETRY_BASE_DELAY * (2 ** attempt)
                        logger.info(f"Retry {attempt+1}/{MAX_RETRIES} for {key} after {delay:.1f}s (connection error)")
                        self._total_retries += 1
                        time.sleep(delay)
                        continue
                    logger.warning(f"LLM call failed for {key}: {e}")
                    break

                except Exception as e:
                    self._failure_counts[key] = self._failure_counts.get(key, 0) + 1
                    last_error = str(e)
                    logger.warning(f"LLM call failed for {key}: {e}")
                    break

        return LLMResponse(
            content='',
            model='none',
            provider='none',
            success=False,
            error=f"All models failed. Last error: {last_error}",
        )

    def embed(self, text: str) -> list[float]:
        """
        Generate embedding vector for text using local hash-based method.
        Works offline, no API needed. Uses character n-gram hashing.

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

    def get_stats(self) -> dict:
        """Return usage statistics."""
        return {
            'total_calls': self._total_calls,
            'total_retries': self._total_retries,
            'total_cost_usd': round(self._total_cost, 6),
            'failure_counts': dict(self._failure_counts),
            'active_cooldowns': {
                k: round(v - time.time(), 1)
                for k, v in self._cooldowns.items()
                if v > time.time()
            },
            'cache_size': len(self._dedup_cache),
        }

    def reset_failures(self):
        """Reset all failure counts and cooldowns (call after fixing issues)."""
        self._failure_counts.clear()
        self._cooldowns.clear()
        logger.info("Reset all failure counts and cooldowns")

    # --- Cooldown management ---

    def _in_cooldown(self, key: str) -> bool:
        """Check if a model is in cooldown."""
        return self._cooldowns.get(key, 0) > time.time()

    def _set_cooldown(self, key: str, seconds: float):
        """Set a cooldown for a model."""
        self._cooldowns[key] = time.time() + seconds
        logger.info(f"Set {seconds}s cooldown for {key}")

    # --- Request deduplication ---

    def _make_cache_key(self, messages: list, model_key: str, temperature: float) -> str:
        """Create a hash key for deduplication."""
        raw = json.dumps({'m': messages, 'k': model_key, 't': temperature}, sort_keys=True)
        return hashlib.md5(raw.encode()).hexdigest()

    def _check_cache(self, cache_key: str) -> Optional[LLMResponse]:
        """Check if we have a cached response within TTL."""
        if cache_key in self._dedup_cache:
            resp, ts = self._dedup_cache[cache_key]
            if time.time() - ts < DEDUP_TTL:
                logger.debug("Returning cached response")
                return resp
            else:
                del self._dedup_cache[cache_key]
        return None

    def _cache_response(self, cache_key: str, resp: LLMResponse):
        """Cache a response for deduplication."""
        self._dedup_cache[cache_key] = (resp, time.time())
        # Prune old entries
        if len(self._dedup_cache) > 100:
            now = time.time()
            self._dedup_cache = {
                k: (r, t) for k, (r, t) in self._dedup_cache.items()
                if now - t < DEDUP_TTL
            }

    # --- Embedding implementation ---

    def _hash_embed(self, text: str, dims: int = 256) -> list[float]:
        """
        Create a deterministic embedding using character n-gram hashing.
        Not as good as neural embeddings but works offline and is fast.
        Uses multi-scale n-grams and word-level features for reasonable
        similarity between related texts.
        """
        vector = [0.0] * dims
        text_lower = text.lower().strip()

        if not text_lower:
            return vector

        # Character n-grams (2, 3, 4) вЂ” captures local patterns
        for n in [2, 3, 4]:
            weight = 1.0 / n  # Shorter n-grams get slightly more weight
            for i in range(len(text_lower) - n + 1):
                ngram = text_lower[i:i+n]
                h = int(hashlib.md5(ngram.encode()).hexdigest(), 16)
                idx = h % dims
                vector[idx] += weight

        # Word-level hashing вЂ” captures semantics
        words = text_lower.split()
        for word in words:
            # Remove common punctuation
            word = word.strip('.,!?;:()[]{}"\'-')
            if not word:
                continue
            h = int(hashlib.sha256(word.encode()).hexdigest(), 16)
            idx = h % dims
            vector[idx] += 2.0  # Words get higher weight

        # Word pair hashing вЂ” captures word relationships
        for i in range(len(words) - 1):
            w1 = words[i].strip('.,!?;:()[]{}"\'-')
            w2 = words[i+1].strip('.,!?;:()[]{}"\'-')
            if w1 and w2:
                pair = w1 + ' ' + w2
                h = int(hashlib.md5(pair.encode()).hexdigest(), 16)
                idx = h % dims
                vector[idx] += 1.5

        # L2 normalize
        norm = math.sqrt(sum(v*v for v in vector))
        if norm > 0:
            vector = [v / norm for v in vector]

        return vector

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
            # Check for tool calls (which are valid responses without content)
            tool_calls = choice.get('message', {}).get('tool_calls', [])
            if tool_calls:
                content = json.dumps([{
                    'name': tc.get('function', {}).get('name', ''),
                    'arguments': tc.get('function', {}).get('arguments', '{}'),
                } for tc in tool_calls])
            else:
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
