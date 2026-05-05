# Drill — `lateral_movement_chain`

## Briefing

An attacker brute-forces alice's SSH on `host-1.lab.local`, succeeds from a
hostile IP (`203.0.113.42`), then pivots `host-1 → host-2 → host-3` using
SSH and a `curl|sh` persistence step on host-2.

In current platform state, the platform **catches the identity-side activity**
(the brute force + the suspicious-IP login) and forms an `identity_compromise`
incident for alice. The cross-host SSH pivots **slip past detection** —
that's the recurring Linux-process-chain gap (Phase 22 input). So you'll get
a real incident to triage, but the evidence chain stops at host-1.

## Run

```bash
bash labs/drills/run.sh lateral_movement_chain --speed 0.1
```

## Decision points

1. **Identify the pivot identity.** Open the incident in the UI. Find alice
   in the entities panel. Note the source IP (`203.0.113.42`).
   - *Expected:* you understand the incident is about *alice* (not a host)
     and the trigger was a brute force followed by a suspicious-IP success.

2. **Transition to `triaged`.** Use the UI's status button (or `POST
   /v1/incidents/{id}/transitions` with `{"to_status": "triaged"}`).
   - *Expected:* the incident's status moves from `new` → `triaged`.

3. **Propose a containment action.** Block the attacker IP. UI: open the
   recommended-actions panel; the top recommendation should be
   `block_observable` on `203.0.113.42`. Propose it.
   - *Expected:* a `block_observable` action appears in the incident's
     actions list.

4. **(Optional) Execute the action.** Run the proposed `block_observable`.
   The IP gets added to `blocked_observables`; any future event referencing
   it will trip `py.blocked_observable_match`.
   - *Expected:* status of the action becomes `executed`.

## Expected outcome

- Incident kind: `identity_compromise` for alice
- Final status: `triaged` (or further if you progressed it)
- ≥1 `block_observable` action proposed and ideally executed

## What this teaches

- The **identity-side detector chain works on Linux today** — auth-related
  attacks get caught.
- The **Linux process chain doesn't** — the host-1 → host-2 → host-3 SSH
  pivots are visible in the events table but produce no `endpoint_compromise`
  incident. Phase 22 will add a Linux LotL detector to close this.
- Practice: triaging a real `identity_compromise`, proposing a containment
  action, observing the recommended-actions ranking.
