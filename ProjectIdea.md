I want you to deeply understand the overall vision of this project before thinking about implementation details, coding steps, or feature sequencing. For this message, do not jump into building, do not start generating a task list yet, and do not immediately suggest file structures or implementation steps unless I ask for them later. Right now, I want you to absorb the project as a product idea, a systems idea, and an engineering direction.

This project is meant to become one of the strongest and most impressive projects on my resume. I want it to feel like a legitimate modern cybersecurity product, not a student toy, not a generic dashboard, not a simple log viewer, and not a thin wrapper around an existing security tool. The platform should feel like a focused but serious defensive security system built with real product thinking, real engineering logic, and a clear understanding of how modern security operations platforms actually provide value.

The core idea is this:

I want to build a threat-informed automated incident response platform focused on identity compromise and endpoint compromise. The product should feel like a focused mini XDR/SOAR-style system, but intentionally scoped so it is realistic for one strong builder working on a personal machine. This is not supposed to be a universal platform that solves every cybersecurity problem. It is supposed to be a serious, coherent, defensive product slice that feels modern, intelligent, and operationally meaningful.

This project is defensive only. It is meant only for systems I own, control, or explicitly use as a lab. It must not drift into hack-back behavior, offensive targeting, or anything designed for unauthorized environments. The platform should stay entirely centered on responsible detection, correlation, investigation, and controlled response in an owned or authorized environment.

The product is not meant to be passive. I do not want something that merely collects logs, displays alerts, summarizes events, or explains attacks. I want a system that behaves like an incident brain layered on top of security telemetry. It should take raw or near-raw security signals and turn them into structured, higher-level incident understanding. It should help answer questions like:
- Is this user showing signs of account takeover or risky identity behavior?
- Is this endpoint showing suspicious activity that suggests compromise, misuse, scripting abuse, persistence, or post-compromise behavior?
- Are several low-level events actually part of one meaningful incident chain?
- What entities are involved?
- How severe and how confident is the incident?
- What evidence supports the incident?
- What defensive actions should be taken next?
- Which actions are safe to automate and which should remain suggestions?
- How can an analyst quickly understand the story of what happened?

The central value of the platform is that it should connect telemetry, detections, incident formation, explainability, and response. I want it to move beyond raw alerts into:
- normalized entities
- correlated incidents
- timelines
- identity-to-endpoint relationships
- ATT&CK-aware context
- evidence and action history
- severity and confidence reasoning
- analyst-readable incident narratives
- controlled defensive response capability

The project should strongly emphasize that incidents are made of relationships, not just alerts. I want the system to recognize that suspicious identity signals and suspicious endpoint signals may be part of one attack chain. I want it to be capable of treating multiple weak or medium-confidence signals as one stronger structured incident when the context supports that. In other words, the system should feel like it understands that real security operations are not about staring at isolated alerts; they are about joining evidence into a meaningful incident story.

The specific scope is identity compromise plus endpoint compromise because that combination is both realistic and impressive. Identity is one of the most important modern security pressure points, and endpoint activity is where suspicious processes, scripting abuse, persistence behavior, and post-compromise actions often become visible. A product that connects those surfaces in one coherent model feels much more substantial than a tool that only watches one area.

I want the system to be capable of representing situations like:
- suspicious sign-in behavior tied to later suspicious host activity
- repeated authentication anomalies combined with unusual process execution
- suspicious user behavior and suspicious endpoint behavior being treated as one incident chain
- multiple signals that are individually weak but collectively convincing
- platform actions being informed by confidence, severity, context, and affected entities rather than by simple one-rule-one-alert thinking

Just as important, I want to be very clear about what this project is not. It should not become:
- a pure SIEM clone
- a pure EDR clone
- a pure threat intelligence portal
- a vulnerability scanner
- a malware sandbox
- a red-team framework
- a generic alert list
- a simple SOC simulation toy
- a glorified Wazuh dashboard
- a random collection of security scripts with a UI on top

The value is not in recreating entire enterprise product categories. The value is in building a serious, focused, threat-informed incident response platform that demonstrates understanding of how modern defensive systems actually turn telemetry into decisions and decisions into controlled action.

Architecturally, I want the platform to feel like a real product with clear conceptual boundaries. Even if the first implementations are compact, the system should conceptually separate:
- telemetry intake or upstream event acquisition
- normalization into internal event and entity models
- detection interpretation and signal handling
- correlation and incident formation
- incident or case state
- evidence and timeline history
- response policy and response execution
- analyst-facing product experience

A very important principle is that the custom application layer must be the star of the project. Supporting tools can exist, but they should not define the product. I do not want the finished result to feel like “I installed a security tool and added a few extra screens.” I want it to feel like I built a serious security platform on top of upstream telemetry sources and used those integrations to power my own product logic.

