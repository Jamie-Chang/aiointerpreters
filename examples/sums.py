import asyncio
import os
import time
from contextlib import contextmanager

from aiointerpreters.runner import Runner


@contextmanager
def timer(message: str):
    start = time.perf_counter()
    try:
        yield
    finally:
        print(f"{message} {time.perf_counter() - start} s elapsed")


def sum_of_squares(num: int) -> int:
    return sum(i * i for i in range(num + 1))


async def main() -> None:
    runs = 10

    with timer("Single Run"):
        for _ in range(runs):
            sum_of_squares(10_000_000)

    with Runner(workers=os.cpu_count() or 10).start() as runner:
        async_sum_of_squares = runner.wrap(sum_of_squares)
        with timer("Parallel Run"):
            async with asyncio.TaskGroup() as tg:
                for _ in range(runs):
                    tg.create_task(async_sum_of_squares(10_000_000))


if __name__ == "__main__":
    asyncio.run(main())
