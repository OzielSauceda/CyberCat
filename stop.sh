#!/usr/bin/env bash
set -e

COMPOSE_FILE="infra/compose/docker-compose.yml"

if ! docker info >/dev/null 2>&1; then
  echo "Docker engine not reachable — nothing to stop."
  exit 0
fi

echo "Stopping CyberCat stack..."
docker compose -f "$COMPOSE_FILE" down

echo
echo "Stack stopped. Docker Desktop is still running so containers come back fast on next ./start.sh."
echo "To free WSL memory entirely, exit Claude Code (SessionEnd hook handles cleanup) or quit Docker Desktop from the tray."
