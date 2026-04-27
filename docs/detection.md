# Detection Engineering — CyberCat

## Overview

CyberCat has two parallel detection sources that co-exist under the same registration API:

| Source | `rule_source` | Location | When to use |
|---|---|---|---|
| Python rules | `py` | `backend/app/detection/rules/*.py` | Complex logic, stateful queries, multi-event aggregation |
| Sigma rules | `sigma` | `backend/app/detection/sigma_pack/*.yml` | Portable, auditable, Sigma-community-compatible predicates |

Both produce `DetectionResult` objects and register via the same `@register()` decorator. Detection persistence, correlation, and the analyst UI are entirely unaware of the source — `rule_source` is just an enum column.

### Current Python detectors (as of Phase 12)

| Rule ID | Fires on | Uses Redis | Notes |
|---|---|---|---|
| `py.auth.failed_burst` | `auth.failed` | Yes — sliding window | ≥4 failures for same user in 60s |
| `py.auth.anomalous_source_success` | `auth.succeeded` | Yes — seen-sources set per user | Successful auth from a source that has only produced failures in the recent past |
| `py.process.suspicious_child` | `process.created` | No | Encoded PowerShell, office-spawns-shell, rundll32+script heuristic |
| `py.blocked_observable_match` | any event carrying an observable | Yes — 30s cache of `blocked_observables` table | **Closes the response → detection feedback loop** — firing an action that adds to `blocked_observables` makes future events carrying that IP/domain/hash land as new detections on the same incident |

### Input telemetry — the Wazuh decoder (Phase 9B)

The Wazuh decoder (`backend/app/ingest/wazuh_decoder.py`) currently normalizes **three event kinds** from **three OS sources**:

| Event kind | Linux source | Windows source |
|---|---|---|
| `auth.failed` / `auth.succeeded` | sshd (Wazuh rule 5700-series) | — |
| `process.created` | auditd EXECVE (`data.audit.*`) | Sysmon EventID 1 (`data.win.eventdata.*`) |

Non-matching alerts are dropped with a structured warning log. Adding a new source means extending the decoder's whitelist and adding a branch that emits the canonical normalized shape for the `kind` — the detection layer stays unchanged.

---

## The Sigma Pack

### Location

```
backend/app/detection/sigma_pack/
├── pack.yml            ← manifest of active rules
└── *.yml               ← curated SigmaHQ rules (attributed, never auto-synced)
```

### Manifest (`pack.yml`)

```yaml
rules:
  - proc_creation_win_powershell_encoded_cmd.yml
  - proc_creation_win_office_spawn_shell.yml
  # ...
```

Only rules listed in `pack.yml` are loaded. Files present but not listed are ignored (safe staging area). To disable a rule: remove it from `pack.yml`. To add one: add it to the directory and the manifest.

### Attribution policy

Every rule file must have a header comment crediting the original SigmaHQ authors and linking to the DRL license. Rules are committed verbatim from SigmaHQ; updates are cherry-picked individually — never bulk-imported. This keeps our version pinned and our history reviewable.

---

## The Sigma Compiler

CyberCat uses a **custom in-house Sigma evaluator** (~300 lines) rather than pySigma. pySigma targets backend query generation (Elasticsearch DSL, Splunk SPL, etc.) — we evaluate rules directly against our own `Event.normalized` Python dicts.

### Supported subset

**Field modifiers:**
- `|contains` — substring match (case-insensitive)
- `|startswith` — prefix match (case-insensitive)
- `|endswith` — suffix match (case-insensitive)
- `|re` — regex match (case-insensitive, via `re.search`)
- `|all` — when combined with a list value, ALL items in the list must match (default is ANY)

**Condition combinators:**
- `and`, `or`, `not` — boolean operators
- `1 of selection_*` — at least one of the selections matching the glob must match
- `all of selection_*` — all selections matching the glob must match
- `1 of them` / `all of them` — same but over all named selections

**Unsupported (raises `UnsupportedSigmaConstruct` at compile time):**
- `count()`, `max()`, `min()`, `timeframe:` (aggregation / time window rules)
- `|near` correlation rules
- `|base64offset`, `|cidr` modifiers (log a warning + skip)
- `keywords:` (list-only detection without field keys)

When a rule uses an unsupported construct, the loader logs a warning and skips it. The rule does not silently fail to match — it is excluded from the active set.

