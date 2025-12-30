import asyncio
import concurrent.futures
import concurrent.interpreters
import concurrent.interpreters._queues
import importlib
import importlib.util
import inspect
import sys
from contextlib import asynccontextmanager
from functools import cache
from threading import Thread
from typing import Any, Awaitable, Coroutine, Literal, cast

__all__ = ("EventLoopRunner",)

type Module = str
type Path = str
type FunctionName = str
type FunctionInfo = tuple[Literal["module", "path"], Module | Path, FunctionName]
type Args = tuple[object, ...]
type Kwargs = tuple[tuple[str, object], ...]
type EncodedCoroutine = tuple[FunctionInfo, Args, Kwargs]


def encode_coroutine(coro) -> EncodedCoroutine:
    """
    Encodes an unrun coroutine into a serializable state.

    Raises:
        ValueError: If the coroutine has already started or finished.
    """
    # 1. Assert the coroutine is unrun
    if inspect.getcoroutinestate(coro) != inspect.CORO_CREATED:
        raise ValueError(
            "Coroutine has already started or finished. Cannot safely encode."
        )

    code = coro.cr_code
    frame = coro.cr_frame

    func_name = code.co_name
    module_name = frame.f_globals.get("__name__", "")

    if module_name == "__main__":
        fn_info = ("path", code.co_filename, func_name)
    else:
        fn_info = ("module", module_name, func_name)

    arg_names, varargs_name, varkw_name, local_vars = inspect.getargvalues(frame)

    final_args = []
    final_kwargs = []

    pos_only_count = code.co_posonlyargcount

    for i, name in enumerate(arg_names):
        val = local_vars[name]

        if i < pos_only_count:
            final_args.append(val)
        else:
            final_kwargs.append((name, val))

    # Handle *args
    if varargs_name and varargs_name in local_vars:
        final_args.extend(local_vars[varargs_name])

    # Handle **kwargs
    if varkw_name and varkw_name in local_vars:
        for k, v in local_vars[varkw_name].items():
            final_kwargs.append((k, v))

    return fn_info, tuple(final_args), tuple(final_kwargs)


@cache
def load_entry_point(entry_point_type, path_or_module, name):
    if entry_point_type == "module":
        return getattr(importlib.import_module(path_or_module), name)

    elif entry_point_type == "path":
        spec = importlib.util.spec_from_file_location("my_module", path_or_module)
        module = importlib.util.module_from_spec(spec)
        sys.modules["my_module"] = module
        spec.loader.exec_module(module)
        return getattr(module, name)

    else:
        assert False


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
                    case id, ((entry_point_type, module, name), args, kwargs):
                        tg.create_task(
                            _notify_result(
                                id,
                                load_entry_point(entry_point_type, module, name)(
                                    *args, **dict(kwargs)
                                ),
                            )
                        )
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
        >>> async with EventLoopRunner(workers=5, batch_size=2).start() as runner:
        ...     runner.create_task(asyncio.sleep(5))
        ...     runner.create_task(asyncio.sleep(5))
        ...     runner.create_task(asyncio.sleep(5))
        ...     runner.create_task(asyncio.sleep(5))
        ...     runner.create_task(asyncio.sleep(5))

    Limitations:
        - Coroutine object must derive from an importable function
        - Coroutine must be unstarted
    """

    def __init__(self, *, workers: int, batch_size: int = 1) -> None:
        self._tasks = concurrent.interpreters.create_queue()
        self._results = concurrent.interpreters.create_queue()
        self._futures: dict[int, asyncio.Future] = {}
        self._workers = workers
        self._task_group = asyncio.TaskGroup()
        self._loop = asyncio.get_running_loop()
        self._batch_size = batch_size

    def _results_worker(self) -> None:
        while res := self._results.get():
            res = cast(tuple[int, bool, Any], res)
            match res:
                case (id, True, result):
                    future = self._futures.pop(id)
                    self._loop.call_soon_threadsafe(future.set_result, result)
                case (id, False, str(e)):
                    future = self._futures.pop(id)
                    self._loop.call_soon_threadsafe(
                        future.set_exception,
                        Exception(f"Got unshareable exception: {e}"),
                    )

                case (id, False, Exception() as e):
                    future = self._futures.pop(id)
                    self._loop.call_soon_threadsafe(future.set_exception, e)
                case concurrent.interpreters._queues.UNBOUND:
                    # Abrupt termination, items may become unbound
                    return

    @asynccontextmanager
    async def start(self):
        with concurrent.futures.InterpreterPoolExecutor(
            max_workers=self._workers
        ) as executor:
            for _ in range(self._workers):
                executor.submit(
                    runner_sync, self._tasks, self._results, self._batch_size
                )

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

    async def _run[T](self, coro: Coroutine[None, None, T]) -> T:
        future = asyncio.Future()
        self._futures[id(future)] = future
        self._tasks.put((id(future), encode_coroutine(coro)))
        try:
            res = await future
            return res
        finally:
            coro.close()

    def create_task[T](self, coro: Coroutine[None, None, T]) -> asyncio.Task[T]:
        return self._task_group.create_task(self._run(coro))
