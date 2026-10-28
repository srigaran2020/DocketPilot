"""Admin command line.

Create the first firm and admin (the password is asked for, or read from DP_ADMIN_PASSWORD):
    python -m docketpilot.cli create-admin --firm "Demo Chambers" --email admin@example.com --name "Admin"
"""
import argparse
import asyncio
import getpass
import os

from sqlalchemy import select

from docketpilot import audit
from docketpilot.db import SessionLocal
from docketpilot.models import Firm, Role, User
from docketpilot.security import hash_password


async def create_admin(firm_name: str, email: str, name: str, password: str) -> None:
    async with SessionLocal() as session:
        firm = (await session.execute(select(Firm).where(Firm.name == firm_name))).scalar_one_or_none()
        if firm is None:
            firm = Firm(name=firm_name)
            session.add(firm)
            await session.flush()
        user = User(firm_id=firm.id, email=email.lower(), full_name=name,
                    password_hash=hash_password(password), role=Role.admin)
        session.add(user)
        await session.flush()
        audit.record(session, "user.create", firm_id=firm.id, target_type="user",
                     target_id=str(user.id), details={"role": "admin", "via": "cli"})
        await session.commit()
        print(f"created admin user {user.id} in firm {firm.id}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="docketpilot.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("create-admin")
    p.add_argument("--firm", required=True)
    p.add_argument("--email", required=True)
    p.add_argument("--name", required=True)
    args = parser.parse_args()

    password = os.environ.get("DP_ADMIN_PASSWORD") or getpass.getpass("Password (min 12 chars): ")
    if len(password) < 12:
        raise SystemExit("password must be at least 12 characters")
    asyncio.run(create_admin(args.firm, args.email, args.name, password))


if __name__ == "__main__":
    main()
