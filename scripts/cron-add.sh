#!/bin/bash
# Usage: cron-add.sh "0 9 * * *" "/root/scripts/my-script.sh" "description"
# Adds a cron job and logs it
SCHEDULE="${1:?Need schedule}"
CMD="${2:?Need command}"
DESC="${3:-no description}"

# Check if already exists
if crontab -l 2>/dev/null | grep -qF "$CMD"; then
    echo "Already exists: $CMD"
    exit 0
fi

# Add cron
(crontab -l 2>/dev/null; echo "$SCHEDULE $CMD  # $DESC") | crontab -
echo "Added cron: [$SCHEDULE] $CMD — $DESC"

# Save to memory
python3 /root/scripts/memory.py save "cron/$(echo $CMD | md5sum | cut -c1-8)" \
    "schedule=$SCHEDULE cmd=$CMD desc=$DESC" --tags "cron" 2>/dev/null || true
