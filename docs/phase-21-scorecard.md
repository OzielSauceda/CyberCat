# Phase 21 — Coverage Scorecard

_Generated 2026-05-06T04:56:29+00:00 from Caldera operation `326fde6c-fd74-434a-92b6-6275ab5e70e5`._

**Summary:** covered **0** / 17  ·  gaps 3  ·  false-negatives 0  ·  unexpected hits 0  ·  ability errors 14

Status enum: **covered** | **gap** | **false-negative** | **unexpected-hit** | **ability-failed** | **ability-skipped**. See `labs/caldera/README.md` for definitions.

| # | Ability | Technique | Caldera | Expected rule | Fired rules | Status |
|---|---|---|---|---|---|---|
| 1 | identify active user (id / whoami) | T1059.004 | 0 | `GAP` | — | **gap** |
| 2 | process listing (find user processes) | T1057 | 0 | `GAP` | — | **gap** |
| 3 | network connection enumeration | T1018 | 1 | `GAP` | — | **ability-failed** |
| 4 | /etc/passwd read (local) | T1003.008 | -3 | `GAP` | — | **ability-failed** |
| 5 | filesystem enumeration (find files) | T1083 | 0 | `GAP` | — | **gap** |
| 6 | SSH lateral pivot (sshd → bash → ssh) | T1021.004 | n/a | `GAP` | — | **ability-skipped** |
| 7 | curl | sh persistence | T1105 | n/a | `GAP` | — | **ability-skipped** |
| 8 | SUDO brute-force | T1110.001 | -3 | `py.auth.failed_burst` | — | **ability-failed** |
| 9 | clean cred-theft + AWS creds read + login from new IP | T1078 | n/a | `GAP` | — | **ability-skipped** |
| 10 | file-burst rename (30× .encrypted in 60s) | T1486 | n/a | `GAP` | — | **ability-skipped** |
| 11 | useradd backdoor account | T1098 | n/a | `GAP` | — | **ability-skipped** |
| 12 | password change (passwd) | T1098 | 1 | `GAP` | — | **ability-failed** |
| 13 | cron persistence (/etc/cron.d/...) | T1546.003 | -3 | `GAP` | — | **ability-failed** |
| 14 | bash history wipe | T1070.003 | -3 | `GAP` | — | **ability-failed** |
| 15 | tarball stage (data compressed) | T1560.001 | -3 | `GAP` | — | **ability-failed** |
| 16 | scp exfil (push) | T1048.002 | 1 | `GAP` | — | **ability-failed** |
| 17 | systemd persistence (write .service file) | T1543.002 | -3 | `GAP` | — | **ability-failed** |

Phase 22 input: every row with status `gap` or `false-negative` is an ordered candidate. The Phase 22 plan will pick from this list by frequency, scenario coverage, and detector authoring complexity — not by the order they appear here.
