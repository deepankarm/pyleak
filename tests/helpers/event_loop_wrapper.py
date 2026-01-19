from contextlib import asynccontextmanager

from pyleak import no_event_loop_blocking


@asynccontextmanager
async def wrapped_no_event_loop_blocking(action="warn", threshold=0.2):
    async with no_event_loop_blocking(action=action, threshold=threshold):
        yield
