#!/bin/bash
# Cron wrapper: 0 9 * * * /root/sheets-to-telegram/run.sh
cd /root/sheets-to-telegram
exec venv/bin/python3 main.py >> /var/log/sheets-telegram.log 2>&1
