import express from 'express';
import fetch from 'node-fetch';

// ─────────────────────────────────────────────────────────────────────────────
//  CONFIGURATION
// ─────────────────────────────────────────────────────────────────────────────
const PORT       = 9000;
const STATS_PORT = 9001;
const TG_BOT     = process.env.TG_BOT    || '8697044933:AAEjLpqcCKIotwoLa69zdRYfaFyh44KY4tE';
const TG_CHAT    = process.env.TG_CHAT   || '1311004971';
const SERVER_IP  = process.env.SERVER_IP || '68.183.66.2';

const KEYS = {
  github:     process.env.GITHUB_TOKEN   || 'YOUR_GITHUB_TOKEN_HERE',
  gemini:     process.env.GEMINI_KEY     || 'AIzaSyBOQugdzwro6G-waQ0U9rK3SQGE-sT5AZQ',
  openrouter: process.env.OPENROUTER_KEY || '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',
  groq:       process.env.GROQ_API_KEY   || 'YOUR_GROQ_API_KEY_HERE',
  cerebras:   process.env.CEREBRAS_KEY   || 'csk-v889jd9xxyek98mrx4fpnknnc9pk462589eywtev32wf8dkm',
};

// ─────────────────────────────────────────────────────────────────────────────
//  BACKENDS
// ─────────────────────────────────────────────────────────────────────────────
const BACKENDS = {
  github: {
    url:    'https://models.inference.ai.azure.com/chat/completions',
    auth:   () => KEYS.github,
    active: () => !!KEYS.github,
    noTools: false,
    // GitHub Models require strict JSON Schema: additionalProperties:false on every object
    strip: ['store','user','service_tier','logprobs','top_logprobs','n',
            'frequency_penalty','presence_penalty'],
  },
  gemini: {
    url:    'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions',
    auth:   () => KEYS.gemini,
    active: () => !!KEYS.gemini,
    noTools: false,
    // Whitelist only params Gemini OpenAI-compat endpoint actually supports
    allowed: new Set(['model','messages','max_tokens','temperature','top_p','stream',
                      'stop','tools','tool_choice','response_format']),
    strip: [],
  },
  groq: {
    url:    'https://api.groq.com/openai/v1/chat/completions',
    auth:   () => KEYS.groq,
    active: () => !!KEYS.groq,
    noTools: false,
    // Groq: kimi-k2 and qwen3 have reliable tool calling. Llama 3.x has empty-args bug.
    strip: ['store','user','service_tier','logprobs','top_logprobs'],
  },
  cerebras: {
    url:    'https://api.cerebras.ai/v1/chat/completions',
    auth:   () => KEYS.cerebras,
    active: () => !!KEYS.cerebras,
    noTools: false, // Cerebras supports function calling
    // Cerebras does NOT support max_completion_tokens (OpenAI v2) — only max_tokens (v1)
    strip: ['store','user','service_tier','logprobs','top_logprobs','n',
            'frequency_penalty','presence_penalty','max_completion_tokens'],
  },
  openrouter: {
    url:    'https://openrouter.ai/api/v1/chat/completions',
    auth:   () => KEYS.openrouter,
    active: () => !!KEYS.openrouter,
    noTools: false,
    strip: ['store','user','service_tier'],
    extraHeaders: {
      'HTTP-Referer': 'https://openclaw.ai',
      'X-Title': 'Smart Router',
    },
  },
};

// ─────────────────────────────────────────────────────────────────────────────
//  ACTUAL FREE-TIER LIMITS  (verified March 2026)
//
//  GitHub Models (free, student plan):
//    High tier (GPT-4o class): 10 RPM, 50 RPD, 8k input / 4k output tokens
//    Low tier (GPT-4.1-mini/nano): 15 RPM, 150 RPD, 8k input / 4k output tokens
//    NOTE: Student GitHub Copilot is on "Student Plan" — same API limits as free
//
//  Gemini (Google AI Studio free key):
//    gemini-2.5-pro:        5 RPM,  100 RPD, 250k TPM
//    gemini-2.5-flash:     10 RPM,  250 RPD, 250k TPM  ← main model
//    gemini-2.5-flash-lite: 15 RPM, 1000 RPD, 250k TPM  ← best volume!
//    gemini-2.0-flash:      5 RPM,  ~500 RPD, 250k TPM
//
//  Groq (free):
//    llama-3.3-70b-versatile:     30 RPM, 14400 RPD  ← highest volume
//    moonshotai/kimi-k2-instruct:  3 RPM,  1000 RPD
//    qwen/qwen3-32b:               3 RPM,  1000 RPD
//
//  Cerebras (free):
//    llama3.1-8b:   30 RPM, 1000 RPD
//    llama-3.3-70b: 30 RPM, 1000 RPD (larger, better tool calling)
// ─────────────────────────────────────────────────────────────────────────────
const LIMITS = {
  // GitHub — small daily budgets, student plan doesn't increase API limits
  'github/gpt-4.1':                               { reqDay: 50,   rpm: 10 },
  'github/gpt-4.1-mini':                          { reqDay: 150,  rpm: 15 },
  'github/gpt-4.1-nano':                          { reqDay: 150,  rpm: 15 },
  'github/gpt-4o-mini':                           { reqDay: 150,  rpm: 15 },
  'github/gpt-4o':                                { reqDay: 50,   rpm: 10 },

  // Gemini — ACTUAL limits (reduced Dec 2025)
  'gemini/gemini-2.5-flash':                      { reqDay: 250,  rpm: 10,  tokDay: 1_000_000 },
  'gemini/gemini-2.5-flash-lite':                 { reqDay: 1000, rpm: 15,  tokDay: 1_000_000 },
  'gemini/gemini-2.0-flash':                      { reqDay: 500,  rpm: 5,   tokDay: 1_000_000 },

  // Groq — best volume for free tier
  'groq/llama-3.3-70b-versatile':                 { reqDay: 14400, rpm: 30 },
  'groq/moonshotai/kimi-k2-instruct':             { reqDay: 1000,  rpm: 3  },
  'groq/qwen/qwen3-32b':                          { reqDay: 1000,  rpm: 3  },

  // Cerebras fast inference (does support function calling)
  'cerebras/llama3.1-8b':                                 { reqDay: 1000,  rpm: 30 },
  'cerebras/qwen-3-235b-a22b-instruct-2507':              { reqDay: 1000,  rpm: 30 },

  // OpenRouter free models — emergency fallbacks (verified March 2026)
  'openrouter/nvidia/nemotron-3-super-120b-a12b:free':  { reqDay: 50, rpm: 5 },  // 120B, 256k ctx
  'openrouter/openai/gpt-oss-120b:free':                { reqDay: 50, rpm: 5 },  // 120B, 131k ctx
  'openrouter/openai/gpt-oss-20b:free':                 { reqDay: 50, rpm: 5 },  // 20B, fast
  'openrouter/qwen/qwen3-coder:free':                   { reqDay: 50, rpm: 5 },  // Qwen3 Coder
};

