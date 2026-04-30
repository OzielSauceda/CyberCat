"""Entry point for ``python -m cct_agent``.

Wires together config → checkpoints → tails → parsers → shipper and
runs them under one event loop until SIGTERM/SIGINT.

Topology (Phase 16.10):

    /var/log/auth.log    /var/log/audit/audit.log    /var/log/conntrack.log
            │                     │                            │
            ▼                     ▼                            ▼
     tail_lines (sshd)     tail_lines (auditd)         tail_lines (conntrack)
            │                     │                            │
            ▼                     ▼                            ▼
     sshd.parse_line       AuditdParser.feed         conntrack.parse_line
            │                     │                            │
            ▼                     ▼                            │
     events.build_event   process_state.TrackedProcesses       │
            │                     │                            │
            │                     ▼                            │
            │              events.build_event                  │
            │                     │                   events.build_event
            │                     │                            │
            ▼                     ▼                            ▼
            └────────────► Shipper.enqueue ◄───────────────────┘
                                  │
                                  ▼
                             Shipper.run  (batch + POST + retry)

All three sources own their own checkpoint files and run as independent
asyncio tasks. Each is gated on its ``*_enabled`` flag AND a path-exists
check at startup, so the agent degrades gracefully when a subsystem is
unavailable.
"""
from __future__ import annotations

import asyncio
import logging
import signal
import sys
from pathlib import Path

from cct_agent.checkpoint import Checkpoint
from cct_agent.config import AgentConfig
from cct_agent.events import build_event
from cct_agent.parsers.auditd import AuditdParser
from cct_agent.parsers.conntrack import parse_line as parse_conntrack_line
from cct_agent.parsers.sshd import parse_line as parse_sshd_line
from cct_agent.process_state import TrackedProcesses
from cct_agent.shipper import Shipper
from cct_agent.sources.tail import tail_lines

log = logging.getLogger("cct_agent")


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )


async def _run_sshd_source(
    config: AgentConfig,
    shipper: Shipper,
    stop_event: asyncio.Event,
) -> None:
    """Tail /var/log/auth.log; parse with the sshd parser; enqueue events."""
    log_path = Path(config.log_path)
    cp_path = Path(config.checkpoint_path)
    checkpoint = Checkpoint.load(cp_path)
    log.info("sshd source started, tailing %s", log_path)
    try:
        async for line in tail_lines(
            log_path,
            checkpoint,
            poll_interval=config.poll_interval_seconds,
            stop_event=stop_event,
        ):
            parsed = parse_sshd_line(line)
            if parsed is not None:
                try:
                    event = build_event(parsed, host=config.host_name)
                except Exception as e:  # pragma: no cover — defensive
                    log.exception("build_event(sshd) failed for kind=%s: %s", parsed.kind, e)
                else:
                    await shipper.enqueue(event)
            try:
                checkpoint.save()
            except OSError as e:
                log.warning("sshd checkpoint save failed: %s", e)
    except asyncio.CancelledError:
        raise
    except Exception:
        log.exception("sshd source crashed")
        raise


async def _run_auditd_source(
    config: AgentConfig,
    shipper: Shipper,
    stop_event: asyncio.Event,
) -> None:
    """Tail /var/log/audit/audit.log; assemble events; enqueue process.* events."""
    log_path = Path(config.audit_log_path)
    cp_path = Path(config.audit_checkpoint_path)
    checkpoint = Checkpoint.load(cp_path)
    parser = AuditdParser()
    tracker = TrackedProcesses()
    log.info("auditd source started, tailing %s", log_path)
    try:
        async for line in tail_lines(
            log_path,
            checkpoint,
            poll_interval=config.poll_interval_seconds,
            stop_event=stop_event,
        ):
            for parsed in parser.feed(line):
                if parsed.kind == "process.created":
                    enriched = tracker.record(parsed)
                    final = enriched
                else:  # process.exited
                    resolved = tracker.resolve_exit(parsed)
                    if resolved is None:
                        # Untracked exit (cold start or evicted) — drop silently
                        continue
                    final = resolved
                try:
                    event = build_event(final, host=config.host_name)
                except Exception as e:  # pragma: no cover — defensive
                    log.exception(
                        "build_event(auditd) failed for kind=%s: %s", final.kind, e
                    )
                else:
                    await shipper.enqueue(event)
            try:
                checkpoint.save()
            except OSError as e:
                log.warning("audit checkpoint save failed: %s", e)
    except asyncio.CancelledError:
        raise
    except Exception:
        log.exception("auditd source crashed")
        raise


async def _run_conntrack_source(
    config: AgentConfig,
    shipper: Shipper,
    stop_event: asyncio.Event,
) -> None:
    """Tail /var/log/conntrack.log; parse with conntrack parser; enqueue events."""
    log_path = Path(config.conntrack_log_path)
    cp_path = Path(config.conntrack_checkpoint_path)
    checkpoint = Checkpoint.load(cp_path)
    log.info("conntrack source started, tailing %s", log_path)
    try:
        async for line in tail_lines(
            log_path,
            checkpoint,
            poll_interval=config.poll_interval_seconds,
            stop_event=stop_event,
        ):
            parsed = parse_conntrack_line(line)
            if parsed is not None:
                try:
                    event = build_event(parsed, host=config.host_name)
                except Exception as e:  # pragma: no cover — defensive
                    log.exception(
                        "build_event(conntrack) failed for kind=%s: %s",
                        parsed.kind,
                        e,
                    )
                else:
                    await shipper.enqueue(event)
            try:
                checkpoint.save()
            except OSError as e:
                log.warning("conntrack checkpoint save failed: %s", e)
    except asyncio.CancelledError:
        raise
    except Exception:
        log.exception("conntrack source crashed")
        raise


