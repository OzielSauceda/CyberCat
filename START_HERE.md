# CyberCat — Session Startup Commands

Run these in order at the start of every dev session.

---

## 1. Start Docker Desktop

Open Docker Desktop from the Start menu and wait until it shows **"Engine running"** in the system tray before continuing.

---

## 2. Start the stack

```bash
cd infra/compose
docker compose up -d
```

> First time ever, or after pulling changes that touch `backend/` or `frontend/`:
> ```bash
> docker compose build
> docker compose up -d
> ```

---

## 3. Confirm everything is healthy

```bash
docker compose ps
```

All four services should show `running` or `healthy`:

| Service    | Expected state   |
|------------|-----------------|
| `postgres` | healthy          |
| `redis`    | healthy          |
| `backend`  | running          |
| `frontend` | running          |

Quick health check (optional):
```bash
curl http://localhost:8000/healthz
```

---

## 4. Open the app

| Surface           | URL                                  |
|-------------------|--------------------------------------|
| Analyst UI        | http://localhost:3000/incidents      |
| Backend API docs  | http://localhost:8000/docs           |
| Health endpoint   | http://localhost:8000/healthz        |

---

## 5. Seed a test incident (optional — for dev/demo)

Run from the repo root with Git Bash.

**Flagship demo — the attack simulator** (produces the full cross-layer incident chain, best for recording or showing off):

```bash
pip install httpx                                       # one-time, local Python
python -m labs.simulator --scenario credential_theft_chain --speed 0.1 --verify
```

~30 seconds later you'll see both an `identity_compromise` and an `identity_endpoint_chain` incident land in the UI. `--verify` asserts both were created and exits non-zero if not.

**Regression smoke tests** (use during development):

| Script | Checks | Purpose |
|---|---|---|
| `bash labs/smoke_test_phase3.sh` | 5 | Basic detection & correlation |
| `bash labs/smoke_test_phase6.sh` | 15 | Identity → endpoint chain |
| `bash labs/smoke_test_phase9a.sh` | 14 | Response handlers + blocked-observable feedback |
| `bash labs/smoke_test_phase10.sh` | 15 | Current master end-to-end with the simulator |
| `bash labs/smoke_test_phase11.sh` | 8 | Wazuh Active Response (requires `--profile wazuh` + `WAZUH_AR_ENABLED=true`) |

---

## 6. Stop the stack when done

```bash
# from infra/compose/
docker compose down
```

To also wipe the database (destroys all incident data):
```bash
docker compose down -v
```

---

## Cheat sheet

| Task                             | Command (run from `infra/compose/`)               |
|----------------------------------|---------------------------------------------------|
| Start (images already built)     | `docker compose up -d`                            |
| Start + rebuild images           | `docker compose build && docker compose up -d`    |
| Check status                     | `docker compose ps`                               |
| View backend logs                | `docker compose logs -f backend`                  |
| View frontend logs               | `docker compose logs -f frontend`                 |
| Restart just the backend         | `docker compose restart backend`                  |
| Stop everything (keep data)      | `docker compose down`                             |
| Stop + wipe database             | `docker compose down -v`                          |
| Open Redis CLI                   | `docker compose exec redis redis-cli`             |
| Open Postgres shell              | `docker compose exec postgres psql -U cybercat -d cybercat` |
| Run flagship demo (simulator)    | `python -m labs.simulator --scenario credential_theft_chain --speed 0.1 --verify` (from repo root) |
| Run smoke test (full chain)      | `bash labs/smoke_test_phase6.sh` (from repo root) |

---

## If something looks broken

- **Backend won't start** — check `docker compose logs backend`. Most likely cause is Postgres not ready yet; wait 10s and `docker compose restart backend`.
- **Frontend shows blank page** — check `docker compose logs frontend`. If Tailwind or deps are missing, run `docker compose build frontend`.
- **No incidents appearing after smoke test** — check backend logs for Python errors. Confirm `detections_fired` and `incident_touched` appear in the curl output.
- **Port already in use** — another process is on 8000 or 3000. Run `docker compose down` first, or find and kill the conflicting process.