// Context window + max output per model (conservative, free-tier safe values)
// GitHub: 8k total context, 4k output — so messages budget = ~3.5k tokens
// Gemini: 1M context, 8k output — very generous
const MODEL_CTX = {
  'github/gpt-4.1':                { ctx: 8000,    out: 4000 },  // hard limit: 8000 tok
  'github/gpt-4.1-mini':           { ctx: 8000,    out: 4000 },
  'github/gpt-4.1-nano':           { ctx: 8000,    out: 4000 },
  'github/gpt-4o-mini':            { ctx: 8000,    out: 4000 },
  'github/gpt-4o':                 { ctx: 8000,    out: 4000 },
  'gemini/gemini-2.5-flash':       { ctx: 800000,  out: 8192 },  // 1M ctx, use 800k safely
  'gemini/gemini-2.5-flash-lite':  { ctx: 800000,  out: 8192 },
  'gemini/gemini-2.0-flash':       { ctx: 800000,  out: 8192 },
  'groq/llama-3.3-70b-versatile':  { ctx: 6000,    out: 2000 },  // 6000 TPM free: sys truncated
  'groq/moonshotai/kimi-k2-instruct': { ctx: 2000, out: 500 },  // 6000 TPM free tier
  'groq/qwen/qwen3-32b':           { ctx: 2000,   out: 500 },    // 6000 TPM free tier
  'cerebras/llama3.1-8b':                         { ctx: 8000,  out: 4000 },
  'cerebras/qwen-3-235b-a22b-instruct-2507':      { ctx: 8000,  out: 4000 },
  // OpenRouter free models (verified March 2026)
  'openrouter/nvidia/nemotron-3-super-120b-a12b:free': { ctx: 32000, out: 8192 },
  'openrouter/openai/gpt-oss-120b:free':               { ctx: 32000, out: 8192 },
  'openrouter/openai/gpt-oss-20b:free':                { ctx: 32000, out: 4096 },
  'openrouter/qwen/qwen3-coder:free':                  { ctx: 32000, out: 8192 },
};
const DEFAULT_CTX = { ctx: 32000, out: 8192 };

// ─────────────────────────────────────────────────────────────────────────────
//  MODEL CHAINS  (priority order per task type)
//
//  EXECUTION chain (tool calling):
//    Priority: reliability of tool calling > daily volume > speed
//    - Gemini 2.5-flash-lite: 1000 RPD, 15 RPM — best volume for tools
//    - Gemini 2.5-flash: 250 RPD, 10 RPM — best quality
//    - Gemini 2.0-flash: 500 RPD — large volume backup
//    - GitHub GPT-4.1 family: reliable TC but tiny daily budget (50-150)
//    - Groq kimi-k2 / qwen3: tool calling works (NOT llama — empty args bug)
//
//  CHAT chain (no tools):
//    Priority: volume > speed > quality
//    - Groq llama-3.3-70b: 14400 RPD — enormous free capacity
//    - Gemini models for quality
//    - GitHub for GPT quality when available
// ─────────────────────────────────────────────────────────────────────────────
const CHAINS = {
  execution: [
    { backend: 'gemini',   model: 'gemini-2.5-flash' },               // 250/day — best quality tool calling
    { backend: 'gemini',   model: 'gemini-2.0-flash' },               // 500/day — reliable fallback
    { backend: 'gemini',   model: 'gemini-2.5-flash-lite' },          // 1000/day — high volume
    { backend: 'cerebras', model: 'qwen-3-235b-a22b-instruct-2507' }, // 1000/day, 30 RPM — Qwen3 235B fast
    { backend: 'github',   model: 'gpt-4.1-mini' },                   // 150/day GitHub
    { backend: 'github',   model: 'gpt-4.1' },                        // 50/day GitHub quality
    { backend: 'github',   model: 'gpt-4.1-nano' },                   // 150/day fast
    { backend: 'github',   model: 'gpt-4o-mini' },                    // 150/day fallback
    { backend: 'github',   model: 'gpt-4o' },                         // 50/day last GitHub
    { backend: 'groq',       model: 'llama-3.3-70b-versatile' },         // 14400 RPD fallback (sys truncated)
    { backend: 'openrouter', model: 'nvidia/nemotron-3-super-120b-a12b:free' }, // 120B emergency fallback
    { backend: 'openrouter', model: 'openai/gpt-oss-120b:free' },     // 120B OpenAI emergency
    { backend: 'openrouter', model: 'openai/gpt-oss-20b:free' },      // 20B fast emergency
    // NOTE: Groq removed from execution — system message (~6000 tok) exceeds 6000 TPM limit
  ],
  code: [
    { backend: 'gemini',   model: 'gemini-2.5-flash' },
    { backend: 'gemini',   model: 'gemini-2.0-flash' },
    { backend: 'gemini',   model: 'gemini-2.5-flash-lite' },
    { backend: 'cerebras', model: 'qwen-3-235b-a22b-instruct-2507' },
    { backend: 'github',   model: 'gpt-4.1' },
    { backend: 'github',   model: 'gpt-4.1-mini' },
    { backend: 'github',   model: 'gpt-4.1-nano' },
    { backend: 'openrouter', model: 'qwen/qwen3-coder:free' },
  ],
  analysis: [
    { backend: 'gemini',   model: 'gemini-2.5-flash' },
    { backend: 'gemini',   model: 'gemini-2.5-flash-lite' },
    { backend: 'gemini',   model: 'gemini-2.0-flash' },
    { backend: 'cerebras', model: 'qwen-3-235b-a22b-instruct-2507' },
    { backend: 'github',   model: 'gpt-4.1' },
    { backend: 'github',   model: 'gpt-4.1-mini' },
  ],
  task: [
    { backend: 'gemini',   model: 'gemini-2.5-flash-lite' },
    { backend: 'gemini',   model: 'gemini-2.5-flash' },
    { backend: 'gemini',   model: 'gemini-2.0-flash' },
    { backend: 'cerebras', model: 'qwen-3-235b-a22b-instruct-2507' },
    { backend: 'github',   model: 'gpt-4.1' },
    { backend: 'github',   model: 'gpt-4.1-mini' },
  ],
  chat: [
    { backend: 'groq',     model: 'llama-3.3-70b-versatile' }, // 14400/day — huge volume for chat
    { backend: 'gemini',   model: 'gemini-2.5-flash-lite' },
    { backend: 'gemini',   model: 'gemini-2.5-flash' },
    { backend: 'github',   model: 'gpt-4.1-mini' },
    { backend: 'github',   model: 'gpt-4.1-nano' },
    { backend: 'gemini',   model: 'gemini-2.0-flash' },
    { backend: 'cerebras', model: 'llama3.1-8b' },
    { backend: 'github',   model: 'gpt-4.1' },
  ],
};

