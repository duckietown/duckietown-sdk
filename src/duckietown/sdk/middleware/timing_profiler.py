"""Lightweight timing profiler."""

import logging
import time
from collections import defaultdict, deque
from statistics import median, quantiles
from types import TracebackType

_HISTORY_LENGTH = 200
TABLE_SEPARATOR = "+-{0}-+-{1}-+-{2}-+-{3}-+-{4}-+-{5}-+\n"
TABLE_HEADER_FMT = "| {0} | {1} | {2} | {3} | {4} | {5} |\n"
TABLE_ROW_FMT = (
    "| {key} | {count} | {duration} | {median} | {p95} | {frequency} |\n"
)


class TimingProfiler:
    """Track lifetime means and bounded recent latency distributions."""

    _buffer: dict[str, float]
    _count: defaultdict[str, int]
    _data: defaultdict[str, float]
    _history: dict[str, deque[float]]
    _enabled: bool
    _title: str

    class ProfilingContext:
        """Profiling context manager."""

        _key: str
        _profiler: "TimingProfiler"

        def __init__(self, profiler: "TimingProfiler", key: str) -> None:
            """Initialize the profiling context."""
            self._profiler = profiler
            self._key = key

        def __enter__(self) -> None:
            """Start timing when entering the context."""
            self._profiler.tick(self._key)

        def __exit__(
            self,
            _: type[BaseException] | None,
            __: BaseException | None,
            ___: TracebackType | None,
        ) -> None:
            """Stop timing when exiting the context."""
            self._profiler.tock(self._key)

    def __init__(self, title: str) -> None:
        """Initialize the profiler with a log title."""
        self._title = title
        self._enabled = False
        self._buffer = {}
        self._count = defaultdict(int)
        self._data = defaultdict(float)
        self._history = {}

    def enable(self, *, status: bool = True) -> None:
        """Enable or disable profiling."""
        self._enabled = status

    def profile(self, key: str) -> ProfilingContext:
        """Return a profiling context."""
        return self.ProfilingContext(self, key)

    def observe(self, key: str, duration_ms: float) -> None:
        """Record an externally measured duration."""
        if not self._enabled:
            return
        self._data[key] += duration_ms
        self._count[key] += 1
        if key not in self._history:
            self._history[key] = deque(maxlen=_HISTORY_LENGTH)
        self._history[key].append(duration_ms)

    def tick(self, key: str) -> None:
        """Start measuring *key*."""
        if not self._enabled:
            return
        self._buffer[key] = time.perf_counter() * 1000

    def tock(self, key: str) -> None:
        """Stop measuring *key*."""
        if not self._enabled:
            return
        tick = self._buffer.pop(key, None)
        if tick is None:
            return
        self.observe(key, time.perf_counter() * 1000 - tick)

    def log(self, logger: logging.Logger) -> None:
        """Log profiling information."""
        if not self._enabled:
            return
        if not self._count:
            logger.info("\n%s:\n(no samples)\n", self._title)
            return
        headers = (
            "Key",
            "# Calls",
            "Mean (ms)",
            "Median (ms)",
            "p95 (ms)",
            "Freq (Hz)",
        )
        column_sizes = [len(header) for header in headers]
        rows = []
        for key in sorted(self._count):
            cumulative_duration = self._data[key]
            count = self._count[key]
            average_duration = cumulative_duration / float(count)
            recent = list(self._history[key])
            recent_median = median(recent)
            recent_p95 = recent[0]
            if len(recent) > 1:
                percentiles = quantiles(recent, n=100, method="inclusive")
                recent_p95 = percentiles[94]
            average_frequency = (
                "inf"
                if average_duration <= 0
                else round(1000 / average_duration, 1)
            )
            row = (
                key,
                str(count),
                str(round(average_duration, 2)),
                str(round(recent_median, 2)),
                str(round(recent_p95, 2)),
                str(average_frequency),
            )
            for column, value in enumerate(row):
                column_sizes[column] = max(column_sizes[column], len(value))
            rows.append(row)
        separator = TABLE_SEPARATOR.format(
            *("-" * width for width in column_sizes),
        )
        aligned_headers = [
            header.center(width)
            for header, width in zip(headers, column_sizes, strict=True)
        ]
        aligned_headers[0] = headers[0].ljust(column_sizes[0])
        table = separator
        table += TABLE_HEADER_FMT.format(*aligned_headers)
        table += separator
        for row in rows:
            table += TABLE_ROW_FMT.format(
                key=row[0].ljust(column_sizes[0]),
                count=row[1].rjust(column_sizes[1]),
                duration=row[2].rjust(column_sizes[2]),
                median=row[3].rjust(column_sizes[3]),
                p95=row[4].rjust(column_sizes[4]),
                frequency=row[5].rjust(column_sizes[5]),
            )
        table += separator
        table += (
            "Mean/frequency: all samples; median/p95: latest "
            f"{_HISTORY_LENGTH} samples.\n"
        )
        logger.info("\n%s:\n%s\n", self._title, table)
