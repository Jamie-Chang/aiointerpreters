# Examples
## Sums
[sums.py](./sums.py) simple example demonstrating parallel speed up.

## Crawler Example
[crawl.py](./crawl.py) crawls wikepedia links using asyncio, the contents of the pages are then parsed and the number of links are counted using the `Runner`. 

This is one of the fastest ways to do this in Python, however your mileage may vary depending on the number of threads on your machine.
