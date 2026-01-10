import inspect
from dataclasses import dataclass
from types import CoroutineType, FrameType
from typing import Any, Callable, Generator


def get_function[R](
    coro: CoroutineType[Any, None, R],
) -> tuple[Callable[..., CoroutineType[Any, None, R]], tuple, dict]:
    match coro.cr_frame:
        case FrameType(f_code=object(co_name=name), f_locals={"self": instance}):
            func = getattr(instance, name)
        case FrameType(f_code=object(co_name=name), f_locals={"cls": class_}):
            func = getattr(class_, name)
        case FrameType(f_code=object(co_name=name), f_globals=g) if name in g:
            func = g[name]
        case None:
            raise RuntimeError("Coroutine must not be started")
        case _:
            raise ValueError(f"Unable to destructure {coro}")

    arg_names, varargs_name, varkw_name, local_vars = inspect.getargvalues(coro.cr_frame)

    final_args = []
    final_kwargs = {}

    sig = inspect.signature(func)

    for name in arg_names:
        if name in ("cls", "self"):
            continue
        val = local_vars[name]

        param = sig.parameters[name]
        if param.kind is not param.KEYWORD_ONLY:
            final_args.append(val)
        else:
            final_kwargs[name] = val

    # Handle *args
    if varargs_name and varargs_name in local_vars:
        final_args.extend(local_vars[varargs_name])

    # Handle **kwargs
    if varkw_name and varkw_name in local_vars:
        final_kwargs.update(local_vars[varkw_name])

    return func, tuple(final_args), final_kwargs


@dataclass
class PickleableCoroutine[R]:
    """Coroutine wrapper that is pickleable.

    This is achieved by destructuring it into its original arguments and function.
    """

    coroutine: CoroutineType[Any, None, R]

    def __await__(self) -> Generator[Any, None, R]:
        return self.coroutine.__await__()

    def __reduce__(self):
        return restore, get_function(self.coroutine)


def restore[R](
    func: Callable[..., CoroutineType[Any, None, R]], args: tuple, kwargs: dict
) -> CoroutineType[Any, None, R]:
    return func(*args, **kwargs)
