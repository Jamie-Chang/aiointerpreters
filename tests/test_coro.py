import asyncio
import pickle

import pytest

from aiointerpreters.coro import PickleableCoroutine


async def global_simple_add(a, b):
    await asyncio.sleep(0.01)
    return a + b


async def global_varargs(base, *args, **kwargs):
    await asyncio.sleep(0.01)
    result = base + sum(args)
    if "bonus" in kwargs:
        result += kwargs["bonus"]
    return result


class Calculator:
    def __init__(self, factor):
        self.factor = factor

    async def multiply(self, value):
        await asyncio.sleep(0.01)
        return value * self.factor

    @classmethod
    async def class_method_add(cls, x, y):
        await asyncio.sleep(0.01)
        return x + y


@pytest.mark.asyncio
async def test_global_function_basic():
    """Test pickling a simple global async function."""
    original_coro = global_simple_add(10, 20)
    wrapper = PickleableCoroutine(original_coro)

    dumped = pickle.dumps(wrapper)
    restored_wrapper = pickle.loads(dumped)

    result = await restored_wrapper
    assert result == 30


@pytest.mark.asyncio
async def test_instance_method():
    """Test pickling an instance method (requires 'self' binding)."""
    calc = Calculator(factor=5)
    # 10 * 5 = 50
    original_coro = calc.multiply(10)
    wrapper = PickleableCoroutine(original_coro)

    dumped = pickle.dumps(wrapper)
    restored_wrapper = pickle.loads(dumped)

    result = await restored_wrapper
    assert result == 50


@pytest.mark.asyncio
async def test_class_method():
    """Test pickling a @classmethod."""
    original_coro = Calculator.class_method_add(5, 5)
    wrapper = PickleableCoroutine(original_coro)

    dumped = pickle.dumps(wrapper)
    restored_wrapper = pickle.loads(dumped)

    result = await restored_wrapper
    assert result == 10


@pytest.mark.asyncio
async def test_complex_args_kwargs():
    """Test *args and **kwargs handling."""
    # base=10, args=(1,2,3), kwargs={'bonus': 5} -> 10 + 6 + 5 = 21
    original_coro = global_varargs(10, 1, 2, 3, bonus=5)
    wrapper = PickleableCoroutine(original_coro)

    dumped = pickle.dumps(wrapper)
    restored_wrapper = pickle.loads(dumped)

    result = await restored_wrapper
    assert result == 21


@pytest.mark.asyncio
async def test_independence_from_original():
    """Ensure the unpickled object creates a FRESH coroutine execution."""
    original_coro = global_simple_add(1, 1)
    wrapper = PickleableCoroutine(original_coro)

    dumped = pickle.dumps(wrapper)
    restored_wrapper = pickle.loads(dumped)

    # Run the restored one first
    res1 = await restored_wrapper
    # Run the original one second
    res2 = await wrapper

    assert res1 == 2
    assert res2 == 2


@pytest.mark.asyncio
async def test_validation_finished_coroutine():
    """Test passing a finished coroutine raises RuntimeError."""

    async def quick():
        return 1

    c = quick()
    await c  # Consume it

    with pytest.raises(RuntimeError):
        pickle.dumps(PickleableCoroutine(c))