### Field mapping

Sigma uses Windows-style PascalCase field names. CyberCat normalizes events to lowercase snake_case. The mapping lives in `backend/app/detection/sigma/field_map.py`:

| Sigma field | Normalized key |
|---|---|
| `Image` | `image` |
| `CommandLine` | `cmdline` |
| `ParentImage` | `parent_image` |
| `User` | `user` |
| `SourceIp` / `SrcIp` | `source_ip` / `src_ip` |
| `DestinationIp` / `DstIp` | `dst_ip` |
| `DestinationPort` / `DstPort` | `dst_port` |
| `LogonType` | `auth_type` |
| `ComputerName` / `Workstation` | `host` |

**Any Sigma field not in this table causes the rule to be skipped at load time** with a logged warning. Add new fields to `field_map.py` when expanding the normalizer.

Logsource category mapping:

| Sigma `category` | Event `kind` |
|---|---|
| `process_creation` | `process.created` |
| `authentication` | `auth.succeeded`, `auth.failed` |
| `network_connection` | `network.connection` |
| `file_event` | `file.created` |

### Encoding

All Sigma rule files are read with `encoding="utf-8"`. This is explicit to avoid Windows default UTF-16 surprises.

---

## Sigma + Python co-fire is a feature

When `proc_creation_win_powershell_encoded_cmd.yml` (Sigma) and `py.process.suspicious_child` (Python) both match the same event, both fire and both `Detection` rows are persisted. Correlator dedup (per host, per hour bucket) ensures only one incident is opened — but the incident's detection panel shows both rows:

```
rule_source=sigma  sigma-proc-creation-win-powershell-encoded-cmd  high  T1059.001 T1027.010
rule_source=py     py.process.suspicious_child                      high  T1059.001 T1027.010
```

This is intentional: an analyst sees two independent engines converging on the same evidence — a stronger signal than either alone.

---

## Standalone endpoint correlator

The `endpoint_compromise_standalone` correlator opens a standalone `endpoint_compromise` incident when a process-related detection fires and no open `identity_compromise` incident exists for the same user in the last 30 minutes.

**Trigger predicate:** `detection.rule_id` starts with `py.process.`, `sigma-proc_creation_`, or `sigma-proc-creation-`.

**This prefix convention is normative.** If you add a new process-creation detector (Python or Sigma) and want it to trigger a standalone incident, follow the naming convention:
- Python: `py.process.<name>` (set `RULE_ID` in the rule file)
- Sigma: rule ID will be `sigma-proc_creation_<slug>` — ensure the filename starts with `proc_creation_`

**Severity stratification:**

| Correlator | Severity | Confidence | Meaning |
|---|---|---|---|
| `endpoint_compromise_join` (chain) | `high` | `0.80` | Endpoint activity follows identity compromise — strong signal |
| `endpoint_compromise_standalone` | `medium` | `0.60` | Endpoint signal with no identity corroboration — worth investigating |
| `identity_compromise` | `high` | `0.80` | Credential-guessing pattern — high confidence |

The stratification renders automatically in the UI — no special front-end logic required.

**Dedup:** Redis SETNX key `endpoint_compromise:{host}:{YYYYMMDDHH}`, TTL 2h. One standalone incident per host per hour bucket regardless of how many detections fire.

---

## Adding a new rule

### Python rule

1. Create `backend/app/detection/rules/your_rule.py`
2. Set `RULE_ID = "py.<category>.<name>"` (follow existing conventions)
3. Register via `@register` from `app.detection.engine`
4. Import in `backend/app/detection/__init__.py`
5. If the rule covers process creation and should open standalone incidents, name it `py.process.*`

### Sigma rule

1. Locate or write a Sigma YAML rule matching the supported subset (see above)
2. Prepend the SigmaHQ attribution header
3. Place the file in `backend/app/detection/sigma_pack/`
4. Add the filename to `pack.yml`'s `rules:` list
5. Test with `pytest backend/tests/unit/test_sigma_compiler.py`

No server restart required during development — the pack is loaded at application startup. Rebuild the container image to deploy rule changes.

---

## Running tests

```bash
# Unit tests (no infrastructure needed)
pytest backend/tests/unit/

# Integration tests (requires docker compose up -d)
pytest backend/tests/integration/

# Full smoke test (requires running stack)
bash labs/smoke_test_phase7.sh
```
