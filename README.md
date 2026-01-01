# aiointerpreters
Run CPU bound code in [subinterpreters](https://docs.python.org/3.14/library/concurrent.interpreters.html) using asyncio.

## Installation
Pick the tool of your choosing

```bash
uv add aiointerpreters
uv pip install aiointerpreters
pip install aiointerpreters
poetry add aiointerpreters
pdm add aiointerpreters
pipenv install aiointerpreters
```

## Runner
See [runner docs](./runner.md), initially the library only exposes a `Runner` class with a custom interface to schedule asyncio tasks. 

Since the official release of 3.14 and the stablisation of a lot of the interpreter features, this offers no advantage to the standard library `InterpreterPoolExecutor` and therefore is not something that will be updated going forward.

## Executor
This library implements a new `InterpreterThreadPoolExecutor`. This is a drop in replacement for the standard `ThreadPoolExecutor` with options to dynamically switch to using an `Interpreter`.

```py
from aiointerpreters.executors import InterpreterThreadPoolExecutor, interpreter


with InterpreterThreadPoolExecutor() as executor:
    executor.map(interpreter(cpu_bound), (argument for _ in range(runs)))
```

Any function tagged with `interpreter` decorator will be dispatched to an isolated interpreter in a separate thread. Otherwise this follows the original behaviour of `ThreadPoolExecutor`.

Additionally, `InterpreterThreadPoolExecutor` can be set as the default executor for asyncio and used with `asyncio.to_thread`:

```py
# Shortcut 
InterpreterThreadPoolExecutor().set_as_event_loop_default()

# or 
asyncio.get_running_loop().set_default_executor(InterpreterThreadPoolExecutor())

async with asyncio.TaskGroup() as tg:
    tg.create_task(asyncio.to_thread(interpreter(cpu_bound), argument))
    tg.create_task(asyncio.to_thread(io_bound, argument))
```

### Restrictions
The CPU bound function must be picklable. All its arguments and return value must be pickables or [`Shareable`](https://github.com/Jamie-Chang/aiointerpreters/blob/main/src/aiointerpreters/types.py):

```py
type Shareable = (
    str | bytes | int | float | bool | None | tuple[Shareable, ...] | Queue | memoryview
)
```

### Motivation
`concurrent.future.InterpreterPoolExecutor` is currently a great choice if you know you always need an interpreter to run your code. However it's rarely something you want to do by default since you have to always consider the restrictions mentioned above.

You can choose to run a ThreadPoolExecutor alongside an InterpreterPoolExecutor but since they both maintain a pool of threads under the hood, it'll actually save some resources to share the pool of threads. And having one good default option just makes things easier. 

### Using `asyncio.to_thread`
Note: since `ContextVars` are [not pickleable](https://peps.python.org/pep-0567/#making-context-objects-picklable) `InterpreterThreadPoolExecutor` works around it by discarding the context, this is not slightly hacky and may change in the future.


## Examples
See [examples](https://github.com/Jamie-Chang/aiointerpreters/tree/main/examples).