// ─────────────────────────────────────────────────────────────────────────────
//  SCHEMA SANITIZER
//  Both GitHub Models and Gemini (OpenAI-compat, since Nov 2025) require:
//    - additionalProperties: false on EVERY object schema
//    - No $ref, $defs, $schema, $id, unevaluatedProperties
//    - anyOf/oneOf/allOf allowed (TypeBox Optional generates these)
// ─────────────────────────────────────────────────────────────────────────────
const SCHEMA_DROP = new Set([
  '$schema', '$id', '$defs', '$ref', 'unevaluatedProperties',
  'if', 'then', 'else', 'examples', 'default',
]);

function sanitizeSchema(schema) {
  if (!schema || typeof schema !== 'object' || Array.isArray(schema)) return schema;
  const out = {};
  for (const [k, v] of Object.entries(schema)) {
    if (SCHEMA_DROP.has(k)) continue;
    if (k === 'additionalProperties') { out.additionalProperties = false; continue; }
    if (k === 'required' && Array.isArray(v) && v.length === 0) continue;
    if (k === 'properties' && typeof v === 'object' && !Array.isArray(v)) {
      out.properties = Object.fromEntries(
        Object.entries(v).map(([pk, pv]) => [pk, sanitizeSchema(pv)])
      );
    } else if (k === 'items') {
      out.items = Array.isArray(v) ? v.map(s => sanitizeSchema(s)) : sanitizeSchema(v);
    } else if ((k === 'anyOf' || k === 'oneOf' || k === 'allOf') && Array.isArray(v)) {
      const c = v.map(s => sanitizeSchema(s)).filter(Boolean);
      if (c.length) out[k] = c;
    } else {
      out[k] = v;
    }
  }
  if (out.type === 'object' && !('additionalProperties' in out)) out.additionalProperties = false;
  return out;
}

// ─────────────────────────────────────────────────────────────────────────────
//  TOOL COMPRESSION
//  OpenClaw sends ~26kb of tool schemas. After compression: ~3-4kb.
//  Step 1: strip all parameter descriptions, cap tool description to 80 chars.
//  Step 2 (emergency >8kb): keep only name + required params.
// ─────────────────────────────────────────────────────────────────────────────
function stripDescriptions(schema) {
  if (!schema || typeof schema !== 'object' || Array.isArray(schema)) return schema;
  const out = {};
  for (const [k, v] of Object.entries(schema)) {
    if (k === 'description') continue;
    if (k === 'properties' && typeof v === 'object') {
      out.properties = Object.fromEntries(
        Object.entries(v).map(([pk, pv]) => [pk, stripDescriptions(pv)])
      );
    } else if (k === 'items') {
      out.items = Array.isArray(v) ? v.map(s => stripDescriptions(s)) : stripDescriptions(v);
    } else {
      out[k] = v;
    }
  }
  return out;
}

function fixMessageToolSchema(fn) {
  // OpenClaw marks `buttons` and `action` as required but both have defaults.
  // Models that omit them get a validation error → inject defaults instead of requiring them.
  if (fn.name === 'message' && fn.parameters?.required) {
    const params = JSON.parse(JSON.stringify(fn.parameters)); // deep copy
    params.required = params.required.filter(r => r !== 'buttons' && r !== 'action');
    return { ...fn, parameters: params };
  }
  return fn;
}

function injectMessageButtons(data) {
  // If the LLM returned a message tool call without buttons/action, inject defaults
  // so OpenClaw schema validation doesn't fail with "missing properties: buttons/action"
  if (!data?.choices) return data;
  for (const choice of data.choices) {
    const toolCalls = choice?.message?.tool_calls;
    if (!toolCalls) continue;
    for (const tc of toolCalls) {
      if (tc?.function?.name !== 'message') continue;
      try {
        const args = JSON.parse(tc.function.arguments || '{}');
        let changed = false;
        if (!('buttons' in args)) { args.buttons = []; changed = true; }
        if (!('action' in args))  { args.action  = 'send'; changed = true; }
        if (changed) tc.function.arguments = JSON.stringify(args);
      } catch (_) {}
    }
  }
  return data;
}


function compressTools(tools) {
  if (!tools?.length) return tools;
  const compressed = tools.map(t => {
    const fn = fixMessageToolSchema(t.function || t);
    return {
      type: 'function',
      function: {
        name: fn.name,
        description: (fn.description || '').slice(0, 80),
        parameters: sanitizeSchema(
          stripDescriptions(fn.parameters || { type: 'object', properties: {} })
        ),
      },
    };
  });
  if (JSON.stringify(compressed).length <= 8000) return compressed;
  // Emergency: absolute minimum — just names and required param types
  return tools.map(t => {
    const fn  = t.function || t;
    const req = fn.parameters?.required || [];
    const props = fn.parameters?.properties || {};
    return {
      type: 'function',
      function: {
        name: fn.name,
        parameters: {
          type: 'object',
          additionalProperties: false,
          required: req,
          properties: Object.fromEntries(req.map(k => [k, { type: props[k]?.type || 'string' }])),
        },
      },
    };
  });
}

