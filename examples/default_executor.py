import asyncio
import time
from contextlib import contextmanager
from typing import Awaitable

from aiointerpreters.executors import InterpreterThreadPoolExecutor, interpreter


@contextmanager
def timer(message: str):
    start = time.perf_counter()
    try:
        yield
    finally:
        print(f"{message} {time.perf_counter() - start} s elapsed")


def sum_of_squares(num: int) -> int:
    return sum(i * i for i in range(num + 1))


async def to_coro[T](aw: Awaitable[T]) -> T:
    return await aw


async def main() -> None:
    InterpreterThreadPoolExecutor().set_as_event_loop_default()
    runs = 10

    with timer("Single Run"):
        for _ in range(runs):
            sum_of_squares(10_000_000)

    with timer("Async Executor Run"):
        async with asyncio.TaskGroup() as tg:
            for _ in range(runs):
                tg.create_task(asyncio.to_thread(interpreter(sum_of_squares), 10_000_000))

    with timer("Async Executor Run (Non-Interpreter)"):
        async with asyncio.TaskGroup() as tg:
            for _ in range(runs):
                tg.create_task(asyncio.to_thread(sum_of_squares, 10_000_000))


if __name__ == "__main__":
    asyncio.run(main())