def audit_source_active(config: AgentConfig) -> bool:
    """Should the auditd source spin up?

    Active when ``audit_enabled`` is true *and* the configured audit log
    file exists at startup. Anything else means we degrade gracefully to
    sshd-only mode (with a warning so the operator notices).
    """
    if not config.audit_enabled:
        return False
    return Path(config.audit_log_path).exists()


def conntrack_source_active(config: AgentConfig) -> bool:
    """Should the conntrack source spin up?

    Active when ``conntrack_enabled`` is true *and* the configured
    conntrack log file exists at startup. Mirrors ``audit_source_active``;
    the conntrack tail self-creates a checkpoint and waits when the file
    is empty, but if the file does not exist at startup we skip and warn
    so the operator notices the misconfiguration.
    """
    if not config.conntrack_enabled:
        return False
    return Path(config.conntrack_log_path).exists()


async def _run(config: AgentConfig, stop_event: asyncio.Event) -> None:
    if not config.agent_token:
        log.error("CCT_AGENT_TOKEN is empty; refusing to start")
        return

    shipper = Shipper(config)

    sources: list[str] = [config.log_path]
    tasks: list[asyncio.Task[None]] = []

    audit_path = Path(config.audit_log_path)
    audit_active = audit_source_active(config)
    if config.audit_enabled and not audit_path.exists():
        log.warning(
            "auditd source disabled: %s does not exist (kernel audit unavailable?)",
            audit_path,
        )

    if audit_active:
        sources.append(str(audit_path))

    conntrack_path = Path(config.conntrack_log_path)
    conntrack_active = conntrack_source_active(config)
    if config.conntrack_enabled and not conntrack_path.exists():
        log.warning(
            "conntrack source disabled: %s does not exist (kernel conntrack unavailable?)",
            conntrack_path,
        )

    if conntrack_active:
        sources.append(str(conntrack_path))

    log.info(
        "agent ready, tailing %s (api=%s, host=%s, batch=%d, flush=%.1fs, queue_max=%d)",
        " + ".join(sources),
        config.api_url,
        config.host_name,
        config.batch_size,
        config.flush_interval_seconds,
        config.queue_max,
    )

    shipper_task = asyncio.create_task(shipper.run(stop_event), name="shipper")
    sshd_task = asyncio.create_task(
        _run_sshd_source(config, shipper, stop_event), name="sshd-source"
    )
    tasks.append(sshd_task)
    if audit_active:
        audit_task = asyncio.create_task(
            _run_auditd_source(config, shipper, stop_event), name="auditd-source"
        )
        tasks.append(audit_task)
    if conntrack_active:
        conntrack_task = asyncio.create_task(
            _run_conntrack_source(config, shipper, stop_event),
            name="conntrack-source",
        )
        tasks.append(conntrack_task)

    try:
        # Wait until stop is signalled (signal handler) or any source crashes.
        done, pending = await asyncio.wait(
            [stop_event_wait_task(stop_event), *tasks],
            return_when=asyncio.FIRST_COMPLETED,
        )
        # If a source raised, surface it so the operator sees the crash;
        # but still proceed to clean shutdown below.
        for t in done:
            if t in tasks and not t.cancelled():
                exc = t.exception()
                if exc is not None:
                    log.error("source task exited with exception: %s", exc)
    finally:
        stop_event.set()
        # Cancel any source tasks that are still running
        for t in tasks:
            if not t.done():
                t.cancel()
        for t in tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        try:
            await asyncio.wait_for(shipper_task, timeout=10.0)
        except TimeoutError:
            log.warning("shipper did not stop within 10s; cancelling")
            shipper_task.cancel()
            try:
                await shipper_task
            except (asyncio.CancelledError, Exception):
                pass
        log.info(
            "agent stopped (shipped=%d, failed=%d, dropped=%d)",
            shipper.shipped_count,
            shipper.failed_count,
            shipper.dropped_count,
        )


def stop_event_wait_task(stop_event: asyncio.Event) -> asyncio.Task[None]:
    """Return a Task that completes when ``stop_event`` is set."""
    return asyncio.create_task(stop_event.wait(), name="stop-waiter")


def _install_signal_handlers(loop: asyncio.AbstractEventLoop, stop_event: asyncio.Event) -> None:
    def _handler() -> None:
        log.info("received signal; stopping")
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _handler)
        except NotImplementedError:
            # Windows event loop does not support add_signal_handler — fall
            # back to the synchronous signal.signal hook, which works for
            # SIGINT during interactive runs.
            try:
                signal.signal(sig, lambda *_: stop_event.set())
            except (OSError, ValueError):
                pass


def main() -> None:
    _setup_logging()
    config = AgentConfig()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    stop_event = asyncio.Event()
    _install_signal_handlers(loop, stop_event)
    try:
        loop.run_until_complete(_run(config, stop_event))
    finally:
        loop.close()


if __name__ == "__main__":
    main()
