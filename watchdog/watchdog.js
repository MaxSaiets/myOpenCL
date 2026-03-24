// OpenClaw Watchdog — monitors agent activity and notifies on stuck/errors
import fs from 'fs';
import https from 'https';

const BOT_TOKEN = '8697044933:AAEjLpqcCKIotwoLa69zdRYfaFyh44KY4tE';
const CHAT_ID   = '1311004971';
const ROUTER_URL = 'http://127.0.0.1:9000';

const STUCK_TIMEOUT_MS   = 4 * 60 * 1000;   // 4 min no progress = stuck
const CHECK_INTERVAL_MS  = 30 * 1000;        // check every 30s
const STATUS_INTERVAL_MS = 60 * 60 * 1000;  // send stats every 1 hour

let lastActivityMs = Date.now();
let lastLogSize    = 0;
let agentRunning   = false;
let lastRunStart   = 0;
let stuckNotified  = false;
let lastNotifyMs   = 0;
const NOTIFY_COOLDOWN = 5 * 60 * 1000;

function tgRequest(method, data) {
  return new Promise(resolve => {
    const body = JSON.stringify(data);
    const req = https.request({
      hostname: 'api.telegram.org',
      path: `/bot${BOT_TOKEN}/${method}`,
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) }
    }, res => {
      let d = '';
      res.on('data', c => d += c);
      res.on('end', () => { try { resolve(JSON.parse(d)); } catch { resolve({}); } });
    });
    req.on('error', resolve);
    req.write(body);
    req.end();
  });
}

function sendAlert(text, buttons) {
  const now = Date.now();
  if (now - lastNotifyMs < NOTIFY_COOLDOWN) return;
  lastNotifyMs = now;
  const payload = { chat_id: CHAT_ID, text, parse_mode: 'HTML' };
  if (buttons) payload.reply_markup = { inline_keyboard: buttons };
  tgRequest('sendMessage', payload).catch(() => {});
  console.log('[watchdog] alert sent:', text.slice(0, 60));
}

// Send stats via smart-router /send-stats (includes model usage with buttons)
function sendStats() {
  fetch(ROUTER_URL + '/send-stats', { method: 'POST' })
    .then(() => console.log('[watchdog] stats sent'))
    .catch(e => console.error('[watchdog] stats error:', e.message));
}

function getLogPath() {
  const d = new Date();
  const ymd = d.toISOString().slice(0, 10);
  return `/tmp/openclaw/openclaw-${ymd}.log`;
}

function checkActivity() {
  const logPath = getLogPath();
  try {
    const stat = fs.statSync(logPath);
    if (stat.size !== lastLogSize) {
      lastLogSize = stat.size;
      lastActivityMs = Date.now();
      stuckNotified = false;

      const content = fs.readFileSync(logPath, 'utf8');
      const recent = content.split('\n').filter(Boolean).slice(-20).join('\n');

      if (recent.includes('embedded_run_agent_start') || recent.includes('run_tool')) {
        if (!agentRunning) {
          agentRunning = true;
          lastRunStart = Date.now();
          console.log('[watchdog] agent run started');
        }
      }
      if (recent.includes('embedded_run_agent_end') || recent.includes('surface_error')) {
        const wasRunning = agentRunning;
        agentRunning = false;
        if (wasRunning && recent.includes('"isError":true')) {
          const errMatch = recent.match(/"error":"([^"]{0,120})"/);
          const errMsg = errMatch ? errMatch[1] : 'невідома помилка';
          const runSec = Math.floor((Date.now() - lastRunStart) / 1000);
          sendAlert(
            `⚠️ <b>Агент завершив із помилкою</b>\n\nЧас: ${runSec}с\nПомилка: <code>${errMsg}</code>`,
            [[{ text: '📊 Деталі', url: 'http://68.183.66.2:9001/' }]]
          );
        }
      }
    }
  } catch (e) {
    // Log not found yet — normal at startup
  }

  if (agentRunning && !stuckNotified) {
    const silentMs = Date.now() - lastActivityMs;
    if (silentMs > STUCK_TIMEOUT_MS) {
      stuckNotified = true;
      const runSec = Math.floor((Date.now() - lastRunStart) / 1000);
      sendAlert(
        `🔴 <b>Агент завис!</b>\n\nПрацює вже <b>${runSec}с</b> без активності ${Math.round(silentMs/1000)}с.\n\nНадішли <code>стоп</code> щоб скасувати.`,
        [[{ text: '📊 Статус моделей', url: 'http://68.183.66.2:9001/' }]]
      );
    }
  }
}

const startTime = Date.now();
console.log('[watchdog] started | stuck_timeout=' + STUCK_TIMEOUT_MS/1000 + 's');

setInterval(checkActivity, CHECK_INTERVAL_MS);
setInterval(sendStats, STATUS_INTERVAL_MS);  // hourly stats
checkActivity();

// Send startup stats after 3s (let router fully initialize)
setTimeout(sendStats, 3000);
