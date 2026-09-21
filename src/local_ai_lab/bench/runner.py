from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence


async def run_concurrent[InputT, OutputT](
    *,
    items: Sequence[InputT],
    concurrency: int,
    operation: Callable[[InputT], Awaitable[OutputT]],
) -> list[OutputT]:
    if concurrency <= 0:
        raise ValueError("concurrency must be positive")
    semaphore = asyncio.Semaphore(concurrency)

    async def bounded(item: InputT) -> OutputT:
        async with semaphore:
            return await operation(item)

    return list(await asyncio.gather(*(bounded(item) for item in items)))
