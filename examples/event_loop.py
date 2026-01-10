import asyncio

from aiointerpreters.event_loop import EventLoopRunner


async def main():
    async with EventLoopRunner(workers=5, batch_size=2) as runner:
        runner.create_task(asyncio.sleep(5))
        runner.create_task(asyncio.sleep(5))
        runner.create_task(asyncio.sleep(5))
        runner.create_task(asyncio.sleep(5))
        runner.create_task(asyncio.sleep(5))

        runner.create_batch([asyncio.sleep(5), asyncio.sleep(5)])


asyncio.run(main())
