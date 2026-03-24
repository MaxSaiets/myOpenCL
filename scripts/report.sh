#!/bin/bash

ANALYZE_SCRIPT="/root/scripts/analyze.py"

# Виконуємо скрипт аналізу та зберігаємо результат
RESULT=$(python3 $ANALYZE_SCRIPT)

# Виводимо результат для подальшої обробки
echo "$RESULT"