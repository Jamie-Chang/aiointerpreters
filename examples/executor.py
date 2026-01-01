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
    runs = 10

    with timer("Single Run"):
        for _ in range(runs):
            sum_of_squares(10_000_000)

    with timer("Async Executor Run"):
        with InterpreterThreadPoolExecutor() as executor:
            loop = asyncio.get_event_loop()
            async with asyncio.TaskGroup() as tg:
                for _ in range(runs):
                    tg.create_task(
                        to_coro(
                            loop.run_in_executor(executor, interpreter(sum_of_squares), 10_000_000)
                        )
                    )

    with timer("Sync Executor Run (Non-Interpreter)"):
        with InterpreterThreadPoolExecutor() as executor:
            executor.map(sum_of_squares, (10_000_000 for _ in range(runs)))

    with timer("Sync Executor Run"):
        with InterpreterThreadPoolExecutor() as executor:
            executor.map(interpreter(sum_of_squares), (10_000_000 for _ in range(runs)))


if __name__ == "__main__":
    asyncio.run(main())
