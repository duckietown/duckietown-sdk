"""Shared-memory WorldInput and WorldOutput components.

These components replace the DTPS WebSocket round-trip with a direct
mmap + named-FIFO pathway, removing all asyncio scheduling overhead from
the ``[world]:wait-for-outputs`` timer.

The shared-memory layout and FIFO naming convention mirror the
engine-side ``ShmDataConnector``:

Layout of the shared-memory file
--------------------------------
Offset  Size  Field
------  ----  -----
0       4     world_input_length   - uint32LE: byte length of the
                                     WorldInput CBOR blob
4       4     world_output_length  - uint32LE: byte length of the
                                     WorldOutput CBOR blob
8       N     world_input_data     - WorldInput CBOR (N =
                                     _WORLD_INPUT_MAX_BYTES)
8+N     M     world_output_data    - WorldOutput CBOR (M =
                                     _WORLD_OUTPUT_MAX_BYTES)

Total file size: 8 + N + M  (default: 8 + 65536 + 1024 = 66568 bytes)

Signalling
----------
Two named FIFOs live in the same directory as the SHM file:
  <shm_path>.e2s - engine writes 1 byte after WorldInput is ready
  <shm_path>.s2e - SDK writes 1 byte after WorldOutput is ready

Usage (set DTSHELL_SHM_PATH in the environment)
------------------------------------------
export DTSHELL_SHM_PATH=/path/to/file
python -c "from duckietown.sdk.middleware.shm import (
           ShmWorldInput, ShmWorldOutput)"
"""

__all__ = ["ShmWorldInput", "ShmWorldOutput"]

import logging
import os
import struct
from mmap import mmap
from threading import Thread
from typing import Any

from dtps_http import RawData
from duckietown_messages.simulation import WorldInput as WorldInputMessage
from duckietown_messages.simulation import WorldOutput as WorldOutputMessage

from duckietown.sdk.middleware.components import WorldInput, WorldOutput

# Header: two uint32LE values (world_input_length, world_output_length).
_HEADER_FMT = "<II"
_HEADER_SIZE = struct.calcsize(_HEADER_FMT)  # 8 bytes
# Maximum payload sizes.
_WORLD_INPUT_MAX_BYTES = 65536  # 64 KB - plenty for JPEG camera frame
_WORLD_OUTPUT_MAX_BYTES = 1024  # 1 KB - WorldOutput is ~92 bytes CBOR
_TOTAL_SHM_SIZE = (
    _HEADER_SIZE + _WORLD_INPUT_MAX_BYTES + _WORLD_OUTPUT_MAX_BYTES
)
# Offsets into the memory map buffer.
_WORLD_INPUT_OFFSET = _HEADER_SIZE
_WORLD_OUTPUT_OFFSET = _HEADER_SIZE + _WORLD_INPUT_MAX_BYTES

_logger = logging.getLogger(__name__)


