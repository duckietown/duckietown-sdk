"""Regression tests for SHM transport remapping and growth."""

import os
import select
import tempfile
import unittest
from mmap import ACCESS_READ, mmap
from pathlib import Path
from threading import Event
from unittest.mock import patch

from dtps_http import RawData
from duckietown_messages.actuators import DifferentialPWM
from duckietown_messages.simulation import WorldEntityInput, WorldEntityOutput
from duckietown_messages.simulation import WorldInput as WorldInputMessage
from duckietown_messages.simulation import WorldOutput as WorldOutputMessage
from duckietown_messages.simulation.shm_layout import (
    SHM_HEADER_SIZE,
    default_shm_layout,
    pack_shm_header,
    resize_shm_layout,
    unpack_shm_header,
)

from duckietown.sdk.middleware.shm.components import (
    ShmWorldInput,
    ShmWorldOutput,
)


class ShmTransportTests(unittest.TestCase):
    def _make_shm_channel(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)

        shm_path = Path(temp_dir.name) / "world_io"
        layout = default_shm_layout()
        file_descriptor = os.open(shm_path, os.O_CREAT | os.O_RDWR, 0o666)
        try:
            os.ftruncate(file_descriptor, layout.total_size)
            memory_map_ = mmap(file_descriptor, layout.total_size)
            try:
                memory_map_[:SHM_HEADER_SIZE] = pack_shm_header(layout)
            finally:
                memory_map_.close()
        finally:
            os.close(file_descriptor)

        os.mkfifo(str(shm_path) + ".e2s", 0o666)
        os.mkfifo(str(shm_path) + ".s2e", 0o666)
        return shm_path

    def _open_fifo(self, path: Path) -> int:
        file_descriptor = os.open(path, os.O_RDWR)
        self.addCleanup(os.close, file_descriptor)
        return file_descriptor

    def _write_world_input(
        self,
        shm_path: Path,
        message: WorldInputMessage,
        layout,
    ) -> None:
        cbor_bytes = message.to_rawdata().content
        file_descriptor = os.open(shm_path, os.O_RDWR)
        try:
            os.ftruncate(file_descriptor, layout.total_size)
            memory_map_ = mmap(file_descriptor, layout.total_size)
            try:
                memory_map_[:SHM_HEADER_SIZE] = pack_shm_header(
                    layout,
                    world_input_length=0,
                    world_output_length=0,
                )
                memory_map_[
                    layout.world_input_offset : (
                        layout.world_input_offset + len(cbor_bytes)
                    )
                ] = cbor_bytes
                memory_map_[:SHM_HEADER_SIZE] = pack_shm_header(
                    layout,
                    world_input_length=len(cbor_bytes),
                    world_output_length=0,
                )
                memory_map_.flush()
            finally:
                memory_map_.close()
        finally:
            os.close(file_descriptor)

    def _make_large_world_output(self, min_bytes: int) -> WorldOutputMessage:
        entities: dict[str, WorldEntityOutput] = {}
        message = WorldOutputMessage(session_id=23, entities=entities)
        index = 0
        while len(message.to_rawdata().content) <= min_bytes:
            entities[f"vehicle_{index}"] = WorldEntityOutput(
                differential_pwm=DifferentialPWM(
                    left=0.25,
                    right=0.35,
                ),
            )
            message = WorldOutputMessage(
                session_id=23,
                entities=dict(entities),
            )
            index += 1
        return message

    def test_components_remap_when_engine_grows_input_capacity(self) -> None:
        shm_path = self._make_shm_channel()
        engine_to_sdk_fd = self._open_fifo(Path(str(shm_path) + ".e2s"))
        sdk_to_engine_fd = self._open_fifo(Path(str(shm_path) + ".s2e"))
        received_messages: list[dict] = []
        received_event = Event()

        with patch.dict(os.environ, {"DTSHELL_SHM_PATH": str(shm_path)}):
            world_input = ShmWorldInput(
                "127.0.0.1",
                7501,
                "map_0/vehicle_0",
                "",
            )
            world_output = ShmWorldOutput(
                "127.0.0.1",
                7501,
                "map_0/vehicle_0",
                "",
            )

            def _callback(message: dict) -> None:
                received_messages.append(message)
                received_event.set()

            world_input.attach(_callback)
            world_input.start()
            world_output.start()
            try:
                grown_layout = resize_shm_layout(
                    default_shm_layout(),
                    min_world_input_capacity=(
                        default_shm_layout().world_input_capacity * 2
                    ),
                )
                world_input_message = WorldInputMessage(
                    session_id=11,
                    entities={
                        "map_0/vehicle_0": WorldEntityInput(),
                    },
                )
                self._write_world_input(
                    shm_path,
                    world_input_message,
                    grown_layout,
                )
                os.write(engine_to_sdk_fd, b"\x01")

                self.assertTrue(received_event.wait(2.0))
                self.assertEqual(received_messages[0]["session_id"], 11)
                self.assertEqual(world_input._layout, grown_layout)

                world_output.publish(
                    WorldOutputMessage(
                        session_id=11,
                        entities={
                            "map_0/vehicle_0": WorldEntityOutput(
                                differential_pwm=DifferentialPWM(
                                    left=0.1,
                                    right=0.2,
                                ),
                            ),
                        },
                    ),
                )
                ready, _, _ = select.select([sdk_to_engine_fd], [], [], 1.0)
                self.assertTrue(ready)
                self.assertEqual(os.read(sdk_to_engine_fd, 1), b"\x01")

                file_descriptor = os.open(shm_path, os.O_RDONLY)
                try:
                    memory_map_ = mmap(
                        file_descriptor,
                        grown_layout.total_size,
                        access=ACCESS_READ,
                    )
                    try:
                        layout, _, world_output_length = unpack_shm_header(
                            bytes(memory_map_[:SHM_HEADER_SIZE]),
                        )
                        self.assertEqual(layout, grown_layout)
                        self.assertGreater(world_output_length, 0)
                        raw_data = RawData(
                            bytes(
                                memory_map_[
                                    layout.world_output_offset : (
                                        layout.world_output_offset
                                        + world_output_length
                                    )
                                ],
                            ),
                            "application/cbor",
                        )
                        world_output_message = WorldOutputMessage.from_rawdata(
                            raw_data,
                        )
                    finally:
                        memory_map_.close()
                finally:
                    os.close(file_descriptor)

                self.assertEqual(world_output._layout, grown_layout)
                self.assertEqual(world_output_message.session_id, 11)
                self.assertIn("map_0/vehicle_0", world_output_message.entities)
            finally:
                if world_input.has_started:
                    world_input.stop()
                if world_output.has_started:
                    world_output.stop()

    def test_world_output_grows_layout_for_large_payload(self) -> None:
        shm_path = self._make_shm_channel()
        sdk_to_engine_fd = self._open_fifo(Path(str(shm_path) + ".s2e"))
        default_layout = default_shm_layout()

        with patch.dict(os.environ, {"DTSHELL_SHM_PATH": str(shm_path)}):
            world_output = ShmWorldOutput(
                "127.0.0.1",
                7501,
                "map_0/vehicle_0",
                "",
            )
            world_output.start()
            try:
                large_message = self._make_large_world_output(
                    default_layout.world_output_capacity,
                )
                large_payload = large_message.to_rawdata().content
                self.assertGreater(
                    len(large_payload),
                    default_layout.world_output_capacity,
                )

                world_output.publish(large_message)
                ready, _, _ = select.select([sdk_to_engine_fd], [], [], 1.0)
                self.assertTrue(ready)
                self.assertEqual(os.read(sdk_to_engine_fd, 1), b"\x01")

                file_descriptor = os.open(shm_path, os.O_RDONLY)
                try:
                    grown_size = os.fstat(file_descriptor).st_size
                    memory_map_ = mmap(
                        file_descriptor,
                        grown_size,
                        access=ACCESS_READ,
                    )
                    try:
                        layout, _, world_output_length = unpack_shm_header(
                            bytes(memory_map_[:SHM_HEADER_SIZE]),
                        )
                        self.assertGreater(
                            layout.world_output_capacity,
                            default_layout.world_output_capacity,
                        )
                        self.assertEqual(
                            world_output_length,
                            len(large_payload),
                        )
                        raw_data = RawData(
                            bytes(
                                memory_map_[
                                    layout.world_output_offset : (
                                        layout.world_output_offset
                                        + world_output_length
                                    )
                                ],
                            ),
                            "application/cbor",
                        )
                        decoded_message = WorldOutputMessage.from_rawdata(
                            raw_data,
                        )
                    finally:
                        memory_map_.close()
                finally:
                    os.close(file_descriptor)

                self.assertEqual(world_output._layout, layout)
                self.assertEqual(
                    set(decoded_message.entities),
                    set(large_message.entities),
                )
            finally:
                if world_output.has_started:
                    world_output.stop()


if __name__ == "__main__":
    unittest.main()
