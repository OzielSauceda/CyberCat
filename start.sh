#!/usr/bin/env bash
set -e

COMPOSE_FILE="infra/compose/docker-compose.yml"
DOCKER_DESKTOP="/c/Program Files/Docker/Docker/Docker Desktop.exe"

if ! docker info >/dev/null 2>&1; then
  echo "Docker engine not reachable — launching Docker Desktop..."
  if [ -x "$DOCKER_DESKTOP" ]; then
    "$DOCKER_DESKTOP" &
  else
    echo "Could not find Docker Desktop at: $DOCKER_DESKTOP"
    echo "Start it manually, then re-run ./start.sh"
    exit 1
  fi

  printf "Waiting for Docker engine"
  for i in {1..60}; do
    if docker info >/dev/null 2>&1; then
      echo " — ready."
      break
    fi
    printf "."
    sleep 2
    if [ "$i" -eq 60 ]; then
      echo
      echo "Docker didn't come up in 2 minutes. Check Docker Desktop and try again."
      exit 1
    fi
  done
fi

echo "Bringing up CyberCat stack..."
docker compose -f "$COMPOSE_FILE" up -d

echo
docker compose -f "$COMPOSE_FILE" ps

echo
echo "UI:        http://localhost:3000/incidents"
echo "API docs:  http://localhost:8000/docs"
echo "Health:    http://localhost:8000/healthz"