The finalized tech stack for this project is:
- Python
- FastAPI
- PostgreSQL
- Redis
- Wazuh
- Sigma
- Next.js
- TypeScript
- Podman or Docker Compose
- 1 to 2 lightweight lab VMs maximum

This stack is intentional. It should be treated as a serious, resource-aware, free, self-hosted, laptop-safe stack. I do not want the project to drift into heavyweight always-on infrastructure just because it sounds more enterprise on paper. Unless there is an exceptional reason later, I do not want the core identity of the project to depend on Kafka, Temporal, ClickHouse, Kubernetes, OpenCTI, or other heavyweight services running all the time locally.

A major constraint is that this project is being designed around my real development machine: a Lenovo Legion Slim 5 Gen 8 14-inch AMD laptop. I code and run everything on this machine. So the architecture has to remain impressive, serious, and powerful while still being sustainable for long daily use. I do not want a stack that sounds elite but is miserable to run. I want a stack that is genuinely free, practical, strong, and efficient enough to support repeated development, demos, and long work sessions without turning the machine into an overloaded homelab.

That means the system should feel elite because:
- the product thinking is strong
- the detection and incident logic are meaningful
- the architecture is disciplined
- the response model is thoughtful
- the frontend feels real
- the custom logic is substantial

It should not feel elite merely because it uses bloated infrastructure.

On the backend side, I want Python to be the main language for the intelligence of the platform. It should own the integration logic, event processing, normalization, correlation, ATT&CK context support, severity and confidence reasoning, response policy logic, and anything that feels like the brain of the product.

FastAPI should be the backend application layer. It should expose the product surfaces cleanly, such as incidents, entities, timelines, detections, actions, evidence, and related product-level APIs. The backend should feel like a real application backend, not a collection of scripts.

PostgreSQL should be the durable system of record for the platform’s structured state. Redis should be used intentionally for short-lived or coordination-oriented needs such as caching, temporary correlation windows, deduplication, throttling, or ephemeral processing support.

Wazuh should be treated as the primary upstream telemetry source in the initial design, but not as the product itself. Sigma should help reinforce that the detection logic is structured and threat-informed. Next.js and TypeScript should power a polished analyst-facing frontend that feels like a real product surface, not a generic admin panel.

The frontend is very important. I want the analyst experience to feel real, coherent, and product-like. The UI should help communicate that the platform is serious. It should support ideas like:
- incident visibility
- incident detail
- timelines
- evidence
- observables
- related entities
- ATT&CK context
- response history
- incident state transitions
- clear understanding of what happened and why

I want the user experience to reflect the actual workflow of a security analyst:
see incident -> understand context -> inspect evidence -> understand relationships -> review or execute response -> preserve history

I also want explainability to be part of the project’s DNA. The system should not feel like a black box. I want it to be possible to understand:
- what signals contributed to an incident
- why the incident exists
- how relationships were inferred
- why the severity and confidence ended up where they did
- what response was suggested or executed
- when and why platform state changed

I want ATT&CK awareness to be part of the project as well, but in a disciplined way. I do not want empty ATT&CK branding. I want it used where it meaningfully adds context, credibility, and clarity to detections and incidents.

The incident model itself should feel central and professional. Incidents should not just be glorified alerts. They should feel like the main working object of the system. A serious incident in this platform should conceptually include things like:
- a summary or title
- incident type
- severity
- confidence
- current status
- involved users
- involved hosts
- related observables
- evidence references
- a timeline of contributing events
- ATT&CK context where useful
- triggered detections
- recommended or executed actions
- rationale or explanation

Response should be treated as a first-class product capability. The platform should support controlled defensive actions in a lab-safe and auditable way. I want the response philosophy to be thoughtful, not reckless. The system should be able to distinguish between:
- actions safe enough to automate
- actions better suggested than executed
- reversible actions
- disruptive actions that require more care

I want response to feel like part of serious incident handling, not like a gimmick. The project should communicate that controlled response, explainability, and evidence preservation all matter together.

Overall, I want this project to meet a high professional bar. I want it to feel:
- modern
- technically mature
- coherent
- threat-informed
- defensive
- productized
- recruiter-impressive
- aligned with real security workflows
- realistic for the chosen stack and machine
- clearly stronger than a basic student security project

For now, do not give me coding steps or implementation tasks yet. I do not want you to decide what to build first in this response. I want you to absorb this as the overall project idea and internalize the system identity, design philosophy, quality bar, constraints, and intended impression. Treat this as the high-level authoritative explanation of what this project is supposed to become.