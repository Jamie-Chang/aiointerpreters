import asyncio
import concurrent.futures
import concurrent.futures.interpreter
import concurrent.futures.thread
import functools
from dataclasses import dataclass
from typing import Callable

__all__ = ("interpreter", "InterpreterThreadPoolExecutor")


@dataclass
class interpreter[**P, R]:
    """Mark function to run in an isolated interpreter."""

    fn: Callable[P, R]

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        return self.fn(*args, **kwargs)


class WorkerContext(concurrent.futures.thread.WorkerContext):
    def __init__(self, initializer, initargs):
        super().__init__(initializer, initargs)
        self.interp_context: concurrent.futures.interpreter.WorkerContext | None = None

    def __del__(self):
        if self.interp_context:
            self.interp_context.__del__()

    def finalize(self):
        if self.interp_context:
            self.interp_context.finalize()

    def _get_interp_context(self):
        if not self.interp_context:
            if self.initializer is not None:
                try:
                    initdata = (self.initializer, self.initargs, {})
                except ValueError:
                    if isinstance(initializer, str) and initargs:
                        raise ValueError(
                            f"an initializer script does not take args, got {initargs!r}"
                        )
                    raise  # re-raise
            else:
                initdata = None
            self.interp_context = concurrent.futures.interpreter.WorkerContext(initdata)
            self.interp_context.initialize()
        return self.interp_context

    def run(self, task):
        match task:
            case (interpreter(fn), *rest):
                return self._get_interp_context().run((fn, *rest))
            case (functools.partial(args=(interpreter(fn), *args), keywords=kwargs), (), {}):
                return self._get_interp_context().run((fn, args, kwargs))
            case task:
                return super().run(task)


class InterpreterThreadPoolExecutor(concurrent.futures.InterpreterPoolExecutor):
    """ThreadPoolExecutor that dispatches an interpreter when fn is tagged with `interpreter`.

    Warning:
        The main limitation is that only shareable/pickleable objects are allowed.

        This means that ordinarily we cannot run the executor with the ContextVar copied over.
        So `asyncio.to_thread` will break.

        For the time being the context is stripped when calling it with the asyncio.to_thread.
        This may change in the future.
    """

    @classmethod
    def prepare_context(cls, initializer, initargs):
        return WorkerContext.prepare(initializer, initargs)

    def set_as_event_loop_default(
        self, ctx: asyncio.EventLoop | asyncio.Runner | None = None
    ) -> None:
        """Shortcut to set `InterpreterThreadPoolExecutor` as default loop executor

        Equivalent to::
        >>> asyncio.get_running_loop().set_default_executor(InterpreterThreadPoolExecutor())
        """
        match ctx:
            case None:
                loop = asyncio.get_running_loop()
            case asyncio.EventLoop() as loop:
                loop = loop
            case asyncio.Runner() as runner:
                loop = runner.get_loop()
        loop.set_default_executor(self)
