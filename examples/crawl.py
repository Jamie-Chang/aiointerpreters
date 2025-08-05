import asyncio
import time
from contextlib import contextmanager
from typing import cast
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from httpx import AsyncClient

from aiointerpreters.runner import Runner

BASE_WIKI_URL = "https://en.wikipedia.org"
urls = [
    "https://en.wikipedia.org/wiki/Reference_counting",
    "https://en.wikipedia.org/wiki/Bug_tracker",
    "https://en.wikipedia.org/wiki/API",
    "https://en.wikipedia.org/wiki/Python_syntax_and_semantics",
    "https://en.wikipedia.org/wiki/Neuromorphic_computing",
    "https://en.wikipedia.org/wiki/Package_management_system",
    "https://en.wikipedia.org/wiki/C11_(C_standard_revision)",
    "https://en.wikipedia.org/wiki/Free_software",
    "https://en.wikipedia.org/wiki/WinBUGS",
    "https://en.wikipedia.org/wiki/Arbitrary-precision_arithmetic",
    "https://en.wikipedia.org/wiki/Differentiable_function",
    "https://en.wikipedia.org/wiki/Rational_number",
    "https://en.wikipedia.org/wiki/Web_browser",
    "https://en.wikipedia.org/wiki/Industrial_Light_%26_Magic",
    "https://en.wikipedia.org/wiki/Pattern_recognition",
    "https://en.wikipedia.org/wiki/OxMetrics",
    "https://en.wikipedia.org/wiki/LIMDEP",
    "https://en.wikipedia.org/wiki/Combinatorics",
    "https://en.wikipedia.org/wiki/Objective-C",
    "https://en.wikipedia.org/wiki/Name_resolution_(programming_languages)",
]


def parse(content: bytes) -> int:
    soup = BeautifulSoup(content, "html.parser")
    urls = (
        urljoin(BASE_WIKI_URL, cast(str, a_tag.get("href", "")))
        for a_tag in soup.select("div#bodyContent a[href]")
    )
    return sum(1 for _ in urls)


@contextmanager
def timer(message: str):
    start = time.perf_counter()
    try:
        yield
    finally:
        print(f"{message} {time.perf_counter() - start} s elapsed")


async def run_all(urls: list[str]) -> None:
    with timer("ran asyncio"):
        async with AsyncClient(timeout=30) as client:
            with Runner(workers=12).start() as executor:
                semaphore = asyncio.Semaphore(200)
                async with asyncio.TaskGroup() as tg:
                    for url in urls:
                        await semaphore.acquire()
                        tg.create_task(
                            fetch_and_count(executor, client, url),
                            name=url,
                        ).add_done_callback(lambda _: semaphore.release())


async def fetch_and_count(runner: Runner, client: AsyncClient, url: str) -> None:
    response = await client.get(url)
    response.raise_for_status()
    links = await runner.run(parse, content=response.content)
    print(f"Found {url = } {links = }")


if __name__ == "__main__":
    asyncio.run(run_all(urls))
