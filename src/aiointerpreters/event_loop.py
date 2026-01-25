import asyncio
import concurrent.futures
import concurrent.interpreters
import concurrent.interpreters._queues
from contextlib import asynccontextmanager
from threading import Thread
from types import CoroutineType, TracebackType
from typing import Any, AsyncContextManager, Awaitable, cast

from .coro import PickleableCoroutine

__all__ = ("EventLoopRunner",)


def get_many(queue: concurrent.interpreters.Queue, batch_size: int = 1) -> list:
    values = [queue.get()]

    for _ in range(batch_size - 1):
        if values[-1] is None:
            return values

        try:
            values.append(queue.get_nowait())
        except concurrent.interpreters.QueueEmpty:
            break

    return values


async def runner_async(
    queue: concurrent.interpreters.Queue,
    results: concurrent.interpreters.Queue,
    batch_size: int = 1,
) -> None:
    async def _notify_result(id: int, coro: Awaitable) -> None:
        try:
            results.put((id, True, await coro))
        except Exception as e:
            try:
                results.put((id, False, e))
            except concurrent.interpreters.NotShareableError:
                results.put((id, False, repr(e)))

    while True:
        items = get_many(queue, batch_size=batch_size)
        async with asyncio.TaskGroup() as tg:
            for value in items:
                match value:
                    case None:
                        # Signal to terminate
                        return
                    case id, CoroutineType() as coro:
                        tg.create_task(_notify_result(id, coro))

                    case id, [*coros]:
                        tg.create_task(_notify_result(id, asyncio.gather(*coros)))

                    case concurrent.interpreters._queues.UNBOUND:
                        # Abrupt termination, items may become unbound
                        return


def runner_sync(
    queue: concurrent.interpreters.Queue,
    results: concurrent.interpreters.Queue,
    batch_size: int = 1,
) -> None:
    asyncio.run(runner_async(queue, results, batch_size))


class EventLoopRunner:
    """Run a top level asyncio coroutine in a separate interpreter thread.

    Example::
        >>> async with EventLoopRunner(workers=5, batch_size=2) as runner:
        ...     runner.create_task(asyncio.sleep(5))
        ...     runner.create_task(asyncio.sleep(5))
        ...     runner.create_task(asyncio.sleep(5))
        ...     runner.create_task(asyncio.sleep(5))
        ...     runner.create_task(asyncio.sleep(5))

    Limitations:
        - Coroutine object cannot derive from an inner function
        - Coroutine must be unstarted
    """

    def __init__(self, *, workers: int, batch_size: int = 1) -> None:
        self._tasks = concurrent.interpreters.create_queue()
        self._results = concurrent.interpreters.create_queue()
        self._futures: dict[int, asyncio.Future] = {}
        self._workers = workers
        self._task_group = asyncio.TaskGroup()
        self._batch_size = batch_size
        self._ctx: AsyncContextManager | None = None

    def _results_worker(self) -> None:
        while res := self._results.get():
            match cast(tuple[int, bool, Any], res):
                case (id, True, result):
                    future = self._futures.pop(id)
                    future.get_loop().call_soon_threadsafe(future.set_result, result)
                case (id, False, str(e)):
                    future = self._futures.pop(id)
                    future.get_loop().call_soon_threadsafe(
                        future.set_exception,
                        Exception(f"Got unshareable exception: {e}"),
                    )
                case (id, False, Exception() as e):
                    future = self._futures.pop(id)
                    future.get_loop().call_soon_threadsafe(future.set_exception, e)
                case concurrent.interpreters._queues.UNBOUND:
                    # Abrupt termination, items may become unbound
                    return

    async def start(self):
        return await self.__aenter__()

    async def stop(self):
        return await self.__aexit__(None, None, None)

    async def __aenter__(self):
        self._ctx = self.run()
        return await self._ctx.__aenter__()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ):
        assert self._ctx is not None
        await self._ctx.__aexit__(exc_type, exc_value, traceback)

    @asynccontextmanager
    async def run(self):
        with concurrent.futures.InterpreterPoolExecutor(max_workers=self._workers) as executor:
            for _ in range(self._workers):
                executor.submit(runner_sync, self._tasks, self._results, self._batch_size)

            thread = Thread(target=self._results_worker)
            thread.start()
            try:
                async with self._task_group:
                    yield self
            finally:
                self._results.put(None)
                for _ in range(self._workers):
                    self._tasks.put(None)
                thread.join()

    async def _run[T](self, coro: CoroutineType[Any, None, T]) -> T:
        future = asyncio.Future()
        self._futures[id(future)] = future
        self._tasks.put((id(future), PickleableCoroutine(coro)))
        try:
            return await future
        finally:
            coro.close()

    async def _run_batch[T](self, coros: list[CoroutineType[Any, None, T]]) -> tuple[T, ...]:
        future = asyncio.Future()
        self._futures[id(future)] = future
        self._tasks.put((id(future), [PickleableCoroutine(coro) for coro in coros]))
        try:
            return await future
        finally:
            for coro in coros:
                coro.close()

    def create_task[T](self, coro: CoroutineType[Any, None, T]) -> asyncio.Task[T]:
        return self._task_group.create_task(self._run(coro))

    def create_batch[T](
        self, coros: list[CoroutineType[Any, None, T]]
    ) -> asyncio.Task[tuple[T, ...]]:
        return self._task_group.create_task(self._run_batch(coros))
