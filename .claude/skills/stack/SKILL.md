---
name: stack
description: Show CyberCat stack status — container health, exposed ports, and recent backend logs. Use when the user asks if the stack is running, checks health, or wants to see what's up.
---

Run the following and report the results clearly:

1. `docker compose -f infra/compose/docker-compose.yml ps` — show all container names, status, and ports.
2. `docker compose -f infra/compose/docker-compose.yml logs backend --tail 20` — show the last 20 backend log lines.
3. Tell the user the access URLs:
   - UI: http://localhost:3000/incidents
   - API docs: http://localhost:8000/docs
   - Health: http://localhost:8000/healthz

Keep the output concise. Flag any container that is not in a healthy/running state.
