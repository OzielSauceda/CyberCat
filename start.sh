#!/usr/bin/env bash
set -e

COMPOSE_FILE="infra/compose/docker-compose.yml"
ENV_FILE="infra/compose/.env"
ENV_EXAMPLE="infra/compose/.env.example"
DOCKER_DESKTOP="/c/Program Files/Docker/Docker/Docker Desktop.exe"

# ----------------------------------------------------------------------------
# Parse args. Supported flags:
#   --profile <name>    (repeatable; e.g. --profile agent --profile wazuh)
#   --profile=<name>
# Anything else is forwarded to the eventual `docker compose up`.
# ----------------------------------------------------------------------------
PROFILES=()
while [ $# -gt 0 ]; do
  case "$1" in
    --profile)
      shift
      if [ $# -gt 0 ]; then
        PROFILES+=("$1")
        shift
      fi
      ;;
    --profile=*)
      PROFILES+=("${1#--profile=}")
      shift
      ;;
    *)
      shift
      ;;
  esac
done

# Default profile (Phase 16.6): if no --profile was given, run with `agent`.
# That brings up the custom telemetry agent and lab-debian. Wazuh is now
# opt-in via `--profile wazuh`. See docs/decisions/ADR-0011-direct-agent-telemetry.md.
WAZUH_BANNER=1
if [ ${#PROFILES[@]} -eq 0 ]; then
  PROFILES=("agent")
  WAZUH_BANNER=1
fi

# Suppress the Wazuh banner only when wazuh is one of the active profiles.
for p in "${PROFILES[@]}"; do
  if [ "$p" = "wazuh" ]; then
    WAZUH_BANNER=0
  fi
done

if [ "$WAZUH_BANNER" = "1" ]; then
  echo "Telemetry: cct-agent (custom). Wazuh is opt-in — pass --profile wazuh to enable it."
fi

PROFILE_FLAGS=()
for p in "${PROFILES[@]}"; do
  PROFILE_FLAGS+=(--profile "$p")
done

agent_profile_active() {
  for p in "${PROFILES[@]}"; do
    if [ "$p" = "agent" ]; then return 0; fi
  done
  return 1
}

caldera_profile_active() {
  for p in "${PROFILES[@]}"; do
    if [ "$p" = "caldera" ]; then return 0; fi
  done
  return 1
}

# ----------------------------------------------------------------------------
# Docker Desktop bringup (Windows convenience)
# ----------------------------------------------------------------------------
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

# ----------------------------------------------------------------------------
# Bring up the stack
# ----------------------------------------------------------------------------
echo "Bringing up CyberCat stack..."
docker compose -f "$COMPOSE_FILE" "${PROFILE_FLAGS[@]}" up -d

# ----------------------------------------------------------------------------
# First-run cct-agent token bootstrap (only if --profile agent is active)
# ----------------------------------------------------------------------------
if agent_profile_active; then
  current_token=""
  if [ -f "$ENV_FILE" ]; then
    current_token=$(grep "^CCT_AGENT_TOKEN=" "$ENV_FILE" 2>/dev/null | head -1 | sed 's/^CCT_AGENT_TOKEN=//')
  fi

  if [ -z "$current_token" ]; then
    echo
    echo "First-run: provisioning cct-agent API token..."

    # Wait for backend /healthz
    for i in {1..40}; do
      if docker compose -f "$COMPOSE_FILE" exec -T backend curl -sf http://localhost:8000/healthz >/dev/null 2>&1; then
        break
      fi
      sleep 2
    done

    # Ensure cct-agent@local user exists (idempotent — ignore "already exists" failure)
    set +e
    docker compose -f "$COMPOSE_FILE" exec -T backend python -m app.cli create-user \
      --email cct-agent@local \
      --password "$(openssl rand -hex 24 2>/dev/null || head -c 48 /dev/urandom | base64 | head -c 32)" \
      --role analyst >/dev/null 2>&1
    set -e

    # Issue a token
    issue_output=$(docker compose -f "$COMPOSE_FILE" exec -T backend python -m app.cli issue-token \
      --email cct-agent@local --name cct-agent 2>&1) || {
      echo "ERROR: failed to issue cct-agent token:"
      echo "$issue_output"
      exit 1
    }

    # Parse the "  token: <plaintext>" line.
    token=$(echo "$issue_output" | sed -nE 's/^[[:space:]]+token:[[:space:]]+(.+)$/\1/p' | head -1 | tr -d '\r')
    if [ -z "$token" ]; then
      echo "ERROR: could not parse issued token from CLI output:"
      echo "$issue_output"
      exit 1
    fi

    # Ensure .env exists, then upsert CCT_AGENT_TOKEN
    if [ ! -f "$ENV_FILE" ]; then
      if [ -f "$ENV_EXAMPLE" ]; then
        cp "$ENV_EXAMPLE" "$ENV_FILE"
      else
        : > "$ENV_FILE"
      fi
    fi
    if grep -q "^CCT_AGENT_TOKEN=" "$ENV_FILE" 2>/dev/null; then
      sed -i.bak "s|^CCT_AGENT_TOKEN=.*|CCT_AGENT_TOKEN=$token|" "$ENV_FILE"
      rm -f "${ENV_FILE}.bak"
    else
      echo "CCT_AGENT_TOKEN=$token" >> "$ENV_FILE"
    fi

    echo "✓ Token written to $ENV_FILE"
    echo "  Recreating cct-agent with the new token..."
    docker compose -f "$COMPOSE_FILE" "${PROFILE_FLAGS[@]}" up -d --force-recreate cct-agent
  fi
fi

# ----------------------------------------------------------------------------
# First-run Caldera API key bootstrap (only if --profile caldera is active)
# ----------------------------------------------------------------------------
if caldera_profile_active; then
  current_key=""
  if [ -f "$ENV_FILE" ]; then
    current_key=$(grep "^CALDERA_API_KEY=" "$ENV_FILE" 2>/dev/null | head -1 | sed 's/^CALDERA_API_KEY=//' | tr -d '\r')
  fi
  if [ -z "$current_key" ] || [ "$current_key" = "CYBERCAT_DEV_KEY_DO_NOT_SHIP" ]; then
    echo
    echo "First-run: generating CALDERA_API_KEY..."
    new_key=$(openssl rand -hex 16 2>/dev/null || head -c 32 /dev/urandom | base64 | head -c 32)
    if [ ! -f "$ENV_FILE" ]; then
      if [ -f "$ENV_EXAMPLE" ]; then
        cp "$ENV_EXAMPLE" "$ENV_FILE"
      else
        : > "$ENV_FILE"
      fi
    fi
    if grep -q "^CALDERA_API_KEY=" "$ENV_FILE" 2>/dev/null; then
      sed -i.bak "s|^CALDERA_API_KEY=.*|CALDERA_API_KEY=$new_key|" "$ENV_FILE"
      rm -f "${ENV_FILE}.bak"
    else
      echo "CALDERA_API_KEY=$new_key" >> "$ENV_FILE"
    fi
    echo "✓ CALDERA_API_KEY written to $ENV_FILE"
    echo "  Recreating caldera with the new key..."
    docker compose -f "$COMPOSE_FILE" "${PROFILE_FLAGS[@]}" up -d --force-recreate caldera
  fi
fi

echo
docker compose -f "$COMPOSE_FILE" "${PROFILE_FLAGS[@]}" ps

echo
echo "UI:        http://localhost:3000/incidents"
echo "API docs:  http://localhost:8000/docs"
echo "Health:    http://localhost:8000/healthz"
