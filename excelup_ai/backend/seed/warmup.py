"""Keep Neon awake: SELECT 1 every 4 minutes. Run alongside demos:
    python -m seed.warmup
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.config import settings  # noqa: E402


async def main():
    if not settings.database_url:
        print("BLOCKED: create .env with DATABASE_URL first.")
        sys.exit(2)
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(settings.async_url, pool_pre_ping=True)
    print("Keeping Neon awake - Ctrl+C to stop.")
    while True:
        try:
            async with engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            print(".", flush=True)
        except Exception as exc:
            print(f"heartbeat failed: {exc}", flush=True)
        await asyncio.sleep(240)


if __name__ == "__main__":
    asyncio.run(main())
