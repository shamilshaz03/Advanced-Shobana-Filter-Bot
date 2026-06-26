import asyncio
import logging

logger = logging.getLogger(__name__)


async def run_daily_summary(client):
    """Placeholder daily summary task."""
    while True:
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"daily_summary: {e}")
