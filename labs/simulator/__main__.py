"""Entry point: python -m labs.simulator --scenario <name> [--api URL] [--speed N]"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from labs.simulator.client import SimulatorClient
from labs.simulator.scenarios import get_scenario, list_scenarios

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s")


def _parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m labs.simulator",
        description="CyberCat attack simulator — fires events against a running backend.",
    )
    p.add_argument("--scenario", required=True, help="Scenario name (e.g. credential_theft_chain)")
    p.add_argument("--api", default="http://localhost:8000", help="Backend base URL")
    p.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help=(
            "Time compression factor. 1.0 = real-time (~5 min). "
            "0.1 = compressed to ~30s for quick testing."
        ),
    )
    p.add_argument(
        "--verify",
        dest="verify",
        action="store_true",
        default=True,
        help="Assert expected incident tree after scenario (default: on)",
    )
    p.add_argument(
        "--no-verify",
        dest="verify",
        action="store_false",
        help="Skip post-scenario outcome verification",
    )
    p.add_argument(
        "--token",
        default=None,
        help="Bearer token for AUTH_REQUIRED=true mode (cct_... value from cli issue-token)",
    )
    return p.parse_args()


async def _run() -> int:
    args = _parse()

    scenario = get_scenario(args.scenario)
    if scenario is None:
        print(
            f"Unknown scenario: {args.scenario!r}\n"
            f"Available: {', '.join(list_scenarios())}"
        )
        return 1

    if args.speed <= 0:
        print(f"--speed must be > 0, got {args.speed}")
        return 1

    print(
        f"CyberCat Simulator — scenario={args.scenario!r}  "
        f"api={args.api}  speed={args.speed}"
    )

    async with SimulatorClient(base_url=args.api, token=args.token) as client:
        if not await client.healthz():
            print(f"ERROR: backend not reachable at {args.api}/healthz")
            return 1

        await scenario.run(client, speed=args.speed)

        if args.verify:
            ok = await scenario.verify(client)
            return 0 if ok else 1

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
