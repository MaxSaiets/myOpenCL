#!/bin/bash

# Збір метрик
CPU_IDLE=$(top -bn1 | grep 'Cpu(s)' | sed 's/.*, *\([0-9.]*\)%* id.*/\1/')
CPU_USAGE=$(echo "100 - $CPU_IDLE" | bc -l)

RAM_INFO=$(free -m | awk '/Mem:/ {print $3"/"$2}')
DISK_USAGE=$(df -h / | awk 'NR==2 {print $5}')
PROCESS_COUNT=$(ps aux | wc -l)

TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# Формування рядка логу
LOG_ENTRY="[$TIMESTAMP] CPU: ${CPU_USAGE}%, RAM: ${RAM_INFO} MB, Disk: ${DISK_USAGE}, Processes: ${PROCESS_COUNT}"

# Збереження в лог
echo "$LOG_ENTRY" >> /root/data/server_metrics_$(date +%Y%m%d).log
