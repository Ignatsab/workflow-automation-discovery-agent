"""Initialize the LangGraph PostgreSQL checkpoint schema."""

from __future__ import annotations

import asyncio
import os


async def migrate() -> None:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    database_url = os.environ.get("CHECKPOINT_DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("CHECKPOINT_DATABASE_URL must be configured")
    async with AsyncPostgresSaver.from_conn_string(database_url) as checkpointer:
        await checkpointer.setup()


def main() -> None:
    asyncio.run(migrate())


if __name__ == "__main__":
    main()
