"""
Unified LLM client for OpenRouter and Google Gemini APIs.
Uses urllib.request (stdlib) — no external dependencies.
"""

import json
import os
import time
import logging
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


@dataclass
class ModelConfig:
    """Configuration for a single model."""
    provider: str          # 'openrouter' | 'gemini'
    model_id: str          # e.g. 'openrouter/auto'
    api_base: str
    api_key_env: str       # env var name for API key
    max_context: int = 200000
    max_output: int = 4096
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0


# --- Default model configurations ---
MODELS = {
    'fast': ModelConfig(
        provider='gemini',
        model_id='gemini-2.5-flash',
        api_base='https://generativelanguage.googleapis.com/v1beta',
        api_key_env='GEMINI_API_KEY',
        max_context=1048576,
        max_output=65536,
        cost_per_1k_input=0.0,
        cost_per_1k_output=0.0,
    ),
    'reasoning': ModelConfig(
        provider='openrouter',
        model_id='openrouter/optimus-alpha',
        api_base='https://openrouter.ai/api/v1',
        api_key_env='OPENROUTER_API_KEY',
        max_context=200000,
        max_output=65536,
        cost_per_1k_input=0.005,
        cost_per_1k_output=0.015,
    ),
    'default': ModelConfig(
        provider='openrouter',
        model_id='openrouter/auto',
        api_base='https://openrouter.ai/api/v1',
        api_key_env='OPENROUTER_API_KEY',
        max_context=200000,
        max_output=4096,
        cost_per_1k_input=0.003,
        cost_per_1k_output=0.012,
    ),
    'embed': ModelConfig(
        provider='gemini',
        model_id='text-embedding-004',
        api_base='https://generativelanguage.googleapis.com/v1beta',
        api_key_env='GEMINI_API_KEY',
        max_context=2048,
        max_output=768,
        cost_per_1k_input=0.0,
        cost_per_1k_output=0.0,
    ),
}

# Fallback order when primary model fails
FALLBACK_CHAIN = ['fast', 'default', 'reasoning']


class LLMClient:
    """Unified LLM client with multi-provider support and fallback."""

    def __init__(self, models: dict = None):
        self.models = models or MODELS
        self._failure_counts: dict[str, int] = {}
        self._total_cost: float = 0.0
        self._total_calls: int = 0

    # --- Public API ---

    def complete(
        self,
        messages: list[dict],
        model_key: str = 'default',
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: str = 'text',
        system: str = None,
    ) -> LLMResponse:
        """
        Send a chat completion request with automatic fallback.

        Args:
            messages: List of {role, content} dicts.
            model_key: Key into self.models (fast/reasoning/default).
            temperature: Sampling temperature.
            max_tokens: Max output tokens.
            response_format: 'text' or 'json'.
            system: Optional system message prepended to messages.

        Returns:
            LLMResponse with content and metadata.
        """
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
        Generate embedding vector for text using Gemini embedding model.

        Args:
            text: Text to embed (max ~2048 tokens).

        Returns:
            List of floats (768-dim vector), or empty list on failure.
        """
        cfg = self.models.get('embed')
        if not cfg:
            logger.error("No embedding model configured")
            return []

        api_key = os.environ.get(cfg.api_key_env, '')
        if not api_key:
            logger.error(f"Missing env var: {cfg.api_key_env}")
            return []

        url = f"{cfg.api_base}/models/{cfg.model_id}:embedContent?key={api_key}"
        payload = {
            'model': f'models/{cfg.model_id}',
            'content': {'parts': [{'text': text}]},
        }

        try:
            req = Request(url, data=json.dumps(payload).encode(), method='POST')
            req.add_header('Content-Type', 'application/json')
            with urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
            return data.get('embedding', {}).get('values', [])
        except Exception as e:
            logger.warning(f"Embedding failed: {e}")
            return []

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
        if cfg.provider == 'openrouter':
            return self._call_openrouter(cfg, messages, temperature, max_tokens, response_format)
        elif cfg.provider == 'gemini':
            return self._call_gemini(cfg, messages, temperature, max_tokens, response_format)
        else:
            raise ValueError(f"Unknown provider: {cfg.provider}")

    def _call_openrouter(
        self, cfg: ModelConfig, messages: list, temperature: float, max_tokens: int, response_format: str
    ) -> LLMResponse:
        api_key = os.environ.get(cfg.api_key_env, '')
        if not api_key:
            raise ValueError(f"Missing env var: {cfg.api_key_env}")

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

        return LLMResponse(
            content=choice['message']['content'],
            model=cfg.model_id,
            provider='openrouter',
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

        usage = data.get('usageMetadata', {})
        inp_tok = usage.get('promptTokenCount', 0)
        out_tok = usage.get('candidatesTokenCount', 0)

        return LLMResponse(
            content=content,
            model=cfg.model_id,
            provider='gemini',
            input_tokens=inp_tok,
            output_tokens=out_tok,
            cost_usd=0.0,  # Gemini Flash is free tier
            latency_ms=latency,
        )
