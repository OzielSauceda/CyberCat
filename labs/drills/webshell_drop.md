# Drill — `webshell_drop`

## Briefing

An attacker uploads a PHP web shell to a public-facing web server
(`host-web.lab.local`), then uses the shell to run reconnaissance commands
(`id`, `cat /etc/passwd`) and download a follow-up payload via wget — all
spawned by the apache2 process.

Like cryptojacking (A2), this drill **produces no incident in current
platform state**. The recurring Linux process-chain gap means
`apache2 → sh → child` chains slip past `process_suspicious_child`
(Windows-only branches). Plus, no detector watches inbound HTTP or .php
file-creation in a web root — both are Phase 22+ candidates.

This is a gap-review drill focused on understanding **why webshells are
specifically nasty**: persistence + low signal + reuse of normal web
server primitives.

## Run

```bash
bash labs/drills/run.sh webshell_drop --speed 0.1
```

## Decision points

1. **Find the upload event.** Open the events table; look for
   `file.created` with `path=/var/www/html/upload.php` and `user=www-data`.
   - *Expected:* you can spot the file-creation event and reason about why
     a `.php` file owned by `www-data` in a web root is a strong signal in
     the real world.

2. **Identify the apache2 child processes.** Look for the three
   `process.created` events with `parent_image=/usr/sbin/apache2`:
   `id`, `cat /etc/passwd`, `wget`.
   - *Expected:* you understand that the process *parent* (apache2) is
     the most important piece of evidence here — apache2 spawning shell
     children is the canonical webshell signature.

3. **Reason about how a Phase 22 detector would catch this.** A LotL
   detector would key on `(parent_image=apache2, child_image in {sh, bash,
   id, cat, wget, curl, python})` AND `(user=www-data)`. Different from
   `process_suspicious_child` because the trigger is the parent, not the
   child binary name.
   - *Expected:* you can describe the Phase 22 detector design at one
     paragraph of detail.

4. **(Optional) Block the attacker IP.** The inbound HTTP came from
   `203.0.113.42`. If you wanted to disrupt the attacker, you could
   manually add it to `blocked_observables`. (Same constraint as A2 —
   no admin API; would need to propose+execute a `block_observable`
   action against a synthetic incident.)
   - *Expected:* you understand the operator-tooling gap that makes ad-hoc
     blocking tedious without a synthetic incident.

## Expected outcome

- Incident kind: none formed (current platform state — recorded gap).
- Drill outcome: you can describe the Phase 22 webshell detector at code-
  paragraph detail.

## What this teaches

- **Webshells use the web server's own process tree.** No external malware
  binary; the attacker's "tool" is whatever shell + utilities the OS ships
  with. Detection has to live above the binary level.
- **Parent-process is the highest-signal field.** `apache2 → sh` is rare
  enough in healthy operation to be a near-zero-false-positive trigger.
- Practice: reading process trees, recognizing process-parent signals,
  reasoning about volumetric vs categorical detector designs.
