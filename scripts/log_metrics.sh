#!/bin/bash

LOG_DIR="/root/data"
METRICS_SCRIPT="/root/scripts/monitor.sh"

# Створення директорії для логів, якщо вона не існує
mkdir -p "$LOG_DIR"

# Виконання скрипта моніторингу та збереження результату у лог-файл
"$METRICS_SCRIPT" >> "$LOG_DIR/server_metrics_$(date +%Y%m%d_%H%M%S).log"