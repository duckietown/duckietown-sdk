"""Regression tests for SDK drivers, transports, and lifecycle."""

# ruff: noqa: SLF001

from __future__ import annotations

import asyncio
import math
import os
import tempfile
import unittest
from functools import partial
from pathlib import Path
from threading import Event, get_ident
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock, patch

import numpy as np
import pytest
from dtps_http import RawData
from dtps_http.constants import SHM_DEFAULT_CAPACITY
from duckietown_messages.actuators import CarLights, DifferentialPWM
from duckietown_messages.colors import RGBA
from duckietown_messages.sensors import CompressedImage
from duckietown_messages.simulation import WorldEntityInput, WorldEntityOutput
from duckietown_messages.simulation import WorldInput as WorldInputMessage
from duckietown_messages.simulation import WorldOutput as WorldOutputMessage
from duckietown_messages.standard import Boolean, Header

from duckietown.sdk.middleware.dtps import components as dtps_components
from duckietown.sdk.middleware.dtps.base import (
    DTPS,
    DTPSConnector,
    GenericDTPSPublisher,
    GenericDTPSSubscriber,
)
from duckietown.sdk.middleware.dtps.components import (
    DTPSCameraDriver,
    DTPSDeltaTDriver,
    DTPSInertialMeasurementUnit,
    DTPSLEDsDriver,
    DTPSMapLayerDriver,
    DTPSMotorsDriver,
    DTPSPoseDriver,
    DTPSResetFlagDriver,
    DTPSTimeOfFlightDriver,
    DTPSTwist,
    DTPSWheelEncoderDriver,
    DTPSWorldInput,
    DTPSWorldOutput,
)
from duckietown.sdk.middleware.timing_profiler import TimingProfiler
from duckietown.sdk.types import Component, CompoundComponent
from duckietown.sdk.utils.jpeg import JPEG

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping


class _EchoSubscriber(GenericDTPSSubscriber):
    def _unpack(self, message: object) -> object:
        return message


def _deliver_callback(
    callback: Callable[[RawData], Awaitable[None]],
    raw: RawData,
) -> None:
    async def deliver() -> None:
        await callback(raw)

    coroutine = deliver()
    asyncio.run(coroutine)


async def _record_raw(
    received: list[RawData],
    received_event: Event,
    raw: RawData,
) -> None:
    received.append(raw)
    received_event.set()


def _record_callback(
    received: list[tuple[int, object]],
    message: object,
) -> None:
    received.append((get_ident(), message))


def _declared_drivers(base: type[Component]) -> set[type[Component]]:
    return {
        value
        for value in vars(dtps_components).values()
        if isinstance(value, type)
        and value.__module__ == dtps_components.__name__
        and issubclass(value, base)
    }


