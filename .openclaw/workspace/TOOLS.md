# TOOLS.md — Інфраструктура сервера

## Сервер
- Host: 68.183.66.2 (Ubuntu 24.04, 1vCPU 2GB)
- Node: v22.22.1, PM2 global, Python 3.12

## PM2 процеси
| Назва | Порт | Опис |
|-------|------|------|
| openclaw | 18789 | OpenClaw gateway |
| smart-router | 9000/9001 | LLM router + stats |
| watchdog | — | моніторинг |

## Корисні команди
```bash
pm2 status
pm2 logs openclaw --lines 30 --nostream
curl http://127.0.0.1:9000/health
```

## GitHub
- User: MaxSaiets
- Token: GH_TOKEN в env

## Env vars
```
GH_TOKEN=...
GITHUB_USER=MaxSaiets
TELEGRAM_BOT_TOKEN=8697...
TELEGRAM_CHAT_ID=1311004971
```