// ─────────────────────────────────────────────────────────────────────────────
//  CONTEXT COMPRESSION
//  Walk backwards through messages, keeping as many as fit in the budget.
//  Oversized individual messages (tool outputs) are truncated.
//
//  IMPORTANT: The budget is per-model. GitHub has tiny context (~3.5k tokens
//  for messages). Gemini has up to 800k. We use the actual MODEL_CTX values.
// ─────────────────────────────────────────────────────────────────────────────
function estTok(msg) {
  const c = typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content || '');
  return Math.ceil(c.length / 3.5) + 10;
}

function trimMsgContent(msg, maxTok) {
  const c = typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content || '');
  if (c.length / 3.5 <= maxTok) return msg;
  return { ...msg, content: c.slice(0, maxTok * 3) + '\n[...trimmed]' };
}

function compressMessages(messages, budget) {
  if (!messages?.length) return messages;
  budget = Math.max(budget || 4000, 500);

  let system = messages.filter(m => m.role === 'system');
  const nonSys = messages.filter(m => m.role !== 'system');
  if (!nonSys.length) return messages;

  // Truncate system if too large for this model's budget (e.g. Cerebras/Groq ctx=6-8k)
  let sysTok = system.reduce((s, m) => s + estTok(m), 0);
  const sysAllowance = Math.floor(budget * 0.6);
  if (sysTok > sysAllowance && sysAllowance > 300) {
    const maxPerSys = Math.floor(sysAllowance / Math.max(system.length, 1));
    system = system.map(m => trimMsgContent(m, maxPerSys));
    sysTok = system.reduce((s, m) => s + estTok(m), 0);
    console.log('[router] sys-truncate: sysTok=' + sysTok + ' budget=' + budget);
  }

  const perMsgMax = Math.min(3000, Math.floor(budget * 0.4));
  let   remaining = budget - sysTok - 60;
  const kept      = [];

  for (let i = nonSys.length - 1; i >= 0; i--) {
    const m = trimMsgContent(nonSys[i], perMsgMax);
    const t = estTok(m);
    if (remaining <= 0 && kept.length >= 1) break; // budget gone — keep at least 1
    if (t > remaining && kept.length > 0) break;
    remaining -= t;
    kept.unshift(m);
  }

  // Emergency: budget was too small even for 1 msg → force last user message truncated
  if (kept.length === 0 && nonSys.length > 0) {
    const last = nonSys[nonSys.length - 1];
    kept.push(trimMsgContent(last, Math.max(perMsgMax, 150)));
  }

  // Always keep the first user message (original task) — prevents model from losing context
  // after many tool call rounds when earlier messages get compressed away.
  const firstUser = nonSys.find(m => m.role === 'user');
  if (firstUser && kept.length > 0 && kept[0] !== firstUser) {
    const firstUserTrunc = trimMsgContent(firstUser, perMsgMax);
    if (!kept.some(m => m === firstUser || (m.role === 'user' &&
        typeof m.content === 'string' && typeof firstUser.content === 'string' &&
        m.content === firstUser.content))) {
      kept.unshift(firstUserTrunc); // prepend original task
    }
  }

  // Drop dangling tool responses at start (they need preceding assistant+tool_call)
  while (kept.length > 1 && kept[0].role === 'tool') kept.shift();

  const dropped = nonSys.length - kept.length;
  if (dropped === 0) return [...system, ...kept];

  const note = { role: 'system', content: '[' + dropped + ' older messages omitted]' };
  console.log('[router] ctx-compress: dropped=' + dropped + ' kept=' + kept.length + ' budget=' + budget);
  return [...system, note, ...kept];
}

// ─────────────────────────────────────────────────────────────────────────────
//  TASK CLASSIFICATION
//  If request has tools array → ALWAYS execution chain (tool-capable models only).
// ─────────────────────────────────────────────────────────────────────────────
const KW = {
  code:     ['код','code','python','javascript','typescript','script','скрипт',
             'debug','fix','bug','import','function','async','bash','sql',
             'git','docker','def ','class ','traceback','syntax error'],
  analysis: ['поясни','explain','аналіз','analyze','порівняй','compare',
             'дослідж','research','розгорнуто','детально','чому','why','як працює'],
  task:     ['зроби','виконай','створи','реалізуй','налаштуй','встанови',
             'запусти','збережи','запуш','push','deploy','setup','install'],
};

function classifyMessages(messages) {
  const nonSys = messages.filter(m => m.role !== 'system');
  const recent5 = nonSys.slice(-5);
  if (recent5.some(m => Array.isArray(m.tool_calls) && m.tool_calls.length) ||
      recent5.some(m => m.role === 'tool')) return 'execution';
  const text = nonSys
    .filter(m => m.role === 'user')
    .map(m => typeof m.content === 'string' ? m.content : JSON.stringify(m.content))
    .join(' ').toLowerCase();
  if (KW.code.some(k => text.includes(k)))     return 'code';
  if (KW.task.some(k => text.includes(k)))     return 'task';
  if (KW.analysis.some(k => text.includes(k))) return 'analysis';
  return 'chat';
}

function getChain(messages, hasTools) {
  if (hasTools) return { type: 'execution', chain: CHAINS.execution };
  const type = classifyMessages(messages);
  return { type, chain: CHAINS[type] || CHAINS.chat };
}

// ─────────────────────────────────────────────────────────────────────────────
//  COOLDOWN & USAGE TRACKING
// ─────────────────────────────────────────────────────────────────────────────
let dailyDate  = new Date().toDateString();
let dailyUsage = {};
let totalUsage = {};
const cooldowns = {};
const rpmCounters = {}; // { key: [timestamp, ...] } rolling 60s window
const stats = { requests: 0, errors: 0, byType: {}, byModel: {}, startTime: Date.now() };

function resetDayIfNeeded() {
  const today = new Date().toDateString();
  if (dailyDate !== today) { dailyDate = today; dailyUsage = {}; }
}

function isOnCooldown(key) { return Date.now() < (cooldowns[key] || 0); }

function setCooldown(key, seconds) {
  cooldowns[key] = Date.now() + Math.min(seconds, 86400) * 1000;
  console.log('[router] cooldown: ' + key + ' for ' + Math.round(seconds) + 's');
}