class ShmTransportTests(unittest.TestCase):
    """Verify driver contracts, native DTPS SHM, and safe lifecycle."""

    def test_profiler_reports_bounded_recent_latency_statistics(self) -> None:
        """Separate startup outliers from recent measurements."""
        profiler = TimingProfiler("transport")
        log = Mock()
        profiler.observe("ignored", 1.0)
        profiler.log(log)
        log.info.assert_not_called()
        profiler.enable()
        profiler.observe("delivery", 1300.0)
        profiler.log(log)
        first_report = log.info.call_args.args[-1]
        first_row = next(
            line for line in first_report.splitlines() if "delivery" in line
        )
        first_cells = [cell.strip() for cell in first_row.split("|")[1:-1]]
        if first_cells[2:5] != ["1300.0", "1300.0", "1300.0"]:
            pytest.fail("Single-sample percentiles are incorrect.")
        recent_count = 200
        for _sample in range(recent_count):
            profiler.observe("delivery", 10.0)
        profiler.log(log)
        report = log.info.call_args.args[-1]
        row = next(line for line in report.splitlines() if "delivery" in line)
        cells = [cell.strip() for cell in row.split("|")[1:-1]]
        if cells[:5] != ["delivery", "201", "16.42", "10.0", "10.0"]:
            pytest.fail("Recent percentiles include a stale startup sample.")
        if len(profiler._history["delivery"]) != recent_count:
            pytest.fail("Profiler history is not bounded.")
        if "all samples" not in report or "latest 200" not in report:
            pytest.fail("Profiler does not explain its sample windows.")

    def test_profiler_column_widths_fit_contents(self) -> None:
        """Keep profiler columns aligned without truncating values."""
        cases = (
            ("x", 0.0, 1),
            ("wide/duration", 123456789012345.67, 1),
            ("wide/frequency", 0.00000000001, 1),
            ("k" * 120, 1.0, 10**18),
        )
        for key, duration, count in cases:
            with self.subTest(key=key, duration=duration, count=count):
                profiler = TimingProfiler("transport")
                profiler.enable()
                profiler.observe(key, duration)
                profiler._count[key] = count
                profiler._data[key] = duration * count
                log = Mock()
                profiler.log(log)
                table = log.info.call_args.args[-1]
                lines = [
                    line for line in table.splitlines()
                    if line.startswith(("+", "|"))
                ]
                boundaries = [
                    index for index, value in enumerate(lines[0])
                    if value == "+"
                ]
                for line in lines:
                    if len(line) != len(lines[0]):
                        pytest.fail("Profiler row and border widths differ.")
                    boundary = "+" if line.startswith("+") else "|"
                    actual_boundaries = [
                        index for index, value in enumerate(line)
                        if value == boundary
                    ]
                    if actual_boundaries != boundaries:
                        pytest.fail("Profiler column borders are misaligned.")
                values = [
                    value.strip() for value in lines[-2].strip("|").split("|")
                ]
                if values[0] != key or values[1] != str(count):
                    pytest.fail("Profiler keys or call counts were truncated.")

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

    def test_publisher_driver_transport_options(self) -> None:
        """Retain transport configuration for every publisher driver."""
        peer = self._make_peer()
        channel = str(self._make_channel_base())
        prefix = ("root", "robot")
        cases = (
            (
                DTPSLEDsDriver,
                "lights",
                ("actuator", "lights", "lights", "pattern"),
            ),
            (
                DTPSMotorsDriver,
                "wheels",
                ("actuator", "wheels", "wheels", "pwm_filtered"),
            ),
            (DTPSResetFlagDriver, "", ("state", "reset")),
            (DTPSWorldOutput, "", ("out",)),
        )
        if {case[0] for case in cases} != _declared_drivers(
            GenericDTPSPublisher,
        ):
            pytest.fail("Publisher matrix omits a declared driver.")
        with patch.object(DTPS, "get_connector", return_value=peer) as connect:
            for driver_type, name, topic in cases:
                for shm_only in (False, True):
                    with self.subTest(driver=driver_type, shm_only=shm_only):
                        publisher = driver_type(
                            "127.0.0.1",
                            1,
                            "robot",
                            name,
                            path_prefix=prefix,
                            shm_path=channel,
                            shm_only=shm_only,
                        )
                        actual = (
                            publisher._topic,
                            publisher._path_prefix,
                            publisher._shm_path,
                            publisher._shm_only,
                        )
                        if actual != (topic, prefix, channel, shm_only):
                            pytest.fail("Publisher lost transport options.")
                        if (
                            type(publisher).publish
                            is not GenericDTPSPublisher.publish
                        ):
                            pytest.fail("A no-op driver publish masks DTPS.")
                        if publisher._publisher_task is not None:
                            pytest.fail("Constructor started a publisher.")
                        with pytest.raises(RuntimeError, match="not started"):
                            publisher.publish({})
                        shared = connect.call_args.kwargs.get("shared", True)
                        if shared == shm_only:
                            pytest.fail("Incorrect publisher context sharing.")

    def test_subscriber_driver_transport_options(self) -> None:
        """Retain topics and options for every subscriber driver."""
        peer = self._make_peer()
        channel = str(self._make_channel_base())
        prefix = ("root", "robot")
        frequency = 30.0
        cases = (
            (
                DTPSCameraDriver,
                "front",
                "robot",
                ("sensor", "camera", "front", "jpeg"),
            ),
            (DTPSDeltaTDriver, "", "", ("delta_time",)),
            (
                DTPSInertialMeasurementUnit,
                "imu",
                "robot",
                ("sensor", "imu", "imu", "all"),
            ),
            (DTPSMapLayerDriver, "tiles", "", ("map", "tiles")),
            (DTPSPoseDriver, "", "robot", ("state", "pose")),
            (
                DTPSTimeOfFlightDriver,
                "front",
                "robot",
                ("sensor", "time_of_flight", "front", "range"),
            ),
            (DTPSTwist, "", "robot", ("state", "twist")),
            (
                DTPSWheelEncoderDriver,
                "left",
                "robot",
                ("sensor", "wheel_encoder", "left", "ticks"),
            ),
            (
                DTPSWheelEncoderDriver,
                "right",
                "robot",
                ("sensor", "wheel_encoder", "right", "ticks"),
            ),
            (DTPSWorldInput, "", "robot", ("in",)),
        )
        if {case[0] for case in cases} != _declared_drivers(
            GenericDTPSSubscriber,
        ):
            pytest.fail("Subscriber matrix omits a declared driver.")
        with patch.object(DTPS, "get_connector", return_value=peer) as connect:
            for driver_type, name, robot_name, topic in cases:
                for shm_only in (False, True):
                    with self.subTest(driver=driver_type, shm_only=shm_only):
                        subscriber = driver_type(
                            "127.0.0.1",
                            1,
                            "robot",
                            name,
                            frequency=frequency,
                            path_prefix=prefix,
                            shm_path=channel,
                            shm_only=shm_only,
                        )
                        actual = (
                            subscriber._robot_name,
                            subscriber._topic,
                            subscriber._path_prefix,
                            subscriber._shm_path,
                            subscriber._shm_only,
                            subscriber._frequency,
                        )
                        expected = (
                            robot_name,
                            topic,
                            prefix,
                            channel,
                            shm_only,
                            frequency,
                        )
                        if actual != expected:
                            pytest.fail("Subscriber lost transport options.")
                        if subscriber._subscription is not None:
                            pytest.fail("Constructor started a subscription.")
                        shared = connect.call_args.kwargs.get("shared", True)
                        if shared == shm_only:
                            pytest.fail(
                                "Incorrect subscriber context sharing.",
                            )

    @staticmethod
    def _subscriber_payloads() -> tuple[
        tuple[
            Callable[..., GenericDTPSSubscriber],
            str,
            Mapping[str, object],
            object,
        ],
        ...,
    ]:
        image = np.zeros((8, 8, 3), dtype=np.uint8)
        jpeg = JPEG.encode(image)
        position = {"x": 1.0, "y": 2.0, "z": 3.0}
        rotation = {"w": 1.0, "x": 0.0, "y": 0.0, "z": 0.0}
        header = {"timestamp": 123.0}
        imu = {"ax": 0.1, "ay": 0.2, "az": 9.81}
        pose = {"position": position, "rotation": rotation}
        twist = {
            "linear_velocity": position,
            "angular_velocity": position,
        }
        world = {"session_id": 7, "entities": {}}
        map_layer = {"data": {"map_0/tile_0_0": {"type": "straight"}}}
        return (
            (DTPSCameraDriver, "front", {"data": jpeg}, image),
            (DTPSDeltaTDriver, "", {"data": 0.1}, 0.1),
            (DTPSInertialMeasurementUnit, "imu", {"data": imu}, imu),
            (DTPSMapLayerDriver, "tiles", map_layer, map_layer),
            (
                DTPSPoseDriver,
                "",
                {"header": header, **pose},
                {
                    "timestamp": 123.0,
                    **pose,
                },
            ),
            (DTPSTimeOfFlightDriver, "front", {"data": 0.3}, 0.3),
            (
                DTPSTwist,
                "",
                {"header": header, **twist},
                {
                    "timestamp": 123.0,
                    **twist,
                },
            ),
            (DTPSWheelEncoderDriver, "left", {"data": 135}, 2 * math.pi),
            (DTPSWheelEncoderDriver, "right", {"data": -135}, -2 * math.pi),
            (DTPSWorldInput, "", world, world),
        )

    def test_subscriber_driver_decoding_and_callbacks(self) -> None:
        """Decode every subscriber payload without exposing metadata."""
        peer = self._make_peer()
        with patch.object(DTPS, "get_connector", return_value=peer):
            for (
                driver_type,
                name,
                message,
                expected,
            ) in self._subscriber_payloads():
                with self.subTest(driver=driver_type, name=name):
                    subscriber = driver_type("127.0.0.1", 1, "robot", name)
                    callback = Mock()
                    subscriber.attach(callback)
                    enriched = dict(message)
                    enriched["__dtps_timing__"] = {
                        "engine_send_called_ns": 1,
                    }
                    raw = RawData.cbor_from_native_object(enriched)
                    receive = subscriber._get_callback()
                    _deliver_callback(receive, raw)
                    callback.assert_called_once()
                    delivered = callback.call_args.args[0]
                    np.testing.assert_equal(delivered, expected)
                    np.testing.assert_equal(subscriber.latest, expected)
                    with (
                        patch.object(subscriber, "_start") as start,
                        patch.object(subscriber, "_stop") as stop,
                    ):
                        reading = subscriber.get(block=True, clean_up=True)
                        np.testing.assert_equal(reading, expected)
                        start.assert_called_once_with()
                        stop.assert_called_once_with()
                    subscriber.detach(callback)
                    if subscriber._callbacks:
                        pytest.fail("Detached callback was retained.")

    def test_all_subscriber_drivers_receive_native_shm(self) -> None:
        """Receive every subscriber payload through native SHM."""
        for (
            driver_type,
            name,
            message,
            expected,
        ) in self._subscriber_payloads():
            with self.subTest(driver=driver_type, name=name):
                peer = self._make_peer()
                channel = str(self._make_channel_base())
                subscriber = driver_type(
                    "127.0.0.1",
                    1,
                    "robot",
                    name,
                    path_prefix=("testing",),
                    shm_path=channel,
                    shm_only=True,
                )
                topic = peer.context.navigate(
                    "testing",
                    subscriber._robot_name,
                    *subscriber._topic,
                )
                try:
                    subscriber.start()
                    raw = RawData.cbor_from_native_object(message)
                    coroutine = topic.publish(
                        raw,
                        shm_path=channel,
                        shm_only=True,
                    )
                    peer.arun(coroutine, block=True)
                    if not subscriber._event.wait(2.0):
                        pytest.fail("Subscriber did not receive SHM data.")
                    reading = subscriber.get(
                        block=True,
                        timeout=0,
                        clean_up=True,
                    )
                    np.testing.assert_equal(reading, expected)
                    if not subscriber._connector_closed:
                        pytest.fail("Read cleanup left the SHM context open.")
                finally:
                    if subscriber.is_started:
                        subscriber.stop()

    def test_actuator_setters_publish_typed_messages(self) -> None:
        """Forward all actuator setters through transport publishing."""
        peer = self._make_peer()
        header = Header(timestamp=123.0)
        color = RGBA(r=0.25, g=0.5, b=0.75, a=1.0, header=header)
        rgba = (0.25, 0.5, 0.75, 1.0)
        with patch.object(DTPS, "get_connector", return_value=peer):
            motors = DTPSMotorsDriver("127.0.0.1", 1, "robot", "wheels")
            lights = DTPSLEDsDriver("127.0.0.1", 1, "robot", "lights")
            reset = DTPSResetFlagDriver("127.0.0.1", 1, "robot", "")
            cases = (
                (
                    motors,
                    partial(motors.set, 0.2, -0.3, header=header),
                    DifferentialPWM(left=0.2, right=-0.3, header=header),
                ),
                (
                    lights,
                    partial(lights.set, rgba, rgba, rgba, rgba, header=header),
                    CarLights(
                        front_left=color,
                        front_right=color,
                        back_left=color,
                        back_right=color,
                        header=header,
                    ),
                ),
                (
                    reset,
                    partial(reset.set, data=False, header=header),
                    Boolean(data=False, header=header),
                ),
            )
            for component, set_value, expected in cases:
                for should_publish in (False, True):
                    with self.subTest(
                        driver=type(component),
                        publish=should_publish,
                    ), patch.object(component, "publish") as publish:
                        set_value(publish=should_publish)
                        if should_publish:
                            publish.assert_called_once_with(expected)
                        else:
                            publish.assert_not_called()

    def test_actuator_and_encoder_reject_invalid_values(self) -> None:
        """Reject invalid actuator commands and encoder sides."""
        peer = self._make_peer()
        valid = (0.0, 0.0, 0.0, 1.0)
        with patch.object(DTPS, "get_connector", return_value=peer):
            motors = DTPSMotorsDriver("127.0.0.1", 1, "robot", "wheels")
            lights = DTPSLEDsDriver("127.0.0.1", 1, "robot", "lights")
            with patch.object(motors, "publish") as publish:
                for left, right in ((-1.1, 0), (0, 1.1)):
                    with pytest.raises(ValueError, match="PWM"):
                        motors.set(left, right)
                publish.assert_not_called()
            with patch.object(lights, "publish") as publish:
                for invalid in ((-0.1, 0, 0, 1), (0, 0, 0, 1.1)):
                    with pytest.raises(ValueError, match="RGBA"):
                        lights.set(valid, valid, valid, invalid)
                publish.assert_not_called()
            with pytest.raises(ValueError, match="Side"):
                DTPSWheelEncoderDriver("127.0.0.1", 1, "robot", "middle")

    def test_message_serialization_variants(self) -> None:
        """Serialize native, typed, and raw messages."""
        message = DifferentialPWM(left=0.2, right=0.3)
        payload = {"session_id": 7, "image": b"\x00\xff"}
        raw = RawData.cbor_from_native_object(payload)
        if GenericDTPSPublisher._serialize_message(raw) is not raw:
            pytest.fail("RawData was re-encoded.")
        for value, expected in (
            (message, message.to_native()),
            (payload, payload),
            (None, None),
        ):
            with self.subTest(value=type(value)):
                serialized = GenericDTPSPublisher._serialize_message(value)
                if serialized.get_as_native_object() != expected:
                    pytest.fail("Serialization changed the payload.")

    def test_all_publisher_drivers_deliver_native_shm(self) -> None:
        """Deliver every publisher message through a native SHM peer."""
        color = RGBA(r=0.1, g=0.2, b=0.3, a=1.0)
        cases = (
            (
                DTPSLEDsDriver,
                "lights",
                CarLights(
                    front_left=color,
                    front_right=color,
                    back_left=color,
                    back_right=color,
                ),
            ),
            (DTPSMotorsDriver, "wheels", DifferentialPWM(left=0.2, right=0.3)),
            (DTPSResetFlagDriver, "", Boolean(data=True)),
            (
                DTPSWorldOutput,
                "",
                WorldOutputMessage(
                    session_id=7,
                    entities={},
                ),
            ),
        )
        for driver_type, name, message in cases:
            with self.subTest(driver=driver_type):
                peer = self._make_peer()
                channel = str(self._make_channel_base())
                received: list[RawData] = []
                received_event = Event()
                receive = partial(_record_raw, received, received_event)

                publisher = driver_type(
                    "127.0.0.1",
                    1,
                    "robot",
                    name,
                    path_prefix=("testing",),
                    shm_path=channel,
                    shm_only=True,
                )
                topic = peer.context.navigate(
                    "testing",
                    "robot",
                    *publisher._topic,
                )
                coroutine = topic.subscribe(
                    receive,
                    shm_path=channel,
                    shm_only=True,
                    queue_size=1,
                )
                subscription = peer.arun(coroutine, block=True)
                if subscription is None:
                    pytest.fail("Native peer did not subscribe.")
                try:
                    publisher.start()
                    publisher.publish(message)
                    if not received_event.wait(2.0):
                        pytest.fail("Publisher did not deliver over SHM.")
                    decoded = type(message).from_rawdata(received[-1])
                    if decoded != message:
                        pytest.fail("SHM delivery changed the message.")
                finally:
                    if publisher.is_started:
                        publisher.stop()
                    coroutine = subscription.unsubscribe()
                    peer.arun(coroutine, block=True)

    def test_publish_errors_release_queue_acknowledgements(self) -> None:
        """Acknowledge dequeued work even when transport writes fail."""

        async def check() -> None:
            for shm_path in (None, "/unused/test-channel"):
                publisher = GenericDTPSPublisher.__new__(GenericDTPSPublisher)
                publisher._queue = asyncio.Queue(maxsize=1)
                publisher._profiler = TimingProfiler("publish test")
                publisher._shm_path = shm_path
                publisher._shm_only = shm_path is not None
                raw = RawData.cbor_from_native_object({"command": 1})
                publisher._queue.put_nowait((raw, 1))
                transport = Mock()
                transport.publish = AsyncMock(
                    side_effect=RuntimeError("write failed"),
                )
                with pytest.raises(RuntimeError, match="write failed"):
                    await publisher._publish_pending(transport)
                await asyncio.wait_for(publisher._queue.join(), timeout=0.1)
                if shm_path is None:
                    transport.publish.assert_awaited_once_with(raw)
                else:
                    transport.publish.assert_awaited_once_with(
                        raw,
                        shm_path=shm_path,
                        shm_only=True,
                    )

        asyncio.run(check())

    def test_network_queue_overflow_and_shutdown_drain(self) -> None:
        """Bound network work and drain abandoned items on stop."""

        async def check() -> None:
            publisher = GenericDTPSPublisher.__new__(GenericDTPSPublisher)
            publisher._queue = asyncio.Queue(maxsize=1)
            publisher._publisher_task = None
            publisher._shm_only = False
            first = RawData.cbor_from_native_object({"command": 1})
            second = RawData.cbor_from_native_object({"command": 2})
            await publisher._publish_network(first, 1)
            await publisher._publish_network(second, 2)
            if publisher._queue.qsize() != 1:
                pytest.fail("Network queue is not bounded.")
            queued = publisher._queue.get_nowait()
            if queued != (first, 1):
                pytest.fail("Overflow replaced an already queued command.")
            publisher._queue.task_done()
            publisher._queue.put_nowait(queued)
            await publisher._stop_publisher()
            await asyncio.wait_for(publisher._queue.join(), timeout=0.1)
            if not publisher._queue.empty():
                pytest.fail("Shutdown left queued work behind.")

        asyncio.run(check())

    def test_shm_publish_rejects_missing_or_finished_workers(self) -> None:
        """Reject absent, cancelled, and normally completed workers."""

        async def complete() -> None:
            return None

        async def check() -> None:
            publisher = GenericDTPSPublisher.__new__(GenericDTPSPublisher)
            publisher._queue = asyncio.Queue(maxsize=1)
            raw = RawData.cbor_from_native_object({"command": 1})
            publisher._publisher_task = None
            with pytest.raises(RuntimeError, match="not running"):
                await publisher._publish_shm(raw, 0)
            publisher._publisher_task = asyncio.create_task(complete())
            publisher._publisher_task.cancel()
            await asyncio.gather(
                publisher._publisher_task,
                return_exceptions=True,
            )
            with pytest.raises(RuntimeError, match="not running"):
                await publisher._publish_shm(raw, 0)
            publisher._publisher_task = asyncio.create_task(complete())
            await publisher._publisher_task
            with pytest.raises(RuntimeError, match="stopped"):
                await publisher._publish_shm(raw, 0)

        asyncio.run(check())

    def test_subscriber_subscription_options(self) -> None:
        """Use correct routing, frequency, and native SHM queue size."""

        async def check() -> None:
            for shm_path in (None, "/unused/test-channel"):
                queue = Mock()
                queue.subscribe = AsyncMock(return_value=Mock())
                connector = Mock()
                connector.context.navigate.return_value = queue
                with patch.object(
                    DTPS, "get_connector", return_value=connector,
                ):
                    subscriber = _EchoSubscriber(
                        "127.0.0.1",
                        1,
                        "robot",
                        ("sensor", "data"),
                        path_prefix=("testing",),
                        shm_path=shm_path,
                        shm_only=shm_path is not None,
                    )
                    await subscriber._subscribe()
                    connector.context.navigate.assert_called_once_with(
                        "testing",
                        "robot",
                        "sensor",
                        "data",
                    )
                    options: dict[str, object] = {"max_frequency": None}
                    if shm_path is not None:
                        options.update(
                            queue_size=1,
                            shm_path=shm_path,
                            shm_only=True,
                        )
                    awaited = queue.subscribe.await_args
                    if awaited is None or awaited.kwargs != options:
                        pytest.fail("Incorrect DTPS subscription options.")
                    if subscriber._subscription is None:
                        pytest.fail("Subscription was not tracked.")

        asyncio.run(check())

    def test_subscriber_callback_threads_and_resets(self) -> None:
        """Offload native callbacks and ignore only SHM null resets."""
        connector = Mock()
        with patch.object(DTPS, "get_connector", return_value=connector):
            for shm_only in (False, True):
                with self.subTest(shm_only=shm_only):
                    subscriber = _EchoSubscriber(
                        "127.0.0.1",
                        1,
                        "robot",
                        ("sensor", "data"),
                        shm_only=shm_only,
                    )
                    received: list[tuple[int, object]] = []
                    receive = partial(_record_callback, received)
                    subscriber.attach(receive)
                    callback = subscriber._get_callback()
                    null = RawData.cbor_from_native_object(None)
                    payload = {
                        "data": 3,
                        "__dtps_timing__": {"ignored": "bad"},
                    }
                    raw = RawData.cbor_from_native_object(payload)
                    loop_thread = get_ident()
                    _deliver_callback(callback, null)
                    if bool(received) == shm_only:
                        pytest.fail("Incorrect null-reset handling.")
                    received.clear()
                    _deliver_callback(callback, raw)
                    callback_thread, delivered = received[0]
                    if delivered != {"data": 3}:
                        pytest.fail("Metadata leaked to application data.")
                    if (callback_thread != loop_thread) != shm_only:
                        pytest.fail("Callback ran on the wrong thread.")

    def test_subscriber_callback_failure_propagates(self) -> None:
        """Preserve callback failures across both callback paths."""
        connector = Mock()
        with patch.object(DTPS, "get_connector", return_value=connector):
            for shm_only in (False, True):
                with self.subTest(shm_only=shm_only):
                    subscriber = _EchoSubscriber(
                        "127.0.0.1",
                        1,
                        "robot",
                        ("sensor", "data"),
                        shm_only=shm_only,
                    )
                    subscriber.attach(
                        Mock(side_effect=RuntimeError("callback failed")),
                    )
                    callback = subscriber._get_callback()
                    raw = RawData.cbor_from_native_object({"data": 1})
                    with pytest.raises(RuntimeError, match="callback failed"):
                        _deliver_callback(callback, raw)

    def test_subscriber_cleanup_and_restart(self) -> None:
        """Stop subscriptions and replace private contexts."""
        for shm_only in (False, True):
            with self.subTest(shm_only=shm_only):
                peer = self._make_peer()
                subscription = Mock()
                subscription.unsubscribe = AsyncMock()
                queue = Mock()
                queue.subscribe = AsyncMock(return_value=subscription)
                close_context = AsyncMock()
                with (
                    patch.object(
                        DTPS, "get_connector", return_value=peer,
                    ) as connect,
                    patch.object(peer.context, "navigate", return_value=queue),
                    patch.object(peer.context, "aclose", close_context),
                ):
                    subscriber = _EchoSubscriber(
                        "127.0.0.1",
                        1,
                        "robot",
                        ("sensor", "data"),
                        shm_path="/unused/channel" if shm_only else None,
                        shm_only=shm_only,
                    )
                    for _attempt in range(2):
                        subscriber.start()
                        coroutine = queue.subscribe()
                        peer.arun(coroutine, block=True)
                        subscriber.stop()
                        if subscriber._subscription is not None:
                            pytest.fail("Stopped subscription was retained.")
                        if subscriber._connector_closed != shm_only:
                            pytest.fail("Incorrect subscriber context state.")
                    expected_closes = 2 if shm_only else 0
                    if close_context.await_count != expected_closes:
                        pytest.fail("Incorrect subscriber context lifetime.")
                    if shm_only:
                        connect.assert_called_with(
                            "127.0.0.1", 1, shared=False,
                        )

    def test_shm_cleanup_closes_context_on_unsubscribe_error(self) -> None:
        """Close private resources even if unsubscribe fails."""

        async def check() -> None:
            connector = Mock()
            connector.context.aclose = AsyncMock()
            with patch.object(DTPS, "get_connector", return_value=connector):
                subscriber = _EchoSubscriber(
                    "127.0.0.1",
                    1,
                    "robot",
                    ("sensor", "data"),
                    shm_only=True,
                )
                subscriber._subscription = Mock()
                subscriber._subscription.unsubscribe = AsyncMock(
                    side_effect=RuntimeError("unsubscribe failed"),
                )
                with pytest.raises(RuntimeError, match="unsubscribe failed"):
                    await subscriber._stop_shm()
                connector.context.aclose.assert_awaited_once_with()
                if subscriber._subscription is not None:
                    pytest.fail("Failed subscription was retained.")
                if not subscriber._connector_closed:
                    pytest.fail("Private context was left open.")

        asyncio.run(check())

    def test_subscriber_get_consumes_each_reading_once(self) -> None:
        """Auto-start readers and consume the latest data once."""
        with patch.object(DTPS, "get_connector", return_value=Mock()):
            subscriber = _EchoSubscriber(
                "127.0.0.1",
                1,
                "robot",
                ("sensor", "data"),
            )
        with (
            patch.object(subscriber, "_start") as start,
            patch.object(subscriber, "_stop") as stop,
        ):
            if subscriber.get() is not None:
                pytest.fail("Empty subscriber returned a reading.")
            start.assert_called_once_with()
            subscriber._callback("first")
            subscriber._callback("latest")
            if subscriber.get() != "latest":
                pytest.fail("Subscriber did not return its latest reading.")
            if subscriber.get() is not None:
                pytest.fail("Subscriber delivered a reading twice.")
            subscriber._callback("blocking")
            if subscriber.get(block=True, clean_up=True) != "blocking":
                pytest.fail("Blocking read lost an available observation.")
            stop.assert_called_once_with()
            if subscriber.is_started:
                pytest.fail("Read cleanup left the subscriber running.")

    def test_subscriber_timeout_cleans_up_when_requested(self) -> None:
        """Release an auto-started subscriber after a timed-out read."""
        with patch.object(DTPS, "get_connector", return_value=Mock()):
            subscriber = _EchoSubscriber(
                "127.0.0.1",
                1,
                "robot",
                ("sensor", "data"),
            )
        with (
            patch.object(subscriber, "_start") as start,
            patch.object(subscriber, "_stop") as stop,
        ):
            result = subscriber.get(block=True, timeout=0, clean_up=True)
            if result is not None:
                pytest.fail("Timed-out read returned an observation.")
            start.assert_called_once_with()
            stop.assert_called_once_with()
            if subscriber.is_started:
                pytest.fail("Timed-out read leaked its subscription.")

    def test_transport_profiling_controls(self) -> None:
        """Enable, report, and disable profiling on both endpoints."""
        peer = self._make_peer()
        with patch.object(DTPS, "get_connector", return_value=peer):
            endpoints = (
                _EchoSubscriber("127.0.0.1", 1, "robot", ("sensor", "data")),
                GenericDTPSPublisher("127.0.0.1", 1, "robot", ("actuator",)),
            )
        for endpoint in endpoints:
            with self.subTest(endpoint=type(endpoint)):
                log = Mock()
                endpoint.print_profiling(log)
                log.info.assert_not_called()
                endpoint.enable_profiling()
                endpoint._profiler.observe("operation", 1.0)
                endpoint.print_profiling(log)
                log.info.assert_called_once()
                endpoint.enable_profiling(status=False)
                endpoint._profiler.observe("operation", 2.0)
                if endpoint._profiler._count["operation"] != 1:
                    pytest.fail("Disabled endpoint still recorded timing.")

    def test_subscription_start_failure_is_retryable(self) -> None:
        """Propagate asynchronous registration errors to start()."""
        peer = self._make_peer()
        subscription = Mock()
        subscription.unsubscribe = AsyncMock()
        queue = Mock()
        queue.subscribe = AsyncMock(
            side_effect=RuntimeError("subscribe failed"),
        )
        with (
            patch.object(DTPS, "get_connector", return_value=peer),
            patch.object(peer.context, "navigate", return_value=queue),
        ):
            subscriber = _EchoSubscriber(
                "127.0.0.1", 1, "robot", ("sensor", "data"),
            )
            try:
                with pytest.raises(RuntimeError, match="subscribe failed"):
                    subscriber.start()
                if subscriber.is_started:
                    pytest.fail("Failed subscription is marked started.")
                queue.subscribe.side_effect = None
                queue.subscribe.return_value = subscription
                subscriber.start()
                subscriber.stop()
                subscription.unsubscribe.assert_awaited_once_with()
            finally:
                if subscriber.is_started:
                    subscriber.stop()

    def test_publisher_start_failure_is_retryable(self) -> None:
        """Propagate scheduled publisher initialization failures."""
        peer = self._make_peer()
        with patch.object(DTPS, "get_connector", return_value=peer):
            publisher = GenericDTPSPublisher(
                "127.0.0.1", 1, "robot", ("actuator",),
            )
        with patch.object(
            publisher, "_start_publisher", new_callable=AsyncMock,
        ) as start:
            start.side_effect = RuntimeError("publisher startup failed")
            try:
                with pytest.raises(RuntimeError, match="publisher startup"):
                    publisher.start()
                if publisher.is_started:
                    pytest.fail("Failed publisher is marked started.")
                start.side_effect = None
                publisher.start()
                publisher.stop()
            finally:
                if publisher.is_started:
                    publisher.stop()

    def test_publisher_context_failure_is_retryable(self) -> None:
        """Report navigation and publisher-entry failures on startup."""
        for stage in ("navigate", "enter"):
            with self.subTest(stage=stage):
                peer = self._make_peer()
                manager = AsyncMock()
                queue = Mock()
                queue.publisher_context.return_value = manager
                failure = RuntimeError("publisher context failed")
                with (
                    patch.object(DTPS, "get_connector", return_value=peer),
                    patch.object(
                        peer.context, "navigate", return_value=queue,
                    ) as navigate,
                ):
                    publisher = GenericDTPSPublisher(
                        "127.0.0.1", 1, "robot", ("actuator",),
                    )
                    if stage == "navigate":
                        navigate.side_effect = failure
                    else:
                        manager.__aenter__.side_effect = failure
                    try:
                        with pytest.raises(RuntimeError) as error:
                            publisher.start()
                        if error.value is not failure:
                            pytest.fail("Startup hid the context error.")
                        if publisher.is_started:
                            pytest.fail("Failed publisher remains started.")
                        if publisher._publisher_task is not None:
                            pytest.fail("Failed startup leaked its worker.")
                        navigate.side_effect = None
                        manager.__aenter__.side_effect = None
                        publisher.start()
                        publisher.stop()
                    finally:
                        if publisher.is_started:
                            publisher.stop()

    def test_publisher_waits_for_context_and_cancels_cleanly(self) -> None:
        """Wait for context entry and clean up cancelled starts."""

        async def check() -> None:
            async def enter_context(
                entered: asyncio.Event,
                release: asyncio.Event,
            ) -> Mock:
                entered.set()
                await release.wait()
                return Mock()

            for cancel in (False, True):
                with self.subTest(cancel=cancel):
                    entered = asyncio.Event()
                    release = asyncio.Event()
                    manager = AsyncMock()
                    manager.__aenter__.side_effect = partial(
                        enter_context, entered, release,
                    )
                    queue = Mock()
                    queue.publisher_context.return_value = manager
                    publisher = GenericDTPSPublisher.__new__(
                        GenericDTPSPublisher,
                    )
                    publisher._queue = asyncio.Queue(maxsize=1)
                    publisher._shm_only = False
                    publisher._robot_name = "robot"
                    publisher._path_prefix = ()
                    publisher._topic = ("actuator",)
                    publisher._connector = Mock()
                    publisher._connector.context.navigate.return_value = queue
                    coroutine = publisher._start_publisher()
                    startup = asyncio.create_task(coroutine)
                    try:
                        await asyncio.wait_for(entered.wait(), timeout=1)
                        if startup.done():
                            pytest.fail("Startup did not wait for entry.")
                        if cancel:
                            startup.cancel()
                            with pytest.raises(asyncio.CancelledError):
                                await startup
                        else:
                            release.set()
                            await asyncio.wait_for(startup, timeout=1)
                    finally:
                        startup.cancel()
                        await asyncio.gather(startup, return_exceptions=True)
                        await publisher._stop_publisher()
                    pending = asyncio.all_tasks()
                    current_task = asyncio.current_task()
                    if current_task is not None:
                        pending.discard(current_task)
                    if pending:
                        pytest.fail("Publisher startup leaked tasks.")

        asyncio.run(check())

    def test_actuator_start_failure_is_retryable(self) -> None:
        """Keep actuator rollback from publishing before startup."""
        for driver_type in (DTPSMotorsDriver, DTPSLEDsDriver):
            for shm_only in (False, True):
                with self.subTest(driver=driver_type, shm_only=shm_only):
                    peer = self._make_peer()
                    with patch.object(
                        DTPS, "get_connector", return_value=peer,
                    ):
                        actuator = driver_type(
                            "127.0.0.1", 1, "robot", "actuator",
                            shm_only=shm_only,
                        )
                        with patch.object(
                            actuator, "_start_publisher",
                            new_callable=AsyncMock,
                        ) as start:
                            failure = RuntimeError("publisher startup failed")
                            start.side_effect = failure
                            with pytest.raises(RuntimeError) as error:
                                actuator.start()
                            if error.value is not failure:
                                pytest.fail("Rollback hid the startup error.")
                            if actuator.is_started:
                                pytest.fail("Failed actuator remains started.")
                            start.side_effect = None
                            actuator.start()
                            actuator.stop()
                            if actuator.is_started:
                                pytest.fail("Actuator retry did not stop.")

    def test_component_start_rolls_back_and_retries(self) -> None:
        """Clean partial startup before permitting another start."""
        component = Component()
        with (
            patch.object(
                component,
                "_start",
                side_effect=RuntimeError("startup failed"),
            ) as start,
            patch.object(component, "_stop") as stop,
        ):
            with pytest.raises(RuntimeError, match="startup failed"):
                component.start()
            stop.assert_called_once_with()
            if component.is_started:
                pytest.fail("Rolled-back component is still started.")
            stop.reset_mock()
            start.side_effect = None
            component.start()
            component.stop()
            stop.assert_called_once_with()
            if component.is_started:
                pytest.fail("Component could not restart after rollback.")

    def test_component_interrupt_does_not_run_rollback(self) -> None:
        """Propagate Ctrl+C without blocking on startup rollback."""
        component = Component()
        with (
            patch.object(component, "_start", side_effect=KeyboardInterrupt),
            patch.object(component, "_stop") as stop,
        ):
            with pytest.raises(KeyboardInterrupt):
                component.start()
            stop.assert_not_called()
            if component.is_started:
                pytest.fail("Interrupted startup is marked started.")

    def test_failed_rollback_preserves_errors_and_allows_stop(self) -> None:
        """Preserve startup errors and make failed cleanup retryable."""
        component = Component()
        startup_error = RuntimeError("startup failed")
        cleanup_error = RuntimeError("cleanup failed")
        with (
            patch.object(component, "_start", side_effect=startup_error),
            patch.object(
                component,
                "_stop",
                side_effect=cleanup_error,
            ) as stop,
        ):
            with pytest.raises(ExceptionGroup) as errors:
                component.start()
            if errors.value.exceptions != (startup_error, cleanup_error):
                pytest.fail("Startup or cleanup failure was lost.")
            if not component.is_started:
                pytest.fail("Failed cleanup cannot be retried with stop().")
            stop.side_effect = None
            component.stop()
            if component.is_started:
                pytest.fail("Successful cleanup did not reset the component.")

    def test_compound_start_rolls_back_started_children(self) -> None:
        """Release earlier children if a later child fails to start."""
        first = Component()
        failing = Component()
        last = Component()
        compound = CompoundComponent(
            {
                ("sensor", "first"): first,
                ("sensor", "failing"): failing,
                ("sensor", "last"): last,
            },
        )
        with (
            patch.object(first, "_stop") as first_stop,
            patch.object(failing, "_stop") as failing_stop,
            patch.object(
                failing,
                "_start",
                side_effect=RuntimeError("child startup failed"),
            ) as start,
        ):
            with pytest.raises(RuntimeError, match="child startup failed"):
                compound.start()
            first_stop.assert_called_once_with()
            failing_stop.assert_called_once_with()
            components = (compound, first, failing, last)
            if any(component.is_started for component in components):
                pytest.fail("Failed compound startup left children running.")
            start.side_effect = None
            compound.start()
            compound.stop()
            if any(component.is_started for component in components):
                pytest.fail("Compound could not restart after rollback.")

    def test_compound_stop_attempts_all_children_and_retries(self) -> None:
        """Collect failures while stopping every remaining child."""
        first = Component()
        middle = Component()
        last = Component()
        compound = CompoundComponent(
            {
                ("sensor", "first"): first,
                ("sensor", "middle"): middle,
                ("sensor", "last"): last,
            },
        )
        first_error = RuntimeError("first cleanup failed")
        last_error = RuntimeError("last cleanup failed")
        compound.start()
        with (
            patch.object(
                first,
                "_stop",
                side_effect=first_error,
            ) as first_stop,
            patch.object(middle, "_stop") as middle_stop,
            patch.object(last, "_stop", side_effect=last_error) as last_stop,
        ):
            with pytest.raises(ExceptionGroup) as errors:
                compound.stop()
            if errors.value.exceptions != (first_error, last_error):
                pytest.fail("Compound cleanup did not collect both failures.")
            middle_stop.assert_called_once_with()
            if middle.is_started or not compound.is_started:
                pytest.fail("Incorrect state after partial compound cleanup.")
            first_stop.side_effect = None
            last_stop.side_effect = None
            compound.stop()
            middle_stop.assert_called_once_with()
            components = (compound, first, middle, last)
            if any(component.is_started for component in components):
                pytest.fail("Retry did not finish compound cleanup.")

    def test_leds_stop_always_cleans_publisher(self) -> None:
        """Stop the publisher even if sending idle lights fails."""
        lights = DTPSLEDsDriver("127.0.0.1", 1, "robot", "lights")
        lights.has_started = True
        lights._publisher_task = Mock()
        lights._publisher_task.done.return_value = False
        for failure in (None, RuntimeError("idle publication failed")):
            with (
                patch.object(lights, "publish", side_effect=failure),
                patch.object(GenericDTPSPublisher, "_stop") as cleanup,
                patch("duckietown.sdk.middleware.dtps.components.time.sleep"),
            ):
                if failure is None:
                    lights._stop()
                else:
                    with pytest.raises(RuntimeError, match="idle publication"):
                        lights._stop()
                cleanup.assert_called_once_with()

    def test_connector_propagates_task_errors(self) -> None:
        """Propagate startup failures to the blocking caller."""

        async def fail() -> None:
            message = "startup failed"
            raise RuntimeError(message)

        peer = self._make_peer()
        with pytest.raises(RuntimeError, match="startup failed"):
            peer.arun(fail(), block=True)

    def test_connector_cancels_timed_out_work(self) -> None:
        """Cancel blocked operations when their deadline expires."""
        cancelled = Event()

        async def wait_forever() -> None:
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        peer = self._make_peer()
        with pytest.raises(TimeoutError):
            peer.arun(wait_forever(), block=True, timeout=0.05)
        if not cancelled.wait(1):
            pytest.fail("Timed-out connector work was not cancelled.")

    def test_connector_rejects_stopped_loop(self) -> None:
        """Fail promptly rather than enqueueing on a dead loop."""
        loop = asyncio.new_event_loop()
        connector = DTPSConnector(Mock(), loop)

        async def complete() -> None:
            return None

        try:
            with pytest.raises(RuntimeError, match="not running"):
                connector.arun(complete(), block=True)
        finally:
            loop.close()

    def test_dtps_resets_inherited_process_state(self) -> None:
        """Discard inherited event loops and cached contexts."""
        new_loop = Mock(spec=asyncio.AbstractEventLoop)
        with (
            patch.multiple(
                DTPS,
                _pid=-1,
                _loop=Mock(),
                _worker=Mock(),
                _contexts={("parent", 1): Mock()},
                _connectors={("parent", 1): Mock()},
            ),
            patch(
                "duckietown.sdk.middleware.dtps.base.asyncio.new_event_loop",
                return_value=new_loop,
            ),
            patch(
                "duckietown.sdk.middleware.dtps.base.threading.Thread",
            ) as worker,
        ):
            DTPS._init()
            if DTPS._pid != os.getpid() or DTPS._loop is not new_loop:
                pytest.fail("Worker did not create its own DTPS loop.")
            if DTPS._contexts or DTPS._connectors:
                pytest.fail("Worker retained parent DTPS caches.")
            worker.return_value.start.assert_called_once_with()

    def test_connector_rejects_inherited_instance(self) -> None:
        """Require component creation inside each worker process."""
        peer = self._make_peer()

        async def complete() -> None:
            return None

        with (
            patch.object(peer, "_pid", -1),
            pytest.raises(RuntimeError, match="another process"),
        ):
            peer.arun(complete(), block=True)

    def test_shm_publish_propagates_worker_failure(self) -> None:
        """Report failed workers without hanging on queue joins."""

        async def check() -> None:
            publisher = GenericDTPSPublisher.__new__(GenericDTPSPublisher)
            publisher._queue = asyncio.Queue(maxsize=1)

            async def fail() -> None:
                await publisher._queue.get()
                publisher._queue.task_done()
                message = "publish failed"
                raise RuntimeError(message)

            publisher._publisher_task = asyncio.create_task(fail())
            payload = RawData.cbor_from_native_object({"session_id": 1})
            with pytest.raises(RuntimeError, match="publish failed"):
                await asyncio.wait_for(
                    publisher._publish_shm(payload, 0),
                    timeout=0.1,
                )

        asyncio.run(check())

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

    def test_publisher_cancels_unstarted_worker(self) -> None:
        """Cancel before task execution without creating an orphan."""

        async def check() -> None:
            publisher = GenericDTPSPublisher.__new__(GenericDTPSPublisher)
            publisher._queue = asyncio.Queue(maxsize=1)
            publisher._shm_only = False
            with patch.object(
                publisher,
                "_publisher",
                new_callable=AsyncMock,
            ) as worker:
                coroutine = publisher._run_publisher()
                publisher._publisher_task = asyncio.create_task(coroutine)
                await publisher._stop_publisher()
                worker.assert_not_called()
            if publisher._publisher_task is not None:
                pytest.fail("Cancelled worker is still tracked.")

        asyncio.run(check())

    def test_http_websockets_publisher_stops_and_restarts(self) -> None:
        """Stop HTTP/WebSockets workers and keep shared contexts."""
        started_event = Event()
        stopped_event = Event()
        workers: list[asyncio.Task[None]] = []

        async def wait_for_stop() -> None:
            world_output._publisher_ready.set()
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
            failing = Component()
            compound = CompoundComponent(
                {
                    ("world", "output"): world_output,
                    ("sensor", "failing"): failing,
                },
            )
            try:
                with (
                    patch.object(
                        failing,
                        "_start",
                        side_effect=RuntimeError("child startup failed"),
                    ),
                    pytest.raises(RuntimeError, match="child startup"),
                ):
                    compound.start()
                running = (
                    compound.is_started,
                    world_output.is_started,
                    world_output._publisher_task is not None,
                    any(not worker.done() for worker in workers),
                )
                if any(running):
                    pytest.fail("Failed startup left a publisher running.")
                for _attempt in range(2):
                    started_event.clear()
                    stopped_event.clear()
                    compound.start()
                    if (
                        not started_event.wait(2.0)
                        or world_output._publisher_task is None
                    ):
                        pytest.fail(
                            "Publisher did not start or is untracked.",
                        )
                    worker = world_output._publisher_task
                    compound.stop()
                    if (
                        not worker.done()
                        or not stopped_event.is_set()
                        or world_output._publisher_task is not None
                        or close_context.await_count
                    ):
                        pytest.fail("Incorrect stopped task/context state.")
            finally:
                if compound.has_started:
                    compound.stop()
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
            payload_sizes = (1, SHM_DEFAULT_CAPACITY + 1, 1)
            for offset, payload_size in enumerate(payload_sizes):
                received_event.clear()
                session_id = expected_session_id + offset
                message = WorldInputMessage(
                    session_id=session_id,
                    entities={
                        "map_0/vehicle_0": WorldEntityInput(
                            compressed_image=CompressedImage(
                                format="jpeg",
                                data=b"x" * payload_size,
                            ),
                        ),
                    },
                )
                coroutine = topic.publish(
                    message.to_rawdata(),
                    shm_path=str(channel_base) + ".world_input",
                    shm_only=True,
                )
                peer.arun(coroutine, block=True)

                if not received_event.wait(2.0):
                    pytest.fail("Native SHM observation was not delivered.")
                if (
                    received_messages[-1] != message.to_native()
                    or world_input.current_session_id != session_id
                ):
                    pytest.fail(
                        "Native SHM observation was truncated or stale.",
                    )
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
            sessions = range(expected_session_id, expected_session_id + 3)
            for session_id in sessions:
                received_event.clear()
                world_output.start()
                assert (  # noqa: S101
                    world_output._connector.context is not previous_context
                )
                previous_context = world_output._connector.context
                worker = world_output._publisher_task
                assert worker is not None  # noqa: S101
                entity_output = WorldEntityOutput(
                    differential_pwm=DifferentialPWM(left=0.1, right=0.2),
                )
                is_large_payload = session_id == expected_session_id + 1
                entity_count = 2**14 if is_large_payload else 1
                message = WorldOutputMessage(
                    session_id=session_id,
                    entities={
                        f"map_0/vehicle_{index}": entity_output
                        for index in range(entity_count)
                    },
                )
                raw_data = message.to_rawdata()
                if (
                    is_large_payload
                    and len(raw_data.content) <= SHM_DEFAULT_CAPACITY
                ):
                    pytest.fail(
                        "Large action fixture does not exceed SHM capacity.",
                    )
                world_output.publish(message)
                assert received_event.wait(2.0)  # noqa: S101
                received_message = WorldOutputMessage.from_rawdata(
                    received_payloads[-1],
                )
                if received_message != message:
                    pytest.fail("Native SHM actions were truncated or stale.")
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
