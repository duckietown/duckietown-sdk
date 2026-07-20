"""Integration tests for the SDK shared-memory world channels."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import patch

from dtps_http import RawData
from dtps_http.shm import ShmReader, ShmWriter
from duckietown_messages.actuators import DifferentialPWM
from duckietown_messages.simulation import WorldEntityInput, WorldEntityOutput
from duckietown_messages.simulation import WorldInput as WorldInputMessage
from duckietown_messages.simulation import WorldOutput as WorldOutputMessage

from duckietown.sdk.middleware.shm.components import (
    ShmWorldInput,
    ShmWorldOutput,
)


class ShmTransportTests(unittest.TestCase):
    """Verify SDK world-I/O wrappers use generic SHM channels."""

    def _make_channel_base(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return Path(temp_dir.name) / "world_io"

    def test_world_input_uses_generic_channel(self) -> None:
        """Deliver a world input message through the generic channel."""
        channel_base = self._make_channel_base()
        expected_session_id = 11
        received_messages: list[dict] = []
        received_event = Event()
        writer = ShmWriter(
            str(channel_base) + ".world_input",
            lambda _: None,
            lambda _: None,
        )

        with patch.dict(
            os.environ,
            {"DTSHELL_SHM_PATH": str(channel_base)},
        ):
            world_input = ShmWorldInput(
                "127.0.0.1",
                7501,
                "map_0/vehicle_0",
                "",
            )

            def on_world_input(message: dict) -> None:
                received_messages.append(message)
                received_event.set()

            world_input.attach(on_world_input)
            world_input.start()
            try:
                message = WorldInputMessage(
                    session_id=expected_session_id,
                    entities={
                        "map_0/vehicle_0": WorldEntityInput(),
                    },
                )
                writer.publish(message.to_rawdata().content)

                assert received_event.wait(2.0)  # noqa: S101
                assert (  # noqa: S101
                    received_messages[0]["session_id"] == expected_session_id
                )
                assert world_input.current_session_id == expected_session_id  # noqa: S101
            finally:
                world_input.stop()
                writer.close()

    def test_world_output_uses_generic_channel(self) -> None:
        """Deliver a world output through the generic channel."""
        channel_base = self._make_channel_base()
        expected_session_id = 23
        received_payloads: list[bytes] = []
        received_event = Event()

        def on_payload(payload: bytes) -> None:
            received_payloads.append(payload)
            received_event.set()

        reader = ShmReader(
            str(channel_base) + ".world_output",
            on_payload,
            lambda _: None,
            lambda _: None,
        )
        reader.start()
        with patch.dict(
            os.environ,
            {"DTSHELL_SHM_PATH": str(channel_base)},
        ):
            world_output = ShmWorldOutput(
                "127.0.0.1",
                7501,
                "map_0/vehicle_0",
                "",
            )
            world_output.start()
            try:
                world_output.publish(
                    WorldOutputMessage(
                        session_id=expected_session_id,
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

                assert received_event.wait(2.0)  # noqa: S101
                raw_data = RawData(
                    received_payloads[0],
                    "application/cbor",
                )
                received_message = WorldOutputMessage.from_rawdata(raw_data)
                assert received_message.session_id == expected_session_id  # noqa: S101
                assert "map_0/vehicle_0" in received_message.entities  # noqa: S101
            finally:
                world_output.stop()
                reader.stop()


if __name__ == "__main__":
    unittest.main()
