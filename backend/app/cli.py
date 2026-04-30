"""Bootstrap CLI for CyberCat auth management.

Not network-callable — direct DB access only. Run after `alembic upgrade head`.

Usage:
    python -m app.cli seed-admin --email admin@local --password changeme
    python -m app.cli create-user --email user@local --password changeme --role read_only
    python -m app.cli set-role --email user@local --role analyst
    python -m app.cli issue-token --email user@local --name smoke-tests
    python -m app.cli revoke-token --token-id <uuid>
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from datetime import UTC

from sqlalchemy import select

from app.auth.models import ApiToken, User, UserRole
from app.auth.security import generate_token, hash_password
from app.db.session import AsyncSessionLocal


async def _seed_admin(email: str, password: str) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == email))
        if result.scalar_one_or_none():
            print(f"User {email!r} already exists — skipping.")
            return
        user = User(email=email, password_hash=hash_password(password), role=UserRole.admin, is_active=True)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        print(f"Admin created: {email}  id={user.id}")


async def _create_user(email: str, password: str, role: UserRole) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == email))
        if result.scalar_one_or_none():
            print(f"User {email!r} already exists.", file=sys.stderr)
            sys.exit(1)
        user = User(email=email, password_hash=hash_password(password), role=role, is_active=True)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        print(f"User created: {email}  role={role.value}  id={user.id}")


async def _set_role(email: str, role: UserRole) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user is None:
            print(f"User {email!r} not found.", file=sys.stderr)
            sys.exit(1)
        user.role = role
        await db.commit()
        print(f"Updated {email}: role={role.value}")


async def _issue_token(email: str, name: str) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == email, User.is_active.is_(True)))
        user = result.scalar_one_or_none()
        if user is None:
            print(f"Active user {email!r} not found.", file=sys.stderr)
            sys.exit(1)
        plaintext, digest = generate_token()
        token = ApiToken(user_id=user.id, name=name, token_hash=digest)
        db.add(token)
        await db.commit()
        await db.refresh(token)
        print(f"Token issued for {email}:")
        print(f"  name : {name}")
        print(f"  id   : {token.id}")
        print(f"  token: {plaintext}")
        print("Store this token now — it will not be shown again.")


async def _revoke_token(token_id_str: str) -> None:
    from datetime import datetime

    tid = uuid.UUID(token_id_str)
    async with AsyncSessionLocal() as db:
        token = await db.get(ApiToken, tid)
        if token is None:
            print(f"Token {token_id_str!r} not found.", file=sys.stderr)
            sys.exit(1)
        if token.revoked_at is not None:
            print(f"Token already revoked at {token.revoked_at}.")
            return
        token.revoked_at = datetime.now(UTC)
        await db.commit()
        print(f"Token {token_id_str} revoked.")


def main() -> None:
    parser = argparse.ArgumentParser(description="CyberCat auth bootstrap CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("seed-admin", help="Create the first admin (idempotent)")
    p.add_argument("--email", required=True)
    p.add_argument("--password", required=True)

    p = sub.add_parser("create-user", help="Create a new user")
    p.add_argument("--email", required=True)
    p.add_argument("--password", required=True)
    p.add_argument("--role", required=True, choices=[r.value for r in UserRole])

    p = sub.add_parser("set-role", help="Change a user's role")
    p.add_argument("--email", required=True)
    p.add_argument("--role", required=True, choices=[r.value for r in UserRole])

    p = sub.add_parser("issue-token", help="Issue a new API token")
    p.add_argument("--email", required=True)
    p.add_argument("--name", required=True)

    p = sub.add_parser("revoke-token", help="Revoke an API token by ID")
    p.add_argument("--token-id", required=True)

    args = parser.parse_args()

    dispatch = {
        "seed-admin": lambda: _seed_admin(args.email, args.password),
        "create-user": lambda: _create_user(args.email, args.password, UserRole(args.role)),
        "set-role": lambda: _set_role(args.email, UserRole(args.role)),
        "issue-token": lambda: _issue_token(args.email, args.name),
        "revoke-token": lambda: _revoke_token(args.token_id),
    }
    asyncio.run(dispatch[args.cmd]())


if __name__ == "__main__":
    main()
