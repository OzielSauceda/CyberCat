# Demo GIF recording playbook

Operator-run playbook that produces `docs/assets/demo.gif` — the hero GIF at the top of `README.md`. Follow this script once; it takes ~15 minutes end-to-end.

---

## Target

- **File:** `docs/assets/demo.gif`
- **Size:** ≤ 10 MB (ideally 4–7 MB — GitHub inline renders anything over ~10 MB slowly)
- **Resolution:** 1280 × 720 (or 1120 × 700 if your browser chrome eats more pixels)
- **Framerate:** 10–12 fps
- **Duration:** 45–60 seconds
- **Loop:** forever

## Tooling

**Primary:** [ScreenToGif](https://www.screentogif.com/) — free, open-source, Windows-native. Records directly to GIF with a frame-level editor so you can trim dead space.

**Fallback (if ScreenToGif output > 10 MB):** [ShareX](https://getsharex.com/) records to MP4, then convert with ffmpeg's palette pipeline:

```bash
ffmpeg -i demo.mp4 \
  -vf "fps=10,scale=1280:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=256[p];[b][p]paletteuse" \
  -loop 0 \
  docs/assets/demo.gif
```

## Pre-flight — clean state

The incidents list must start empty so the viewer sees the empty → populated transition. Do all of this **before** starting the recorder.

### 1. Start the core stack

```bash
cd infra/compose
docker compose up -d
curl http://localhost:8000/healthz     # wait for "ok"
```

### 2. Confirm flags

In `infra/compose/.env`:

```
WAZUH_AR_ENABLED=false
WAZUH_BRIDGE_ENABLED=false
```

Both default to `false`. The `WazuhBridgeBadge` in the top nav will render gray "Bridge off" — correct for this self-contained demo.

### 3. Wipe the DB + Redis

The safest reset is a full volume wipe (re-runs all migrations, re-seeds lab assets):

```bash
cd infra/compose
docker compose down -v
docker compose up -d
curl http://localhost:8000/healthz     # wait for "ok" again (takes ~15s)
```

Alternative (keeps volumes, faster, truncates in-place):

```bash
docker compose exec postgres psql -U cybercat -d cybercat -c \
  "TRUNCATE TABLE notes, incident_transitions, action_logs, actions, \
   incident_attack, incident_entities, incident_events, incident_detections, \
   incidents, detections, event_entities, events, entities, \
   evidence_requests, blocked_observables, lab_sessions, lab_assets CASCADE;"
docker compose exec redis redis-cli FLUSHDB
```

### 4. Open the UI

Chrome / Edge → <http://localhost:3000/incidents>. Confirm:
- Empty-state panel visible ("No incidents yet" or similar)
- Top-right badge reads "Bridge off" (gray pill)
- Window width close to **1280 px** (drag to fit; exact pixel match matters less than framing)

Hide bookmark bars, notification toasts, OS clock overlays. Close Slack / email / anything that could pop a notification mid-take.

### 5. Pre-warm the simulator

Open a second terminal at the repo root:

```bash
cd C:/Users/oziel/OneDrive/Desktop/CyberCat
pip install httpx                      # one-time; uses your local Python
# DO NOT RUN THE SIMULATOR YET. Just have the command ready in history:
python -m labs.simulator --scenario credential_theft_chain --speed 0.1 --verify
```

Having the command already typed means you can fire it within a second of hitting record.

---

## Recording narrative (target: 50 seconds)

Approach: **browser only in frame.** Alt-tab to fire the simulator instead of including the terminal — it keeps the frame clean and lets you trim the alt-tab frames out in post.

| t | Scene | What's on screen | Action |
|---|---|---|---|
| 0:00–0:04 | Empty list | `/incidents` with empty state, "Bridge off" gray pill | Hold still. Let the viewer read. |
| 0:04–0:06 | Alt-tab, fire simulator | (Trim these frames in post) | In the second terminal: ↑ Enter |
| 0:06–0:08 | Alt-tab back to browser | `/incidents` still empty | Hold. |
| 0:08–0:14 | Incidents appear | Two cards slide in: `identity_compromise` (high) and `identity_endpoint_chain` (critical) | UI polls at 10s — if impatient, F5 once |
| 0:14–0:18 | Click `identity_endpoint_chain` | Navigates to `/incidents/{id}` | Single click |
| 0:18–0:22 | Header + rationale | Severity pill, status pill, confidence bar, rationale box | Pause. Let viewer read rationale. |
| 0:22–0:30 | Scroll to ATT&CK kill chain | 14-tactic strip, Credential Access + Execution highlighted indigo/lime | Slow scroll |
| 0:30–0:38 | Graphical timeline | 5 color-coded dots on baseline, 2 detection triangles with dashed connectors, hover one dot to show tooltip | Slow scroll, then hover |
| 0:38–0:45 | Entity graph (right column) | SVG graph: alice ↔ workstation-42 ↔ 203.0.113.42 | Hover a node, edge weight appears |
| 0:45–0:50 | Actions + Evidence Requests | Auto-proposed `tag_incident(cross-layer-chain)` and `request_evidence(triage_log)` | Hold the final frame 2 s |

**Cadence rule of thumb:** slow is better than jumpy for a GIF. A viewer scrolling past your hero reel will pause when something catches their eye — give them frames to pause on.

---

## Recording — ScreenToGif

1. Download from <https://www.screentogif.com/> → install → open **Recorder**.
2. Drag the capture region over the browser window. Target ~1280 × 720.
3. Frame rate: **12 fps**.
4. Hit **Record**. Follow the narrative table above in one take.
5. Hit **Stop**. The editor opens.
6. **Trim:** delete the alt-tab frames (0:04–0:08 in the table above) so the recorded duration reads ~46 s. Right-click → *Delete previous/selected/next frames*.
7. **Review:** scrub through. Any dead air > 500 ms that isn't intentional? Delete those frames.
8. **Save as GIF:**
   - Color depth: 256 (palette)
   - Quality: 85
   - Repeat forever: on
   - Output: `C:\Users\oziel\OneDrive\Desktop\CyberCat\docs\assets\demo.gif`
9. Check file size in Explorer. If **> 10 MB**, fall through to the ffmpeg pipeline below.

## Recording — ShareX + ffmpeg fallback

Use this if ScreenToGif's output is too large or too jittery.

1. ShareX → **Capture → Screen recording (GIF/MP4)** → configure: MP4, 15 fps, region select.
2. Record the same narrative above. Save the MP4 to `docs/assets/demo.mp4` (temp).
3. Convert with ffmpeg (install via `winget install Gyan.FFmpeg` if missing):
   ```bash
   cd docs/assets
   ffmpeg -i demo.mp4 \
     -vf "fps=10,scale=1280:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=256[p];[b][p]paletteuse" \
     -loop 0 \
     demo.gif
   ```
4. Delete the intermediate `demo.mp4` — it shouldn't be committed.

If the GIF is still > 10 MB, lower `fps=10` → `fps=8` and/or `scale=1280` → `scale=1024`. Don't drop the color palette below 256 — it looks awful on CyberCat's layer-color UI.

---

## Acceptance

- [ ] `docs/assets/demo.gif` exists
- [ ] File size ≤ 10 MB
- [ ] Plays 45–60 s, loops
- [ ] In-frame viewer can identify all five beats:
  1. Empty incidents list
  2. Two new incident cards appearing (high + critical)
  3. ATT&CK kill-chain panel
  4. Graphical timeline with detection triangles
  5. Entity graph or auto-proposed actions
- [ ] No secrets in frame (no `.env` file open, no password manager, no terminal with credentials)
- [ ] Renders inline when you preview `README.md` in VS Code

## Troubleshooting

**No incidents appear after simulator run.**
Check `docker compose logs backend --tail 50` for Python errors. Confirm the simulator's `--verify` block printed `PASSED`.

**Cards appear but neither is critical.**
The `identity_endpoint_chain` correlator is auto-elevated to `critical` by `auto_actions.py`. If you see `high`, the auto-action didn't run — check backend logs for a correlation error.

**The Bridge badge shows "Wazuh · live" instead of "Bridge off".**
Someone set `WAZUH_BRIDGE_ENABLED=true` in `.env`. Change it back and `docker compose restart backend`.

**GIF has a timestamp or mouse cursor artifact.**
ScreenToGif → Options → disable "Show cursor" and "Show clicks."

**File too large no matter what.**
Shorter narrative. Cut the Actions+Evidence beat down to 3 s, or skip the entity-graph hover.