class ShmWorldInput(WorldInput):
    """Shared-memory world-input subscriber.

    Spawns a background thread that blocks on the engine to SDK FIFO.
    When the engine signals a new WorldInput, the thread:
    1. Reads world_input_length from the header.
    2. Reads world_input_length bytes from the world_input_data region.
    3. Deserializes the CBOR to a ``WorldInput`` dict.
    4. Calls ``self._callback(message)`` (inherited from
       GenericSubscriber).
    """

    _engine_to_sdk_file_descriptor: int | None
    _engine_to_sdk_path: str
    _memory_map: mmap | None
    _running: bool
    _sdk_to_engine_file_descriptor: int | None
    _sdk_to_engine_path: str
    _shm_path: str
    _thread: Thread

    def __init__(
        self,
        host: str,
        _: int,
        robot_name: str,
        __: str,
        **___: Any,  # noqa: ANN401
    ) -> None:
        """Initialise the SHM world-input subscriber."""
        super().__init__(host, robot_name)
        shm_path = os.environ.get("DTSHELL_SHM_PATH", "")
        if not shm_path:
            message = (
                "ShmWorldInput requires the DTSHELL_SHM_PATH environment "
                "variable."
            )
            raise RuntimeError(message)
        self._shm_path = shm_path
        self._engine_to_sdk_path = shm_path + ".e2s"
        self._sdk_to_engine_path = shm_path + ".s2e"
        self._memory_map = None
        self._engine_to_sdk_file_descriptor = None
        self._sdk_to_engine_file_descriptor = None
        self._running = False
        self._thread = Thread(
            target=self._reader_loop,
            daemon=True,
            name="ShmWorldInput-reader",
        )

    def _start(self) -> None:
        """Open the SHM file and FIFOs, then start the reader thread."""
        file_descriptor = os.open(self._shm_path, os.O_RDWR)
        self._memory_map = mmap(file_descriptor, _TOTAL_SHM_SIZE)
        os.close(file_descriptor)
        # Open FIFOs in O_RDWR so we hold both ends (avoids ENXIO when
        # the other side hasn't opened yet) and so the file descriptor
        # stays valid.
        self._engine_to_sdk_file_descriptor = os.open(
            self._engine_to_sdk_path,
            os.O_RDWR,
        )
        self._sdk_to_engine_file_descriptor = os.open(
            self._sdk_to_engine_path,
            os.O_RDWR,
        )
        self._running = True
        self._thread.start()

    def _stop(self) -> None:
        """Signal the reader thread to exit."""
        self._running = False
        # Unblock the reader if it is blocked on os.read.
        # Writing a byte to the read end will wake it.
        try:
            if self._engine_to_sdk_file_descriptor is not None:
                os.write(self._engine_to_sdk_file_descriptor, b"\x00")
        except OSError:
            pass

    def _unpack(self, message: Any) -> Any:  # noqa: ANN401
        self._remember_session_id(message)
        return message

    def _reader_loop(self) -> None:  # noqa: C901
        """Read WorldInput from memory map and call _callback."""
        if (
            self._engine_to_sdk_file_descriptor is None
            or self._memory_map is None
        ):  # pragma: no cover
            message = "_reader_loop called before _start()"
            raise RuntimeError(message)
        fifo_file_descriptor = self._engine_to_sdk_file_descriptor
        memory_map_ = self._memory_map
        while self._running:
            try:
                signal = os.read(fifo_file_descriptor, 1)
            except OSError:
                if not self._running:
                    return
                _logger.exception("Engine to SDK FIFO read error.")
                continue
            if not signal:
                continue
            # Ignore the stop-signal byte (value == 0).
            if signal == b"\x00":
                if not self._running:
                    return
                continue
            # Read WorldInput from the memory map.
            try:
                header_bytes = memory_map_[:_HEADER_SIZE]
                world_input_length, _ = struct.unpack(
                    _HEADER_FMT,
                    header_bytes,
                )
                if world_input_length == 0:
                    continue
                if world_input_length > _WORLD_INPUT_MAX_BYTES:
                    _logger.warning(
                        "world_input_length=%d exceeds "
                        "WORLD_INPUT_MAX_BYTES=%d; skipping.",
                        world_input_length,
                        _WORLD_INPUT_MAX_BYTES,
                    )
                    continue
                cbor_bytes = bytes(
                    memory_map_[
                        _WORLD_INPUT_OFFSET : (
                            _WORLD_INPUT_OFFSET + world_input_length
                        )
                    ],
                )
                latest_header_bytes = memory_map_[:_HEADER_SIZE]
                latest_world_input_length, _ = struct.unpack(
                    _HEADER_FMT,
                    latest_header_bytes,
                )
                if latest_world_input_length != world_input_length:
                    _logger.debug(
                        "Ignoring unstable WorldInput snapshot: "
                        "length changed from %d to %d while reading.",
                        world_input_length,
                        latest_world_input_length,
                    )
                    continue
            except Exception:
                _logger.exception("Error reading WorldInput from SHM.")
                continue
            # Deserialize
            try:
                raw_data = RawData(cbor_bytes, "application/cbor")
                world_input_message = WorldInputMessage.from_rawdata(raw_data)
                message = world_input_message.model_dump()
                self._callback(message)
            except Exception:
                _logger.exception("Error deserializing WorldInput.")


