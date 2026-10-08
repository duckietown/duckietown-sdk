"""Integration tests for the SDK shared-memory world channels."""

# ruff: noqa: SLF001

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import AsyncMock, Mock, patch

import pytest
from dtps_http import RawData
from duckietown_messages.actuators import DifferentialPWM
from duckietown_messages.simulation import WorldEntityInput, WorldEntityOutput
from duckietown_messages.simulation import WorldInput as WorldInputMessage
from duckietown_messages.simulation import WorldOutput as WorldOutputMessage

from duckietown.sdk.middleware.dtps.base import DTPS, DTPSConnector
from duckietown.sdk.middleware.dtps.components import (
    DTPSWorldInput,
    DTPSWorldOutput,
)


class ShmTransportTests(unittest.TestCase):
    """Verify DTPS world-I/O components use native SHM channels."""

    def _make_channel_base(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return Path(temp_dir.name) / "world_io"

    def _make_peer(self) -> DTPSConnector:
        peer = DTPS.get_connector("127.0.0.1", 1, shared=False)
        self.addCleanup(self._close_peer, peer)
        return peer

    @staticmethod
    def _close_peer(peer: DTPSConnector) -> None:
        coroutine = peer.context.aclose()
        peer.arun(coroutine, block=True)

    def test_connector_propagates_task_errors(self) -> None:
        """Propagate startup failures to the blocking caller."""
        async def fail() -> None:
            message = "startup failed"
            raise RuntimeError(message)

        peer = self._make_peer()
        with pytest.raises(RuntimeError, match="startup failed"):
            peer.arun(fail(), block=True)

    def test_connector_does_not_block_its_event_loop(self) -> None:
        """Schedule callback cleanup without blocking its own loop."""
        async def check() -> None:
            loop = asyncio.get_running_loop()
            connector = DTPSConnector(Mock(), loop)
            completed = asyncio.Event()

            async def complete() -> None:
                completed.set()

            with patch(
                "concurrent.futures.Future.result",
                side_effect=RuntimeError("Cannot block the event loop"),
            ) as result:
                connector.arun(complete(), block=True)
                await asyncio.wait_for(completed.wait(), timeout=1)
                if result.call_count:
                    pytest.fail("Connector blocked its own event loop.")

        asyncio.run(check())

    def test_http_websockets_publisher_stops_and_restarts(self) -> None:
        """Stop HTTP/WebSockets workers and keep shared contexts."""
        started_event = Event()
        stopped_event = Event()
        workers: list[asyncio.Task[None]] = []

        async def wait_for_stop() -> None:
            worker = asyncio.current_task()
            if worker is None:
                message = "Publisher is not running in an asyncio task."
                raise RuntimeError(message)
            workers.append(worker)
            started_event.set()
            try:
                waiting_event = asyncio.Event()
                await waiting_event.wait()
            finally:
                stopped_event.set()

        async def close_workers() -> None:
            for worker in workers:
                worker.cancel()
            await asyncio.gather(*workers, return_exceptions=True)

        connector = DTPS.get_connector("127.0.0.1", 1)
        publisher_mock = AsyncMock(side_effect=wait_for_stop)
        close_context = AsyncMock()
        with (
            patch.object(DTPSWorldOutput, "_publisher", publisher_mock),
            patch.object(connector.context, "aclose", close_context),
        ):
            world_output = DTPSWorldOutput("127.0.0.1", 1, "gym", "")
            try:
                for _attempt in range(2):
                    started_event.clear()
                    stopped_event.clear()
                    world_output.start()
                    if not started_event.wait(2.0):
                        pytest.fail("HTTP/WebSockets publisher did not start.")
                    worker = world_output._publisher_task
                    if worker is None:
                        pytest.fail(
                            "HTTP/WebSockets publisher task is not tracked.",
                        )
                    world_output.stop()
                    if (
                        not worker.done()
                        or not stopped_event.is_set()
                        or world_output._publisher_task is not None
                        or close_context.await_count
                    ):
                        pytest.fail("Incorrect stopped task/context state.")
            finally:
                if world_output.has_started:
                    world_output.stop()
                coroutine = close_workers()
                connector.arun(coroutine, block=True)

    def test_world_input_uses_native_dtps_channel(self) -> None:
        """Deliver native DTPS snapshots and ignore retained resets."""
        channel_base = self._make_channel_base()
        expected_session_id = 11
        received_messages: list[dict] = []
        received_event = Event()
        peer = self._make_peer()
        topic = peer.context.navigate("robot", "gym", "in")
        reset = RawData.cbor_from_native_object(None)
        coroutine = topic.publish(
            reset,
            shm_path=str(channel_base) + ".world_input",
            shm_only=True,
        )
        peer.arun(coroutine, block=True)

        world_input = DTPSWorldInput(
            "127.0.0.1",
            1,
            "gym",
            "",
            shm_path=str(channel_base) + ".world_input",
            shm_only=True,
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
            coroutine = topic.publish(
                message.to_rawdata(),
                shm_path=str(channel_base) + ".world_input",
                shm_only=True,
            )
            peer.arun(coroutine, block=True)

            assert received_event.wait(2.0)  # noqa: S101
            assert (  # noqa: S101
                received_messages[0]["session_id"] == expected_session_id
            )
            assert world_input.current_session_id == expected_session_id  # noqa: S101
            assert None not in received_messages  # noqa: S101
        finally:
            world_input.stop()
        assert world_input._subscription is None  # noqa: S101
        assert world_input._connector_closed  # noqa: S101

    def test_world_output_uses_native_dtps_channel(self) -> None:
        """Deliver native DTPS actions across a publisher restart."""
        channel_base = self._make_channel_base()
        expected_session_id = 23
        received_payloads: list[RawData] = []
        received_event = Event()

        async def on_payload(payload: RawData) -> None:
            received_payloads.append(payload)
            received_event.set()

        peer = self._make_peer()
        topic = peer.context.navigate("robot", "gym", "out")
        coroutine = topic.subscribe(
            on_payload,
            queue_size=1,
            shm_path=str(channel_base) + ".world_output",
            shm_only=True,
        )
        subscription = peer.arun(coroutine, block=True)
        assert subscription is not None  # noqa: S101
        world_output = DTPSWorldOutput(
            "127.0.0.1",
            1,
            "gym",
            "",
            shm_path=str(channel_base) + ".world_output",
            shm_only=True,
        )
        with pytest.raises(RuntimeError, match="not started"):
            world_output.publish(WorldOutputMessage(entities={}))
        previous_context = None
        try:
            sessions = (expected_session_id, expected_session_id + 1)
            for session_id in sessions:
                received_event.clear()
                world_output.start()
                assert (  # noqa: S101
                    world_output._connector.context is not previous_context
                )
                previous_context = world_output._connector.context
                worker = world_output._publisher_task
                assert worker is not None  # noqa: S101
                world_output.publish(
                    WorldOutputMessage(
                        session_id=session_id,
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
                received_message = WorldOutputMessage.from_rawdata(
                    received_payloads[-1],
                )
                assert received_message.session_id == session_id  # noqa: S101
                assert (  # noqa: S101
                    "map_0/vehicle_0" in received_message.entities
                )
                world_output.stop()
                assert worker.done()  # noqa: S101
                assert world_output._publisher_task is None  # noqa: S101
                assert world_output._connector_closed  # noqa: S101
        finally:
            if world_output.has_started:
                world_output.stop()
            coroutine = subscription.unsubscribe()
            peer.arun(coroutine, block=True)

    def test_callback_can_publish_then_stop(self) -> None:  # noqa: PLR0915
        """Publish an action and stop both components in a callback."""
        channel_base = self._make_channel_base()
        peer = self._make_peer()
        expected_session_id = 31
        received_event = Event()
        stopped_event = Event()
        received_messages: list[WorldOutputMessage] = []
        callback_errors: list[Exception] = []

        async def on_output(raw: RawData) -> None:
            message = WorldOutputMessage.from_rawdata(raw)
            assert isinstance(message, WorldOutputMessage)  # noqa: S101
            received_messages.append(message)
            received_event.set()

        output_topic = peer.context.navigate("robot", "gym", "out")
        subscribe_coroutine = output_topic.subscribe(
            on_output,
            queue_size=1,
            shm_path=str(channel_base) + ".world_output",
            shm_only=True,
        )
        subscription = peer.arun(subscribe_coroutine, block=True)
        assert subscription is not None  # noqa: S101
        world_input = DTPSWorldInput(
            "127.0.0.1",
            1,
            "gym",
            "",
            shm_path=str(channel_base) + ".world_input",
            shm_only=True,
        )
        world_output = DTPSWorldOutput(
            "127.0.0.1",
            1,
            "gym",
            "",
            shm_path=str(channel_base) + ".world_output",
            shm_only=True,
        )
        world_input.enable_profiling()
        world_output.enable_profiling()

        def on_input(message: dict) -> None:
            try:
                world_output.publish(
                    WorldOutputMessage(
                        session_id=message["session_id"],
                        entities={},
                    ),
                )
                world_input.stop()
                world_output.stop()
            except Exception as error:  # noqa: BLE001
                callback_errors.append(error)
            finally:
                stopped_event.set()

        world_input.attach(on_input)
        world_output.start()
        world_input.start()
        try:
            input_topic = peer.context.navigate("robot", "gym", "in")
            message = WorldInputMessage(
                session_id=expected_session_id,
                entities={},
            )
            publish_coroutine = input_topic.publish(
                message.to_rawdata(),
                shm_path=str(channel_base) + ".world_input",
                shm_only=True,
            )
            peer.arun(publish_coroutine, block=True)
            assert stopped_event.wait(2.0)  # noqa: S101
            assert not callback_errors  # noqa: S101
            assert received_event.wait(2.0)  # noqa: S101
            assert (  # noqa: S101
                received_messages[-1].session_id == expected_session_id
            )
            assert not world_input.has_started  # noqa: S101
            assert not world_output.has_started  # noqa: S101
        finally:
            if world_input.has_started:
                world_input.stop()
            if world_output.has_started:
                world_output.stop()
            unsubscribe_coroutine = subscription.unsubscribe()
            peer.arun(unsubscribe_coroutine, block=True)


if __name__ == "__main__":
    unittest.main()
