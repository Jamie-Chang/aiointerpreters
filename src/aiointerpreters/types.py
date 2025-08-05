from concurrent.interpreters import Queue

"""
Useful type to annotate values that can be passed to interpreters.
"""
type Shareable = (
    str | bytes | int | float | bool | None | tuple[Shareable, ...] | Queue | memoryview
)