// RPM tracking: sliding 60-second window
function checkRpm(key) {
  const lim = LIMITS[key]?.rpm;
  if (!lim) return true; // no RPM limit defined
  const now = Date.now();
  if (!rpmCounters[key]) rpmCounters[key] = [];
  rpmCounters[key] = rpmCounters[key].filter(t => now - t < 60000); // keep last 60s
  return rpmCounters[key].length < lim;
}

function trackRpm(key) {
  if (!rpmCounters[key]) rpmCounters[key] = [];
  rpmCounters[key].push(Date.now());
}

function trackUsage(backend, model, usage) {
  resetDayIfNeeded();
  const key  = backend + '/' + model;
  const zero = () => ({ req: 0, prompt: 0, completion: 0, total: 0 });
  if (!dailyUsage[key]) dailyUsage[key] = zero();
  if (!totalUsage[key]) totalUsage[key] = zero();
  dailyUsage[key].req++;
  totalUsage[key].req++;
  if (usage) {
    const p = usage.prompt_tokens || 0, c = usage.completion_tokens || 0;
    const t = usage.total_tokens  || (p + c);
    dailyUsage[key].prompt     += p; totalUsage[key].prompt     += p;
    dailyUsage[key].completion += c; totalUsage[key].completion += c;
    dailyUsage[key].total      += t; totalUsage[key].total      += t;
    // Auto-cooldown to midnight when token quota is 95% exhausted
    const lim = LIMITS[key];
    if (lim?.tokDay && dailyUsage[key].total >= lim.tokDay * 0.95) {
      setCooldown(key, Math.ceil((new Date().setHours(24,0,0,0) - Date.now()) / 1000));
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
//  RATE-LIMIT RESPONSE PARSER
//  GitHub Models returns wait time in the body, not Retry-After header.
//  "Please wait 28889 seconds before retrying."
//  Gemini RESOURCE_EXHAUSTED = short per-minute limit → 30s cooldown.
// ─────────────────────────────────────────────────────────────────────────────
function parseRetryAfter(headers, bodyText, backend) {
  const hdr = headers?.get?.('retry-after') || headers?.get?.('x-ratelimit-reset-requests');
  if (hdr) { const n = parseInt(hdr, 10); if (n > 0 && n < 86400) return n; }
  const m = (bodyText || '').match(/wait\s+(\d+)\s+second/i) ||
            (bodyText || '').match(/retry[_\- ]after[": ]+(\d+)/i) ||
            (bodyText || '').match(/retry in (\d+(?:\.\d+)?)s/i);
  if (m) return Math.min(Math.ceil(parseFloat(m[1])), 86400);
  // Gemini per-minute quota exhausted → short cooldown (resets every minute)
  if (backend === 'gemini' && (bodyText || '').includes('RESOURCE_EXHAUSTED')) return 30;
  return 60;
}

// ─────────────────────────────────────────────────────────────────────────────
//  SINGLE BACKEND CALL
// ─────────────────────────────────────────────────────────────────────────────
async function callBackend(backend, model, reqBody, stream) {
  const cfg = BACKENDS[backend];
  if (!cfg?.active()) throw Object.assign(new Error('INACTIVE:' + backend), { skip: true });

  const key = backend + '/' + model;
  if (isOnCooldown(key)) throw Object.assign(new Error('COOLDOWN:' + key), { skip: true });

  // Proactive daily-limit check
  resetDayIfNeeded();
  const lim = LIMITS[key];
  if (lim?.reqDay && (dailyUsage[key]?.req || 0) >= lim.reqDay) {
    setCooldown(key, Math.ceil((new Date().setHours(24,0,0,0) - Date.now()) / 1000));
    throw Object.assign(new Error('DAILY_LIMIT:' + key), { skip: true });
  }

  // Proactive RPM check
  if (!checkRpm(key)) {
    throw Object.assign(new Error('RPM_LIMIT:' + key), { skip: true });
  }

  // Build payload
  const mlim     = MODEL_CTX[key] || DEFAULT_CTX;
  const tools    = (!cfg.noTools && reqBody.tools?.length) ? compressTools(reqBody.tools) : undefined;
  const toolsEst = tools ? Math.ceil(JSON.stringify(tools).length / 3.5) : 0;

  // Message budget: ctx minus output minus tools overhead minus safety margin
  // For GitHub (ctx=8000, out=4000): budget = 8000 - 4000 - toolsEst - 300 ≈ 3500 tokens
  // For Gemini (ctx=800000): budget = ~790k tokens
  const rawBudget = mlim.ctx - mlim.out - toolsEst - 300;
  const msgBudget = Math.max(rawBudget, 500); // absolute floor: never less than 500 tok

  const messages = compressMessages(reqBody.messages || [], msgBudget);

  let payload = { ...reqBody, model, messages };
  if (tools)       { payload.tools = tools; }
  else             { delete payload.tools; delete payload.tool_choice; }
  if (cfg.noTools) { delete payload.tools; delete payload.tool_choice; }

  // Cap output tokens
  if ((payload.max_tokens || 0) > mlim.out)            payload.max_tokens = mlim.out;
  if ((payload.max_completion_tokens || 0) > mlim.out) payload.max_completion_tokens = mlim.out;
  if (!payload.max_tokens)                             payload.max_tokens = mlim.out;

  for (const k of (cfg.strip || [])) delete payload[k];

  // Gemini: whitelist only supported params
  if (cfg.allowed) {
    payload = Object.fromEntries(Object.entries(payload).filter(([k]) => cfg.allowed.has(k)));
  }

  payload.stream = stream || false;

  const sz  = Math.round(JSON.stringify(payload).length / 1024);
  const tsz = Math.round(JSON.stringify(payload.tools || []).length / 1024);
  const msgCount = payload.messages?.length || 0;
  console.log('[router] -> ' + key + ' payload=' + sz + 'kb msgs=' + msgCount + (tsz ? ' tools=' + tsz + 'kb' : ''));

  trackRpm(key);

  const res = await fetch(cfg.url, {
    method:  'POST',
    headers: {
      'Content-Type':  'application/json',
      'Authorization': 'Bearer ' + cfg.auth(),
      ...(cfg.extraHeaders || {}),
    },
    body:   JSON.stringify(payload),
    signal: AbortSignal.timeout(90_000),
  });

  if (res.status === 429) {
    const body = await res.text();
    const wait = parseRetryAfter(res.headers, body, backend);
    setCooldown(key, wait);
    throw Object.assign(new Error('RATE_LIMIT:' + key + ' wait=' + wait + 's'), { skip: true });
  }

  return res;
}


function isNoReplyResponse(data, hasTools) {
  // Returns true if model returned plain text (no tool calls) when tools were expected.
  // OpenClaw treats any non-tool-call response as NO_REPLY, so we retry next model.
  if (!hasTools || !data?.choices?.length) return false;
  const choice = data.choices[0];
  const hasToolCalls = (choice?.message?.tool_calls?.length || 0) > 0;
  return !hasToolCalls && choice?.finish_reason === 'stop';
}
// ─────────────────────────────────────────────────────────────────────────────
//  MAIN PROXY  POST /v1/chat/completions
// ─────────────────────────────────────────────────────────────────────────────
const app = express();
app.use(express.json({ limit: '50mb' }));

app.post('/v1/chat/completions', async (req, res) => {
  stats.requests++;
  const { messages = [], stream = false } = req.body;
  const hasTools = !!(req.body.tools?.length);
  const { type, chain } = getChain(messages, hasTools);

  stats.byType[type] = (stats.byType[type] || 0) + 1;
  const bsz = Math.round(JSON.stringify(req.body).length / 1024);
  const tsz = Math.round(JSON.stringify(req.body.tools || []).length / 1024);
  console.log(
    '[router] ' + new Date().toISOString().slice(11, 19) +
    ' type=' + type + ' tools=' + hasTools +
    ' body=' + bsz + 'kb' + (tsz ? ' toolSchema=' + tsz + 'kb' : '')
  );

  let lastErr = 'no backends';
  let githubSchemaFailed = false;

  mainLoop: for (const { backend, model } of chain) {
    const key = backend + '/' + model;

    // Skip all remaining GitHub backends after a schema validation error
    // (they all share the same Azure validator — if one fails, all will)
    if (githubSchemaFailed && backend === 'github') {
      console.log('[router] SKIP ' + key + ' (github schema-fail propagated)');
      continue;
    }

    try {
      const upstream = await callBackend(backend, model, req.body, stream);

      if (upstream.ok) {
        stats.byModel[key] = (stats.byModel[key] || 0) + 1;
        console.log('[router] OK <- ' + key);
        if (stream) {
          res.setHeader('Content-Type', 'text/event-stream');
          res.setHeader('Cache-Control', 'no-cache');
          upstream.body.pipe(res);
          trackUsage(backend, model, null);
        } else {
          const data = await upstream.json();

          // NO_REPLY guard: model returned text when tools expected → retry next
          if (isNoReplyResponse(data, hasTools)) {
            const txt = typeof data.choices[0]?.message?.content === 'string'
              ? data.choices[0].message.content.trim().slice(0, 60) : '';
            console.log('[router] NO_REPLY-SKIP ' + key + ': ' + JSON.stringify(txt));
            lastErr = 'NO_REPLY:' + key;
            trackUsage(backend, model, data.usage || null);
            continue mainLoop;
          }

          if (data.choices) data._router = { backend, model, type };
          injectMessageButtons(data);
          res.status(200).json(data);
          trackUsage(backend, model, data.usage || null);
        }
        return;
      }

      const errText = await upstream.text();
      lastErr = upstream.status + ': ' + errText.slice(0, 600);
      console.log('[router] FAIL ' + key + ' [' + upstream.status + ']: ' + errText.slice(0, 300));

      if (upstream.status === 400 && backend === 'github') {
        const lower = errText.toLowerCase();
        if (lower.includes('schema') || lower.includes('invalid') || lower.includes('function')) {
          console.log('[router] GitHub schema error — skipping all github backends');
          githubSchemaFailed = true;
        }
      }

      if (upstream.status === 429) {
        const wait = parseRetryAfter(upstream.headers, errText, backend);
        setCooldown(key, wait);
      }

    } catch (e) {
      if (e.skip) {
        console.log('[router] SKIP ' + key + ' (' + (e.message || '').split(':')[0] + ')');
      } else {
        console.log('[router] ERR  ' + key + ': ' + (e.message || '').slice(0, 200));
      }
      lastErr = e.message || 'error';
    }
  }

  stats.errors++;
  console.log('[router] 503 all backends failed: ' + lastErr.slice(0, 200));
  res.status(503).json({
    error: { message: 'All backends failed. Last: ' + lastErr, type: 'router_exhausted' },
  });
});

app.get('/v1/models', (_req, res) => {
  res.json({ object: 'list', data: [{ id: 'gpt-4o', object: 'model', owned_by: 'router' }] });
});

app.get('/health', (_req, res) => {
  const active = Object.entries(BACKENDS).filter(([, b]) => b.active()).map(([n]) => n);
  const cd = Object.fromEntries(
    Object.entries(cooldowns).filter(([, v]) => Date.now() < v)
      .map(([k, v]) => [k, Math.ceil((v - Date.now()) / 1000) + 's'])
  );
  const rpm = Object.fromEntries(
    Object.entries(rpmCounters)
      .filter(([, arr]) => arr.length > 0)
      .map(([k, arr]) => [k, arr.filter(t => Date.now() - t < 60000).length + '/' + (LIMITS[k]?.rpm || '?') + ' rpm'])
  );
  res.json({ ok: true, uptime_s: Math.floor((Date.now() - stats.startTime) / 1000), active_backends: active, stats, cooldowns: cd, rpm });
});

app.get('/stats', (_req, res) => res.json(buildStatsData()));

app.post('/send-stats', async (_req, res) => {
  try { await sendTelegramStats(); res.json({ ok: true }); }
  catch (e) { res.status(500).json({ error: e.message }); }
});

app.post('/tg-callback', express.json(), async (req, res) => {
  const cb = req.body?.callback_query;
  if (cb?.data === 'refresh_stats') {
    try {
      await tgCall('answerCallbackQuery', { callback_query_id: cb.id, text: 'Оновлюю...', show_alert: false });
      await tgCall('editMessageText', {
        chat_id: cb.message.chat.id, message_id: cb.message.message_id,
        text: buildStatsText(), parse_mode: 'Markdown',
        reply_markup: JSON.stringify({ inline_keyboard: [statsKeyboard()] }),
      });
    } catch (e) { console.error('[tg-cb] ' + e.message); }
  }
  res.json({ ok: true });
});

// ─────────────────────────────────────────────────────────────────────────────
//  STATS
// ─────────────────────────────────────────────────────────────────────────────
function buildStatsData() {
  resetDayIfNeeded();
  const allKeys = new Set([...Object.keys(dailyUsage), ...Object.keys(totalUsage), ...Object.keys(LIMITS)]);
  const models = {};
  for (const key of allKeys) {
    const lim = LIMITS[key] || {};
    const day = dailyUsage[key] || { req: 0, prompt: 0, completion: 0, total: 0 };
    const tot = totalUsage[key] || { req: 0, prompt: 0, completion: 0, total: 0 };
    const reqRemain = lim.reqDay != null ? Math.max(0, lim.reqDay - day.req) : null;
    const tokRemain = lim.tokDay != null ? Math.max(0, lim.tokDay - day.total) : null;
    const reqPct    = lim.reqDay ? Math.min(100, Math.round(day.req / lim.reqDay * 100)) : null;
    const tokPct    = lim.tokDay ? Math.min(100, Math.round(day.total / lim.tokDay * 100)) : null;
    const rpmNow    = (rpmCounters[key] || []).filter(t => Date.now() - t < 60000).length;
    models[key] = { day, total: tot, limits: lim, reqRemain, tokRemain, reqPct, tokPct, rpmNow };
  }
  return {
    date: dailyDate,
    uptime_s: Math.floor((Date.now() - stats.startTime) / 1000),
    active_backends: Object.entries(BACKENDS).filter(([, b]) => b.active()).map(([n]) => n),
    total_requests: stats.requests,
    total_errors: stats.errors,
    by_type: stats.byType,
    cooldowns: Object.fromEntries(
      Object.entries(cooldowns).filter(([, v]) => Date.now() < v)
        .map(([k, v]) => [k, Math.ceil((v - Date.now()) / 1000) + 's'])
    ),
    models,
  };
}

function buildStatsText() {
  const d   = buildStatsData();
  const upH = Math.floor(d.uptime_s / 3600);
  const upM = Math.floor((d.uptime_s % 3600) / 60);
  let text  = '*Smart Router — Статистика* (' + d.date + ')\n';
  text += 'Uptime: ' + upH + 'г ' + upM + 'хв | Запити: ' + d.total_requests + ' | Помилки: ' + d.total_errors + '\n';
  text += 'Backends: ' + d.active_backends.join(', ') + '\n\n';
  const used = Object.entries(d.models)
    .filter(([, v]) => v.day.req > 0)
    .sort(([, a], [, b]) => b.day.req - a.day.req);
  if (!used.length) { text += '_Сьогодні запитів ще не було_\n'; }
  else {
    for (const [key, v] of used) {
      const short = key.replace('moonshotai/', '').replace('meta-llama/', '').replace(':free', '');
      const bar = v.reqPct != null
        ? '[' + '▓'.repeat(Math.round(v.reqPct / 10)) + '░'.repeat(10 - Math.round(v.reqPct / 10)) + '] ' + v.reqPct + '%'
        : '';
      const reqInfo = v.limits.reqDay
        ? v.day.req + '/' + v.limits.reqDay + ' (залишилось: ' + v.reqRemain + ')'
        : v.day.req + ' req';
      const tokInfo = v.day.total > 0 ? ' | ' + (v.day.total / 1000).toFixed(1) + 'k tok' : '';
      text += '*' + short + '*\n' + bar + '\n' + reqInfo + tokInfo + '\n\n';
    }
  }
  if (Object.keys(d.cooldowns).length) {
    text += 'Cooldowns: ' + Object.entries(d.cooldowns).map(([k, v]) => k.split('/').pop() + ': ' + v).join(', ') + '\n';
  }
  return text;
}

function statsKeyboard() {
  return [
    { text: '📊 Детально', url: 'http://' + SERVER_IP + ':9001/' },
    { text: '🔄 Оновити', callback_data: 'refresh_stats' },
  ];
}

async function tgCall(method, body) {
  const r = await fetch('https://api.telegram.org/bot' + TG_BOT + '/' + method, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  return r.json();
}

async function sendTelegramStats() {
  await tgCall('sendMessage', {
    chat_id: TG_CHAT, text: buildStatsText(), parse_mode: 'Markdown',
    reply_markup: JSON.stringify({ inline_keyboard: [statsKeyboard()] }),
  });
}

// ─────────────────────────────────────────────────────────────────────────────
//  PUBLIC STATS HTML PAGE  (port 9001)
// ─────────────────────────────────────────────────────────────────────────────
const COLORS = {
  github: '#24292e', gemini: '#4285f4', groq: '#f55036',
  cerebras: '#7b2fff', openrouter: '#6366f1',
};

function buildHtml() {
  const d    = buildStatsData();
  const upH  = Math.floor(d.uptime_s / 3600);
  const upM  = Math.floor((d.uptime_s % 3600) / 60);
  const all  = Object.entries(d.models).sort(([, a], [, b]) => (b.day.req + b.total.req) - (a.day.req + a.total.req));

  let rows = '';
  for (const [key, v] of all) {
    const [be]  = key.split('/');
    const col   = COLORS[be] || '#555';
    const short = key.split('/').slice(1).join('/').replace(':free', '');
    const cdBadge = d.cooldowns[key] ? '<span class="cd">CD ' + d.cooldowns[key] + '</span>' : '';
    const rpmBadge = v.rpmNow > 0 ? '<span class="rpm">' + v.rpmNow + '/' + (v.limits.rpm || '?') + ' rpm</span>' : '';
    const reqTxt = v.limits.reqDay
      ? v.day.req + ' / ' + v.limits.reqDay + ' <span class="rem">(' + v.reqRemain + ' left)</span>'
      : v.day.req + ' <span class="unl">∞</span>';
    const tokTxt = v.day.total > 0
      ? (v.day.total / 1000).toFixed(1) + 'k / ' + (v.total.total / 1000).toFixed(1) + 'k all'
      : '—';
    const bar = v.reqPct != null
      ? '<div class="bw"><div class="b" style="width:' + v.reqPct + '%;background:' + col + '"></div></div>' : '';
    const inactive = d.active_backends.includes(be) ? '' : ' ina';
    rows += '<tr class="mr' + inactive + '"><td>' +
      '<span class="badge" style="background:' + col + '">' + be + '</span>' +
      '<span class="mn">' + short + cdBadge + rpmBadge + '</span></td>' +
      '<td>' + reqTxt + bar + '</td><td>' + tokTxt + '</td><td class="c">' + v.total.req + '</td></tr>\n';
  }

  const typeList = Object.entries(d.by_type).map(([t, n]) => '<span class="tb">' + t + ': ' + n + '</span>').join('');

  return `<!DOCTYPE html>
<html lang="uk"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Smart Router</title><meta http-equiv="refresh" content="30">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#0f1117;color:#e2e8f0;min-height:100vh}
.hdr{background:linear-gradient(135deg,#1e2130,#252840);padding:24px 32px;border-bottom:1px solid #2d3148}
.hdr h1{font-size:22px;font-weight:700;color:#fff}.sub{color:#8892a4;font-size:13px;margin-top:4px}
.meta{display:flex;gap:16px;margin-top:16px;flex-wrap:wrap}
.mi{background:#1a1d2e;border:1px solid #2d3148;border-radius:8px;padding:10px 16px}
.mi .v{font-size:22px;font-weight:700;color:#7dd3fc}.mi .l{font-size:11px;color:#64748b;text-transform:uppercase}
.cnt{padding:24px 32px}.sec{font-size:12px;font-weight:600;color:#64748b;text-transform:uppercase;letter-spacing:.8px;margin:0 0 12px}
.chips{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:20px}
.chip{padding:4px 12px;border-radius:20px;font-size:12px;font-weight:600;color:#fff}
.types{margin-bottom:20px}.tb{display:inline-block;background:#1e3a5f;color:#7dd3fc;padding:3px 10px;border-radius:4px;font-size:12px;margin:2px}
table{width:100%;border-collapse:collapse;background:#1a1d2e;border:1px solid #2d3148;border-radius:10px;overflow:hidden}
thead th{background:#252840;padding:10px 14px;text-align:left;font-size:11px;color:#64748b;text-transform:uppercase;font-weight:600}
tr.mr td{padding:12px 14px;border-top:1px solid #252840;vertical-align:middle}
tr.mr.ina{opacity:.35}tr.mr:hover{background:#252840}
.badge{display:inline-block;padding:2px 7px;border-radius:4px;font-size:10px;font-weight:700;color:#fff;text-transform:uppercase;margin-right:4px}
.mn{font-size:12px;color:#94a3b8;margin-top:3px;display:block}
.bw{height:5px;background:#2d3148;border-radius:3px;margin-top:5px;overflow:hidden}
.b{height:100%;border-radius:3px}.rem{color:#4ade80;font-size:12px}.unl{color:#7dd3fc;font-size:12px}.c{text-align:center;color:#64748b}
.cd{background:#7c3aed22;color:#a78bfa;border:1px solid #7c3aed55;border-radius:4px;padding:1px 5px;font-size:10px;margin-left:4px}
.rpm{background:#0f3460;color:#60a5fa;border:1px solid #1d4ed855;border-radius:4px;padding:1px 5px;font-size:10px;margin-left:4px}
.note{text-align:center;color:#334155;font-size:11px;padding:16px}
</style></head>
<body>
<div class="hdr">
  <h1>Smart Router</h1>
  <div class="sub">Автооновлення кожні 30 сек &nbsp;·&nbsp; ${new Date().toLocaleString('uk-UA')}</div>
  <div class="meta">
    <div class="mi"><div class="v">${d.total_requests}</div><div class="l">Запитів</div></div>
    <div class="mi"><div class="v">${d.total_errors}</div><div class="l">Помилок</div></div>
    <div class="mi"><div class="v">${upH}г ${upM}хв</div><div class="l">Uptime</div></div>
    <div class="mi"><div class="v">${d.date}</div><div class="l">День</div></div>
  </div>
</div>
<div class="cnt">
  <div class="sec">Активні backends</div>
  <div class="chips">${d.active_backends.map(b => `<div class="chip" style="background:${COLORS[b]||'#555'}">${b}</div>`).join('')}</div>
  <div class="sec">Типи запитів</div>
  <div class="types">${typeList || '<span style="color:#334155">—</span>'}</div>
  <div class="sec">Використання по моделях (актуальні ліміти 2026)</div>
  <table>
    <thead><tr><th>Модель</th><th>Запити (сьогодні / ліміт)</th><th>Токени (сьогодні / всього)</th><th>Всього</th></tr></thead>
    <tbody>${rows}</tbody>
  </table>
  <div class="note">Автооновлення кожні 30 сек</div>
</div></body></html>`;
}

const statsApp = express();
statsApp.get('/', (_req, res) => { res.setHeader('Content-Type', 'text/html; charset=utf-8'); res.send(buildHtml()); });
statsApp.get('/api', (_req, res) => res.json(buildStatsData()));

// ─────────────────────────────────────────────────────────────────────────────
//  START
// ─────────────────────────────────────────────────────────────────────────────
app.listen(PORT, '127.0.0.1', () => {
  const active = Object.entries(BACKENDS).filter(([, b]) => b.active()).map(([n]) => n);
  console.log('[smart-router] :' + PORT + ' | active: ' + active.join(', '));
  // Log actual daily budgets for visibility
  const topModels = ['gemini/gemini-2.5-flash-lite','gemini/gemini-2.5-flash','groq/llama-3.3-70b-versatile','github/gpt-4.1-mini'];
  for (const k of topModels) {
    const l = LIMITS[k];
    if (l) console.log('[limits] ' + k + ': ' + l.reqDay + '/day, ' + (l.rpm||'?') + ' RPM');
  }
});
statsApp.listen(STATS_PORT, '0.0.0.0', () => {
  console.log('[stats]        :' + STATS_PORT + ' | http://' + SERVER_IP + ':' + STATS_PORT + '/');
});
