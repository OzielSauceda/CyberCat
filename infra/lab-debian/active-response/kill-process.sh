#!/bin/bash
# Wazuh Active Response: kill-process
# Wazuh 4.x passes arguments via stdin JSON under parameters.extra_args.
# Uses sed/cut to parse — no python3 required.

LOG=/var/ossec/logs/active-responses.log

log() {
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) kill-process: $*" >> "$LOG"
}

read -r AR_JSON

# Extract extra_args array from Wazuh AR JSON, e.g.:
# {"parameters":{"extra_args":["lab-debian","725","sleep"],...},...}
_ARGS=$(echo "$AR_JSON" | sed 's/.*"extra_args":\[//' | sed 's/\].*//')
HOST=$(echo "$_ARGS"        | cut -d',' -f1 | tr -d '"')
PID=$(echo "$_ARGS"         | cut -d',' -f2 | tr -d '"')
PROCESS_NAME=$(echo "$_ARGS" | cut -d',' -f3 | tr -d '"')

log "invoked host=$HOST pid=$PID process_name=$PROCESS_NAME"

if [ -z "$PID" ] || [ -z "$PROCESS_NAME" ]; then
    log "ERROR: missing pid or process_name argument"
    log "  AR_JSON was: $AR_JSON"
    exit 1
fi

CMDLINE_FILE="/proc/${PID}/cmdline"
if [ ! -f "$CMDLINE_FILE" ]; then
    log "pid=$PID does not exist or already gone — no-op"
    exit 0
fi

CMDLINE=$(tr '\0' ' ' < "$CMDLINE_FILE" 2>/dev/null || true)
if echo "$CMDLINE" | grep -qF "$PROCESS_NAME"; then
    kill -9 "$PID" 2>/dev/null
    EXIT_CODE=$?
    if [ $EXIT_CODE -eq 0 ]; then
        log "killed pid=$PID ($PROCESS_NAME)"
    else
        log "kill -9 pid=$PID returned $EXIT_CODE"
        exit $EXIT_CODE
    fi
else
    log "SAFETY: pid=$PID cmdline does not match process_name=$PROCESS_NAME — refusing kill"
    log "  cmdline was: $CMDLINE"
    exit 2
fi

exit 0
