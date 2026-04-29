export interface GlossaryEntry {
  title: string
  short: string
  long: string
}

export const GLOSSARY = {
  incident: {
    title: "Incident",
    short: "A grouped story of correlated signals pointing to a single threat.",
    long: "An incident is the core unit of work in CyberCat. When multiple detection signals share a common entity (user, host, IP) within a correlation window, the correlator groups them into one incident with a title, severity, and rationale. Each incident retains every event and rule that contributed so analysts can trace the full chain of evidence.",
  },
  detection: {
    title: "Detection",
    short: "A single rule match against an incoming event.",
    long: "A detection is created when a Sigma rule or custom Python detector matches a normalized event. It carries a severity hint, confidence hint, and ATT&CK tags. Detections feed into the correlator, which decides whether they belong to an existing incident or warrant a new one.",
  },
  event: {
    title: "Event",
    short: "A single normalized telemetry record from the agent or Wazuh.",
    long: "Events are the raw inputs to CyberCat. They arrive from the built-in cct-agent (SSH/auditd/conntrack) or from Wazuh, and are normalized into a canonical internal shape (kind, source, entities, timestamps). All downstream work — detections, incidents, entity graphs — is derived from events.",
  },
  "event-kind": {
    title: "Event Kind",
    short: "The semantic type of a telemetry record (e.g. auth.failed, process.created).",
    long: "Each event carries a kind string that describes what happened: auth.failed, auth.succeeded, session.started, session.ended, process.created, network.connection. The kind drives which detection rules apply and how the event is displayed in the timeline.",
  },
  severity: {
    title: "Severity",
    short: "How dangerous this incident or detection is: info → low → medium → high → critical.",
    long: "Severity is assigned by the correlator based on the highest-severity detection signal involved and any policy overrides. It is a five-level scale: info, low, medium, high, critical. Analysts can escalate severity via a response action.",
  },
  confidence: {
    title: "Confidence",
    short: "0–100 score of how certain CyberCat is this is a real threat.",
    long: "Confidence is a 0–100 score synthesized from the detection rules' own confidence hints, the number of corroborating signals, and the correlator's assessment of entity overlap. A high confidence score means multiple independent signals point to the same threat actor and chain of events.",
  },
  correlator: {
    title: "Correlator",
    short: "The engine that groups detection signals into a single incident.",
    long: "The correlator is CyberCat's core logic layer. It runs on every incoming detection and asks: does this belong to an existing open incident (same entities, recent time window, overlapping ATT&CK chain)? If yes, it enriches the incident. If no, it opens a new one. Each incident records which correlator rule and version created it.",
  },
  entity: {
    title: "Entity",
    short: "A named actor or asset involved in an incident (user, host, IP, process, file).",
    long: "Entities are the people and machines that appear in events. CyberCat tracks users, hosts, IP addresses, processes, files, and generic observables. Each entity accumulates a history of events and incidents across time, making it possible to spot a user account that is implicated in multiple incidents.",
  },
  "entity-graph": {
    title: "Entity Graph",
    short: "A visual map of how entities co-occur across events in this incident.",
    long: "The entity graph shows which entities appeared together in the same events. A dense cluster (user ↔ host ↔ IP) suggests a coordinated chain of activity. The graph is rebuilt from the incident's event data on every load.",
  },
  "kill-chain": {
    title: "ATT&CK Kill Chain",
    short: "The ordered sequence of ATT&CK tactics covered by this incident's detections.",
    long: "MITRE ATT&CK organizes adversary behavior into tactics (the 'why') and techniques (the 'how'). The kill chain panel shows which tactics this incident has evidence for, ordered from initial access through to impact. More tactics covered = more of the attacker's playbook documented.",
  },
  tactic: {
    title: "Tactic",
    short: "A high-level adversary goal in the ATT&CK framework (e.g. Credential Access).",
    long: "ATT&CK tactics represent the adversary's objective at each stage of an attack: Initial Access, Execution, Persistence, Privilege Escalation, Defense Evasion, Credential Access, Discovery, Lateral Movement, Collection, Exfiltration, Impact. Each detection maps to one or more tactics.",
  },
  technique: {
    title: "Technique",
    short: "A specific method used to achieve an ATT&CK tactic (e.g. T1078 Valid Accounts).",
    long: "Techniques are the specific methods adversaries use. They are identified by codes like T1078 (Valid Accounts) or T1059 (Command and Scripting Interpreter). Techniques are children of tactics and may have subtechniques (e.g. T1078.002 Domain Accounts).",
  },
  subtechnique: {
    title: "Sub-technique",
    short: "A more specific variant of an ATT&CK technique (e.g. T1078.004 Cloud Accounts).",
    long: "Sub-techniques narrow down a technique to a specific method or platform. For example, T1078 Valid Accounts has sub-techniques for Default Accounts (T1078.001), Domain Accounts (T1078.002), Local Accounts (T1078.003), and Cloud Accounts (T1078.004).",
  },
  action: {
    title: "Response Action",
    short: "A guarded, audited step an analyst can take in response to an incident.",
    long: "Response actions are the analyst's toolkit: tag an incident, elevate severity, flag a host, quarantine a host in the lab, kill a process, block an observable, or request evidence. Every action is classified by risk level, logged with who ran it and when, and can be reverted if reversible.",
  },
  "auto-safe": {
    title: "Auto-safe",
    short: "An action safe to execute automatically without analyst approval.",
    long: "Auto-safe actions carry no meaningful risk of disruption. CyberCat may execute them automatically as part of a response policy, or an analyst can trigger them without a second confirmation step. Example: tagging an incident or adding a note.",
  },
  "suggest-only": {
    title: "Suggest-only",
    short: "An action CyberCat recommends but will not execute without analyst approval.",
    long: "Suggest-only actions are surfaced in the recommended actions panel but gated behind explicit analyst confirmation. They are safe enough to suggest automatically but consequential enough to require a human decision before execution.",
  },
  reversible: {
    title: "Reversible",
    short: "An action that can be undone — CyberCat stores the reversal information.",
    long: "Reversible actions record enough state to undo themselves. For example, blocking an observable stores the block rule ID so the block can be lifted. The Actions panel shows a Revert button for executed reversible actions.",
  },
  disruptive: {
    title: "Disruptive",
    short: "An action with significant side effects that cannot be automatically undone.",
    long: "Disruptive actions may terminate processes, sever sessions, or modify host state in ways that affect production workloads. They require explicit analyst confirmation and are flagged prominently in the UI. Examples: kill process, quarantine host.",
  },
  source: {
    title: "Event Source",
    short: "Where the event came from: the built-in agent, Wazuh, or the seeder.",
    long: "CyberCat accepts telemetry from three sources: 'direct' (the cct-agent tailing sshd/auditd/conntrack logs), 'wazuh' (the Wazuh indexer bridge, opt-in), and 'seeder' (the built-in demo scenario runner). All sources normalize into the same internal event shape so downstream correlation is source-agnostic.",
  },
  agent: {
    title: "CCT Agent",
    short: "CyberCat's built-in telemetry agent — tails sshd, auditd, and conntrack.",
    long: "The cct-agent is a Python daemon that runs inside the stack and tails three log/proc sources: sshd logs (auth events), auditd logs (process events), and /proc/net/nf_conntrack (network connection events). It normalizes each into canonical CyberCat events and posts them to the backend. It is the default telemetry source; Wazuh is opt-in.",
  },
  wazuh: {
    title: "Wazuh",
    short: "An optional upstream telemetry source — a third-party security platform.",
    long: "Wazuh is an open-source security platform that CyberCat can pull events from via its indexer API. It is opt-in (start with --profile wazuh) and provides richer OS-level telemetry than the built-in agent. Wazuh is also the only path to real OS-level Active Response (iptables, kill -9 on the lab host).",
  },
  sigma: {
    title: "Sigma Rule",
    short: "A portable, vendor-neutral detection rule format used to match events.",
    long: "Sigma is an open standard for writing detection rules in YAML. CyberCat ships a set of built-in Sigma rules (SSH brute force, privilege escalation, lateral movement, etc.) and evaluates them against every normalized event. A Sigma match produces a Detection record.",
  },
  observable: {
    title: "Observable",
    short: "A specific indicator of compromise — IP, domain, file hash, or path.",
    long: "Observables are concrete artifacts associated with a threat: IP addresses, domain names, file hashes, and file paths. CyberCat can block observables (preventing them from being seen again without an alert) and tracks which incidents they appeared in.",
  },
  "blocked-observable": {
    title: "Blocked Observable",
    short: "An observable that has been marked for active blocking or monitoring.",
    long: "When an analyst or response policy blocks an observable, CyberCat records it in the blocked_observables table and (on the agent path) flags future matching events immediately. The block can be listed, filtered by active status, and lifted.",
  },
  "evidence-request": {
    title: "Evidence Request",
    short: "A formal request to collect a forensic artifact from a host.",
    long: "Evidence requests are structured asks for forensic data: a triage log, process list, network connection snapshot, or memory snapshot. They are attached to incidents and tracked through open → collected → dismissed lifecycle states. When collected, the payload URL points to the artifact.",
  },
  lab: {
    title: "Lab",
    short: "A controlled container environment where response actions are safely exercised.",
    long: "The lab is a lightweight Debian container (lab-debian) that acts as a safe sandbox. Response actions that would be dangerous on a real host (quarantine, kill process, block IP) are exercised against the lab container instead. Lab assets (hosts, users, IPs) are registered in the lab registry and are the valid targets for lab-scoped actions.",
  },
  session: {
    title: "Session",
    short: "An authenticated login session tracked across auth and session events.",
    long: "A session is an SSH or equivalent login tracked by CyberCat from session.started through session.ended. Sessions tie together the user, source IP, host, and session ID, making it possible to correlate a brute-force auth.failed chain with the eventual session.started that succeeded.",
  },
  timeline: {
    title: "Event Timeline",
    short: "Chronological list of events that make up this incident.",
    long: "The timeline shows every event that contributed to the incident, sorted by time. Events are color-coded by source layer: identity events (auth, session), endpoint events (process), and network events (connection). Each event can be expanded to show its full normalized payload.",
  },
  status: {
    title: "Incident Status",
    short: "Where the incident is in its lifecycle: new → triaged → investigating → contained → resolved → closed.",
    long: "Incidents move through a defined lifecycle. 'new' means just created by the correlator. 'triaged' means an analyst has reviewed it. 'investigating' means active work is underway. 'contained' means the threat has been isolated. 'resolved' means the root cause is addressed. 'closed' means no further action needed. Incidents can be 'reopened' if new signals arrive.",
  },
  "incident-kind": {
    title: "Incident Kind",
    short: "What kind of compromise pattern this case represents.",
    long: "CyberCat groups incidents into a few high-level kinds based on which signals were involved: suspicious sign-in activity (identity_compromise), suspicious activity on a machine (endpoint_compromise), a compromised account that's now acting on a machine (identity_endpoint_chain), and unclassified. The kind drives which response actions are recommended.",
  },
  "evidence-kind": {
    title: "Evidence Kind",
    short: "The type of forensic artifact requested from a host.",
    long: "Evidence requests come in a few flavors: a triage log (a quick health snapshot), a process list (every running program at the time), open network connections, and a memory snapshot (the heaviest, most invasive option). Choose the lightest evidence kind that answers the question.",
  },
  "role-in-incident": {
    title: "Role in incident",
    short: "How this event fits into the case: trigger, supporting, or background.",
    long: "Each event linked to an incident has a role. The trigger is the event that opened the case. Supporting events help confirm or build on the trigger. Background events are surrounding activity included for context. The timeline is colored by role so you can see the trigger at a glance.",
  },
  "observable-kind": {
    title: "Observable kind",
    short: "What kind of artifact an observable is: IP, domain, file hash, or path.",
    long: "Observables are concrete artifacts associated with a threat. CyberCat tracks four kinds: IP addresses, domain names, file hashes, and file paths. The kind determines how the observable is matched against future events and what blocking it means in practice.",
  },
} satisfies Record<string, GlossaryEntry>

export type GlossarySlug = keyof typeof GLOSSARY