class ShmWorldOutput(WorldOutput):
    """Shared-memory world-output publisher.

    ``publish(data)`` is called by the vehicle's ``step()`` method.  It
    serializes the ``WorldOutput`` message to CBOR, writes it to the
    shared memory map and signals the engine via the SDK to engine FIFO.
    """

    _memory_map: mmap | None
    _sdk_to_engine_file_descriptor: int | None
    _sdk_to_engine_path: str
    _shm_path: str

    def __init__(
        self,
        host: str,
        _: int,
        robot_name: str,
        __: str,
        **___: Any,  # noqa: ANN401
    ) -> None:
        """Initialise the SHM world-output publisher."""
        super().__init__(host, robot_name)
        shm_path = os.environ.get("DTSHELL_SHM_PATH", "")
        if not shm_path:
            message = (
                "ShmWorldOutput requires the DTSHELL_SHM_PATH environment "
                "variable."
            )
            raise RuntimeError(message)
        self._shm_path = shm_path
        self._sdk_to_engine_path = shm_path + ".s2e"
        self._memory_map = None
        self._sdk_to_engine_file_descriptor = None

    def _start(self) -> None:
        """Open the SHM file and the SDK to engine FIFO."""
        file_descriptor = os.open(self._shm_path, os.O_RDWR)
        self._memory_map = mmap(file_descriptor, _TOTAL_SHM_SIZE)
        os.close(file_descriptor)
        self._sdk_to_engine_file_descriptor = os.open(
            self._sdk_to_engine_path,
            os.O_RDWR,
        )

    def _stop(self) -> None:
        """Close handles."""
        try:
            if self._memory_map is not None:
                self._memory_map.close()
                self._memory_map = None
        except OSError:
            pass
        try:
            if self._sdk_to_engine_file_descriptor is not None:
                os.close(self._sdk_to_engine_file_descriptor)
                self._sdk_to_engine_file_descriptor = None
        except OSError:
            pass

    def publish(self, data: Any) -> None:  # noqa: ANN401
        """Serialize *data* and write it to the SHM buffer."""
        if (
            self._memory_map is None
            or self._sdk_to_engine_file_descriptor is None
        ):
            message = "ShmWorldOutput not started. Cannot publish data."
            raise RuntimeError(message)
        if isinstance(data, WorldOutputMessage):
            raw_data = data.to_rawdata()
        else:
            raw_data = RawData.cbor_from_native_object(data)
        cbor_bytes: bytes = raw_data.content
        world_output_length = len(cbor_bytes)
        if world_output_length > _WORLD_OUTPUT_MAX_BYTES:
            _logger.warning(
                "WorldOutput CBOR (%d bytes) exceeds SHM buffer (%d bytes); "
                "dropping.",
                world_output_length,
                _WORLD_OUTPUT_MAX_BYTES,
            )
            return
        # Write the payload first and publish the length only after the
        # bytes are in place so the engine never sees a fresh size for a
        # stale buffer.
        memory_map_ = self._memory_map
        memory_map_[
            _WORLD_OUTPUT_OFFSET : (_WORLD_OUTPUT_OFFSET + world_output_length)
        ] = cbor_bytes
        memory_map_[4:8] = struct.pack("<I", world_output_length)
        memory_map_.flush()
        # Signal the engine.
        try:
            os.write(self._sdk_to_engine_file_descriptor, b"\x01")
        except OSError:
            _logger.exception(
                "Failed to signal engine via SDK to engine FIFO.",
            )
