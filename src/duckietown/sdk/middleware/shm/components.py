"""Shared-memory WorldInput and WorldOutput components.

These components replace the DTPS WebSocket round-trip with a direct
mmap + named-FIFO pathway, removing all asyncio scheduling overhead from
the ``[world]:wait-for-outputs`` timer.

The shared-memory layout and FIFO naming convention mirror the
engine-side ``ShmDataConnector``:

Layout of the shared-memory file
--------------------------------
Offset    Size  Field
------    ----  -----
0         4     magic                 - ASCII "DMIO"
4         4     version               - uint32LE layout version
8         4     world_input_capacity  - uint32LE maximum input bytes
12        4     world_output_capacity - uint32LE maximum output bytes
16        4     world_input_length    - uint32LE current input byte
                                        length
20        4     world_output_length   - uint32LE current output byte
                                        length
24        N     world_input_data      - WorldInput CBOR
24 + N    M     world_output_data     - WorldOutput CBOR

The file can grow when the active map produces larger aggregated world
messages than the current capacities can hold.

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
from mmap import mmap
from pathlib import Path
from threading import Thread, current_thread
from typing import Any

from dtps_http import RawData
from duckietown_messages.simulation import WorldOutput as WorldOutputMessage
from duckietown_messages.simulation.shm_layout import (
    SHM_HEADER_SIZE,
    ShmLayout,
    default_shm_layout,
    pack_shm_header,
    resize_shm_layout,
    unpack_shm_header,
)

from duckietown.sdk.middleware.components import WorldInput, WorldOutput

_DEFAULT_LAYOUT = default_shm_layout()

_logger = logging.getLogger(__name__)


def _load_initial_layout(
    shm_path: str,
    fallback_layout: ShmLayout,
) -> ShmLayout:
    shm_file = Path(shm_path)
    if (not shm_file.exists()) or shm_file.stat().st_size < SHM_HEADER_SIZE:
        return fallback_layout
    with shm_file.open("rb") as file:
        header_bytes = file.read(SHM_HEADER_SIZE)
    layout, _, _ = unpack_shm_header(
        header_bytes,
        fallback_layout=fallback_layout,
    )
    if shm_file.stat().st_size >= layout.total_size:
        return layout
    return fallback_layout


def _open_memory_map(shm_path: str, size: int) -> mmap:
    file_descriptor = os.open(shm_path, os.O_RDWR)
    try:
        return mmap(file_descriptor, size)
    finally:
        os.close(file_descriptor)


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
    _layout: ShmLayout

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
        self._layout = _DEFAULT_LAYOUT
        self._thread = Thread(
            target=self._reader_loop,
            daemon=True,
            name="ShmWorldInput-reader",
        )

    def _sync_layout(self) -> tuple[ShmLayout, int, int]:
        memory_map_ = self._memory_map
        if memory_map_ is None:  # pragma: no cover
            message = "SHM memory map not initialized."
            raise RuntimeError(message)
        layout, world_input_length, world_output_length = unpack_shm_header(
            bytes(memory_map_[:SHM_HEADER_SIZE]),
            fallback_layout=self._layout,
        )
        if layout.total_size > self._layout.total_size:
            memory_map_.close()
            self._memory_map = _open_memory_map(
                self._shm_path,
                layout.total_size,
            )
            memory_map_ = self._memory_map
            if memory_map_ is None:  # pragma: no cover
                message = "SHM remap failed."
                raise RuntimeError(message)
            layout, world_input_length, world_output_length = (
                unpack_shm_header(
                    bytes(memory_map_[:SHM_HEADER_SIZE]),
                    fallback_layout=layout,
                )
            )
        if layout.total_size >= self._layout.total_size:
            self._layout = layout
        return self._layout, world_input_length, world_output_length

    def _close_handles(self) -> None:
        try:
            if self._memory_map is not None:
                self._memory_map.close()
                self._memory_map = None
        except OSError:
            pass
        try:
            if self._engine_to_sdk_file_descriptor is not None:
                os.close(self._engine_to_sdk_file_descriptor)
                self._engine_to_sdk_file_descriptor = None
        except OSError:
            pass
        try:
            if self._sdk_to_engine_file_descriptor is not None:
                os.close(self._sdk_to_engine_file_descriptor)
                self._sdk_to_engine_file_descriptor = None
        except OSError:
            pass

    def _read_world_input_bytes(self) -> bytes | None:
        layout, world_input_length, _ = self._sync_layout()
        if world_input_length == 0:
            return None
        if world_input_length > layout.world_input_capacity:
            _logger.warning(
                "world_input_length=%d exceeds world_input_capacity=%d; "
                "skipping.",
                world_input_length,
                layout.world_input_capacity,
            )
            return None
        memory_map_ = self._memory_map
        if memory_map_ is None:  # pragma: no cover
            _logger.warning(
                "Ignoring engine to SDK signal with no active memory map.",
            )
            return None
        cbor_bytes = bytes(
            memory_map_[
                layout.world_input_offset : (
                    layout.world_input_offset + world_input_length
                )
            ],
        )
        latest_layout, latest_world_input_length, _ = self._sync_layout()
        if latest_world_input_length != world_input_length:
            _logger.debug(
                "Ignoring unstable WorldInput snapshot: length changed "
                "from %d to %d while reading.",
                world_input_length,
                latest_world_input_length,
            )
            return None
        if latest_layout.world_input_capacity != layout.world_input_capacity:
            _logger.debug(
                "Ignoring unstable WorldInput snapshot: input capacity "
                "changed from %d to %d while reading.",
                layout.world_input_capacity,
                latest_layout.world_input_capacity,
            )
            return None
        return cbor_bytes

    def _start(self) -> None:
        """Open the SHM file and FIFOs, then start the reader thread."""
        self._layout = _load_initial_layout(self._shm_path, self._layout)
        self._memory_map = _open_memory_map(
            self._shm_path,
            self._layout.total_size,
        )
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
        if self._thread.is_alive() and current_thread() is not self._thread:
            self._thread.join(timeout=1)
        self._close_handles()

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
            if signal == b"\x00":
                if not self._running:
                    return
                continue
            # Read WorldInput from the memory map.
            try:
                cbor_bytes = self._read_world_input_bytes()
                if cbor_bytes is None:
                    continue
            except Exception:
                _logger.exception("Error reading WorldInput from SHM.")
                continue
            # Deserialize
            try:
                raw_data = RawData(cbor_bytes, "application/cbor")
                native_message = raw_data.get_as_native_object()
                if not isinstance(native_message, dict):
                    _logger.warning(
                        "Ignoring non-dict WorldInput payload of type %s.",
                        type(native_message).__name__,
                    )
                    continue
                self._callback(native_message)
            except Exception:
                _logger.exception("Error deserializing WorldInput.")


class ShmWorldOutput(WorldOutput):
    """Shared-memory world-output publisher.

    ``publish(data)`` serializes the environment-owned ``WorldOutput``
    message to CBOR, writes it to the shared memory map, and signals the
    engine via the SDK to engine FIFO.
    """

    _memory_map: mmap | None
    _sdk_to_engine_file_descriptor: int | None
    _sdk_to_engine_path: str
    _shm_path: str
    _layout: ShmLayout

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
        self._layout = _DEFAULT_LAYOUT

    def _sync_layout(self) -> tuple[ShmLayout, int, int]:
        memory_map_ = self._memory_map
        if memory_map_ is None:  # pragma: no cover
            message = "SHM memory map not initialized."
            raise RuntimeError(message)
        layout, world_input_length, world_output_length = unpack_shm_header(
            bytes(memory_map_[:SHM_HEADER_SIZE]),
            fallback_layout=self._layout,
        )
        if layout.total_size > self._layout.total_size:
            memory_map_.close()
            self._memory_map = _open_memory_map(
                self._shm_path,
                layout.total_size,
            )
            memory_map_ = self._memory_map
            if memory_map_ is None:  # pragma: no cover
                message = "SHM remap failed."
                raise RuntimeError(message)
            layout, world_input_length, world_output_length = (
                unpack_shm_header(
                    bytes(memory_map_[:SHM_HEADER_SIZE]),
                    fallback_layout=layout,
                )
            )
        if layout.total_size >= self._layout.total_size:
            self._layout = layout
        return self._layout, world_input_length, world_output_length

    def _resize_layout(
        self,
        layout: ShmLayout,
        *,
        world_input_length: int,
    ) -> None:
        memory_map_ = self._memory_map
        if memory_map_ is not None:
            memory_map_.close()
        file_descriptor = os.open(self._shm_path, os.O_RDWR)
        try:
            os.ftruncate(file_descriptor, layout.total_size)
            self._memory_map = mmap(file_descriptor, layout.total_size)
        finally:
            os.close(file_descriptor)
        self._layout = layout
        memory_map_ = self._memory_map
        if memory_map_ is None:  # pragma: no cover
            message = "SHM memory map not initialized."
            raise RuntimeError(message)
        memory_map_[:SHM_HEADER_SIZE] = pack_shm_header(
            self._layout,
            world_input_length=world_input_length,
            world_output_length=0,
        )

    def _start(self) -> None:
        """Open the SHM file and the SDK to engine FIFO."""
        self._layout = _load_initial_layout(self._shm_path, self._layout)
        self._memory_map = _open_memory_map(
            self._shm_path,
            self._layout.total_size,
        )
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
        layout, world_input_length, _ = self._sync_layout()
        target_layout = resize_shm_layout(
            layout,
            min_world_output_capacity=world_output_length,
        )
        if target_layout != layout:
            self._resize_layout(
                target_layout,
                world_input_length=world_input_length,
            )
        # Write the payload first and publish the length only after the
        # bytes are in place so the engine never sees a fresh size for a
        # stale buffer.
        memory_map_ = self._memory_map
        if memory_map_ is None:  # pragma: no cover
            message = "SHM memory map not initialized."
            raise RuntimeError(message)
        memory_map_[:SHM_HEADER_SIZE] = pack_shm_header(
            self._layout,
            world_input_length=world_input_length,
            world_output_length=0,
        )
        memory_map_[
            self._layout.world_output_offset : (
                self._layout.world_output_offset + world_output_length
            )
        ] = cbor_bytes
        memory_map_[:SHM_HEADER_SIZE] = pack_shm_header(
            self._layout,
            world_input_length=world_input_length,
            world_output_length=world_output_length,
        )
        # Signal the engine.
        try:
            os.write(self._sdk_to_engine_file_descriptor, b"\x01")
        except OSError:
            _logger.exception(
                "Failed to signal engine via SDK to engine FIFO.",
            )
