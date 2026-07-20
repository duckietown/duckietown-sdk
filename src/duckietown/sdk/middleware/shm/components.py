"""Shared-memory WorldInput and WorldOutput components.

The components use the dtps-http latest-value transport. Given
``DTSHELL_SHM_PATH=/path/to/world_io``, the channels are:

* ``/path/to/world_io.world_input`` for engine-to-SDK WorldInput
    payloads;
* ``/path/to/world_io.world_output`` for SDK-to-engine WorldOutput
    payloads.

Each generic channel owns its memory map, advisory lock, and ``.p2c``
FIFO.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from dtps_http import RawData
from dtps_http.shm import ShmReader, ShmWriter
from duckietown_messages.simulation import WorldOutput as WorldOutputMessage

from duckietown.sdk.middleware.components import WorldInput, WorldOutput
from duckietown.sdk.middleware.timing_profiler import TimingProfiler

__all__ = ["ShmWorldInput", "ShmWorldOutput"]


_WORLD_INPUT_CHANNEL_SUFFIX = ".world_input"
_WORLD_OUTPUT_CHANNEL_SUFFIX = ".world_output"

_logger = logging.getLogger(__name__)


class ShmWorldInput(WorldInput):
    """Receive WorldInput snapshots through the common SHM transport."""

    _profiler: TimingProfiler
    _reader: ShmReader
    _shm_path: str

    def __init__(
        self,
        host: str,
        _: int,
        robot_name: str,
        __: str,
        **___: Any,  # noqa: ANN401
    ) -> None:
        """Initialize the SHM WorldInput subscriber."""
        super().__init__(host, robot_name)
        shm_path = os.environ.get("DTSHELL_SHM_PATH", "")
        if not shm_path:
            message = (
                "ShmWorldInput requires the DTSHELL_SHM_PATH environment "
                "variable."
            )
            raise RuntimeError(message)
        self._shm_path = shm_path + _WORLD_INPUT_CHANNEL_SUFFIX
        self._profiler = TimingProfiler(
            "SHM WorldInput Profiling Information",
        )
        self._reader = ShmReader(
            self._shm_path,
            self._on_payload,
            _logger.warning,
            _logger.error,
        )

    def enable_profiling(
        self,
        status: bool = True,  # noqa: FBT001, FBT002
    ) -> None:
        """Enable or disable SHM profiling."""
        self._profiler.enable(status=status)

    def print_profiling(self, logger: logging.Logger | None = None) -> None:
        """Log SHM profiling information."""
        self._profiler.log(logger or _logger)

    def _on_payload(self, payload: bytes) -> None:
        """Decode and dispatch one coherent WorldInput payload."""
        try:
            with self._profiler.profile("[shm-world-input]:deserialize"):
                raw_data = RawData(payload, "application/cbor")
                native_message = raw_data.get_as_native_object()
            if not isinstance(native_message, dict):
                _logger.warning(
                    "Ignoring non-dict WorldInput payload of type %s.",
                    type(native_message).__name__,
                )
                return
            with self._profiler.profile(
                "[shm-world-input]:callback-dispatch",
            ):
                self._callback(native_message)
        except Exception:
            _logger.exception("Error handling WorldInput from SHM.")

    def _start(self) -> None:
        """Start the generic reader and prime its latest payload."""
        self._reader.start()

    def _stop(self) -> None:
        """Stop the generic reader and release its resources."""
        self._reader.stop()

    def _unpack(self, message: Any) -> Any:  # noqa: ANN401
        self._remember_session_id(message)
        return message


class ShmWorldOutput(WorldOutput):
    """Publish WorldOutput snapshots through common SHM transport."""

    _profiler: TimingProfiler
    _shm_path: str
    _writer: ShmWriter

    def __init__(
        self,
        host: str,
        _: int,
        robot_name: str,
        __: str,
        **___: Any,  # noqa: ANN401
    ) -> None:
        """Initialize the SHM WorldOutput publisher."""
        super().__init__(host, robot_name)
        shm_path = os.environ.get("DTSHELL_SHM_PATH", "")
        if not shm_path:
            message = (
                "ShmWorldOutput requires the DTSHELL_SHM_PATH environment "
                "variable."
            )
            raise RuntimeError(message)
        self._shm_path = shm_path + _WORLD_OUTPUT_CHANNEL_SUFFIX
        self._profiler = TimingProfiler(
            "SHM WorldOutput Profiling Information",
        )
        self._writer = ShmWriter(
            self._shm_path,
            _logger.warning,
            _logger.error,
        )

    def enable_profiling(
        self,
        status: bool = True,  # noqa: FBT001, FBT002
    ) -> None:
        """Enable or disable SHM profiling."""
        self._profiler.enable(status=status)

    def print_profiling(self, logger: logging.Logger | None = None) -> None:
        """Log SHM profiling information."""
        self._profiler.log(logger or _logger)

    def _start(self) -> None:
        """Mark the publisher ready for lazy channel creation."""

    def _stop(self) -> None:
        """Release the generic writer's resources."""
        self._writer.close()

    def publish(self, data: Any) -> None:  # noqa: ANN401
        """Serialize and publish the most recent WorldOutput message."""
        if not self.has_started:
            message = "ShmWorldOutput not started. Cannot publish data."
            raise RuntimeError(message)
        with self._profiler.profile("[shm-world-output]:serialize"):
            if isinstance(data, WorldOutputMessage):
                raw_data = data.to_rawdata()
            else:
                raw_data = RawData.cbor_from_native_object(data)
        with self._profiler.profile("[shm-world-output]:publish"):
            self._writer.publish(raw_data.content)
