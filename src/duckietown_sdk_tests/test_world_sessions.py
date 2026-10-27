"""Regression tests for world-side session propagation in the SDK."""

import asyncio
import math
import threading
import unittest
from collections.abc import Coroutine
from types import TracebackType
from typing import Any, cast
from unittest.mock import AsyncMock, Mock, PropertyMock, patch

import numpy as np
import pytest
from dtps_http import RawData

from duckietown.sdk.middleware.dtps.base import (
    DTPS,
    DTPSConnector,
    GenericDTPSPublisher,
    _attach_dtps_timing_metadata,
    _get_dtps_timing_metadata,
    _strip_dtps_timing_metadata,
)
from duckietown.sdk.middleware.dtps.components import (
    DTPSMotorsDriver,
    DTPSWorldInput,
)
from duckietown.sdk.middleware.timing_profiler import TimingProfiler
from duckietown.sdk.robots.duckiebot import DB21M
from duckietown.sdk.robots.generic_vehicle import GenericVehicle
from duckietown.sdk.types import Component
from duckietown.sdk.utils.lane_position import (
    LanePositionCalculator,
    MapInterpreter,
    bezier_point,
    bezier_tangent,
)


class _LegacyLoopBoundQueue:
    def __init__(self, maxsize: int) -> None:
        self._loop = asyncio.get_event_loop()
        self._items: list[object] = []
        self._getters: list[asyncio.Future[object]] = []
        self._maxsize = maxsize

    def _assert_loop(self) -> None:
        if asyncio.get_running_loop() is not self._loop:
            message = "Task got Future attached to a different loop"
            raise RuntimeError(message)

    async def get(self) -> object:
        self._assert_loop()
        if self._items:
            return self._items.pop(0)
        future: asyncio.Future[object] = self._loop.create_future()
        self._getters.append(future)
        return await future

    async def put(self, item: object) -> None:
        self._assert_loop()
        if self._getters:
            getter = self._getters.pop(0)
            if not getter.done():
                getter.set_result(item)
            return
        self._items.append(item)


class _FakePublisher:
    async def publish(self, _raw_data: RawData) -> None:
        return None


class _FakePublisherContext:
    async def __aenter__(self) -> _FakePublisher:
        return _FakePublisher()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback_: TracebackType | None,
    ) -> None:
        return None


class _FakeTopic:
    def publisher_context(self) -> _FakePublisherContext:
        return _FakePublisherContext()


class _FakeContext:
    def navigate(self, *_args: str) -> _FakeTopic:
        return _FakeTopic()


class _InspectableConnector(DTPSConnector):
    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        super().__init__(cast("Any", _FakeContext()), loop)
        self.futures: list[Any] = []

    def arun(
        self,
        coroutine: Coroutine[Any, Any, Any],
        *,
        block: bool = False,
        timeout: float = 1,
    ) -> object:
        coroutine = self._task(coroutine)
        future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        self.futures.append(future)
        if block:
            return future.result(timeout=timeout)
        return None


class WorldSessionTests(unittest.TestCase):
    """Verify session IDs, vehicle outputs, and connector loops."""

    def test_lane_grid_uses_centered_tile_coordinates(self) -> None:
        """Keep both halves of a tile in the same grid cell."""
        calculator = LanePositionCalculator(Mock(road_tile_size=0.585))
        for offset in (-0.2, 0.2):
            position = np.array([offset * 0.585, 0, 0.585])
            self.assertEqual(calculator.get_grid_coords(position), (0, 1))

    def test_lane_curve_has_correct_radii_and_unit_alignment(self) -> None:
        """Connect circular corner lanes to canonical top/left edges."""
        size = 0.585
        map_data = {
            "frames": {"data": {"map_0/tile_0_0": {
                "pose": {"x": 0.0, "y": 0.0, "yaw": 0.0},
            }}},
            "tiles": {"data": {"map_0/tile_0_0": {"type": "curve"}}},
            "tile_info": {"data": {"map_0": {"tile_size": {"x": size}}}},
        }
        interpreter = MapInterpreter(map_data)
        calculator = LanePositionCalculator(interpreter)
        tile = interpreter.get_tile(0, 0)
        if tile is None:
            pytest.fail("Corner tile was not loaded.")
        center = np.array([-0.5, 0, 0.5]) * size
        endpoints = (
            ([[0.2, 0, 0.5], [-0.5, 0, -0.2]], 0.7),
            ([[-0.5, 0, 0.2], [-0.2, 0, 0.5]], 0.3),
        )
        for curve, (expected, radius) in zip(
            tile["curves"], endpoints, strict=True,
        ):
            expected_endpoints = np.array(expected) * size
            np.testing.assert_allclose(curve[[0, -1]], expected_endpoints)
            position = bezier_point(curve, 0.5)
            measured_radius = float(np.linalg.norm(position - center))
            self.assertAlmostEqual(measured_radius, radius * size)
            tangent = bezier_tangent(curve, 0.5)
            angle = math.atan2(-tangent[2], tangent[0])
            lane = calculator.get_lane_pos2(position, angle)
            self.assertAlmostEqual(lane.dist, 0)
            self.assertAlmostEqual(lane.dot_dir, 1)

    def test_component_finalization_does_not_block_on_stop(self) -> None:
        """Keep blocking shutdown out of component finalizers."""
        with patch.object(Component, "stop") as stop:
            component = Component()
            component.start()
            del component
        stop.assert_not_called()

    def test_network_publish_drops_full_queue(self) -> None:
        """Drop excess commands instead of leaving waiting puts."""
        publisher = GenericDTPSPublisher.__new__(GenericDTPSPublisher)
        first = RawData.cbor_from_native_object({"command": 1})
        second = RawData.cbor_from_native_object({"command": 2})

        async def check() -> None:
            publisher._queue = asyncio.Queue(maxsize=1)
            await publisher._publish_network(first, 1)
            await asyncio.wait_for(
                publisher._publish_network(second, 2),
                timeout=0.1,
            )
            self.assertEqual(publisher._queue.qsize(), 1)
            self.assertEqual(publisher._queue.get_nowait(), (first, 1))
            publisher._queue.task_done()

        asyncio.run(check())

    def test_motors_stop_and_restart_with_nonzero_commands(self) -> None:
        """Clear stop overrides and retire old publisher workers."""
        loop, worker = self._start_loop()
        connector = _InspectableConnector(loop)
        received = threading.Event()
        expected = 0.2

        async def record(raw_data: RawData) -> None:
            payload = raw_data.get_as_native_object()
            if isinstance(payload, dict) and payload.get("left") == expected:
                received.set()

        try:
            with (
                patch.object(DTPS, "get_connector", return_value=connector),
                patch.object(
                    _FakePublisher,
                    "publish",
                    AsyncMock(side_effect=record),
                ),
            ):
                motors = DTPSMotorsDriver("127.0.0.1", 1, "robot", "")
                for pwm in (0.2, 0.3):
                    expected = pwm
                    received.clear()
                    motors.start()
                    try:
                        motors.set(pwm, pwm)
                        if not received.wait(1):
                            pytest.fail("Nonzero motor command was lost.")
                    finally:
                        motors.stop()
                    self.assertIsNone(motors._publisher_task)
        finally:
            self._stop_loop(loop, worker)

    def test_dtps_timing_metadata_round_trips_cleanly(self) -> None:
        """Keep timing metadata separate from callback payloads."""
        payload = {"session_id": 7, "compressed_image": b"\x00\xff"}
        enriched = _attach_dtps_timing_metadata(
            payload,
            engine_send_called_ns=123,
        )
        raw_data = RawData.cbor_from_native_object(enriched)
        received = raw_data.get_as_native_object()
        timing = _get_dtps_timing_metadata(received)
        if timing != {"engine_send_called_ns": 123}:
            pytest.fail("Timing metadata did not survive CBOR serialization.")
        if _strip_dtps_timing_metadata(received) != payload:
            pytest.fail("Timing metadata changed the callback payload.")
        if "__dtps_timing__" in payload:
            pytest.fail("Attaching timing metadata mutated the input.")

    def test_timing_profiler_handles_empty_and_zero_duration(self) -> None:
        """Log empty and zero-duration samples safely."""
        profiler = TimingProfiler("Test profiling")
        logger = Mock()
        profiler.log(logger)
        logger.info.assert_not_called()
        profiler.enable()
        profiler.log(logger)
        logger.info.assert_called_once_with(
            "\n%s:\n(no samples)\n",
            "Test profiling",
        )
        logger.info.reset_mock()
        profiler.observe("zero", 0)
        profiler.log(logger)
        call = logger.info.call_args
        if call is None or "inf" not in call.args[-1]:
            pytest.fail("Zero-duration samples did not log safely.")

    @staticmethod
    def _start_loop() -> tuple[asyncio.AbstractEventLoop, threading.Thread]:
        loop = asyncio.new_event_loop()

        def runner() -> None:
            asyncio.set_event_loop(loop)
            loop.run_forever()

        worker = threading.Thread(target=runner, daemon=True)
        worker.start()
        return loop, worker

    @staticmethod
    def _stop_loop(
        loop: asyncio.AbstractEventLoop,
        worker: threading.Thread,
    ) -> None:
        async def cancel_pending() -> None:
            tasks = [
                task
                for task in asyncio.all_tasks()
                if task is not asyncio.current_task()
            ]
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        try:
            asyncio.run_coroutine_threadsafe(cancel_pending(), loop).result(
                timeout=1,
            )
        finally:
            loop.call_soon_threadsafe(loop.stop)
            worker.join(timeout=1)
            loop.close()

    def test_world_input_tracks_current_session_id(self) -> None:
        """Reject stale or invalid sessions before notifying readers."""
        world_input = DTPSWorldInput(
            "127.0.0.1",
            7501,
            "map_0/vehicle_0",
            "",
        )

        callback = Mock()
        world_input.attach(callback)
        payload = {"session_id": 7, "payload": "ok"}
        world_input._callback(payload)
        self.assertIs(world_input.latest, payload)
        self.assertEqual(world_input.current_session_id, 7)

        for session_id in (7, 6, True, None, "8"):
            world_input._callback({"session_id": session_id})
        world_input._callback({"payload": "missing"})
        self.assertEqual(world_input.current_session_id, 7)
        self.assertIs(world_input.latest, payload)
        callback.assert_called_once_with(payload)
        world_input._callback({"session_id": 8})
        self.assertEqual(world_input.current_session_id, 8)
        self.assertEqual(callback.call_count, 2)

    def test_world_input_keeps_callback_session_stable(self) -> None:
        """Do not advance the session while an older callback runs."""
        world_input = DTPSWorldInput("127.0.0.1", 7501, "gym", "")
        entered = threading.Event()
        release = threading.Event()
        second_completed = threading.Event()
        observed: list[tuple[int, int | None]] = []

        def callback(message: dict) -> None:
            if message["session_id"] == 1:
                entered.set()
                release.wait(1)
            observed.append(
                (message["session_id"], world_input.current_session_id),
            )

        def deliver_second() -> None:
            world_input._callback({"session_id": 2})
            second_completed.set()

        world_input.attach(callback)
        first = threading.Thread(
            target=world_input._callback,
            args=({"session_id": 1},),
        )
        second = threading.Thread(target=deliver_second)
        first.start()
        try:
            self.assertTrue(entered.wait(1))
            second.start()
            self.assertFalse(second_completed.wait(0.05))
            self.assertEqual(world_input.current_session_id, 1)
        finally:
            release.set()
            first.join(timeout=1)
            if second.ident is not None:
                second.join(timeout=1)
        self.assertEqual(observed, [(1, 1), (2, 2)])

    def test_generic_vehicle_does_not_expose_gym_attach_api(self) -> None:
        """Keep Gym callbacks on the environment."""
        vehicle = GenericVehicle(
            "map_0/vehicle_0",
            simulated=True,
            gym_mode=True,
        )

        self.assertFalse(hasattr(vehicle, "attach"))

    def test_db21m_does_not_expose_per_vehicle_gym_step(self) -> None:
        """Keep world stepping on the environment rather than DB21M."""
        vehicle = DB21M(
            "map_0/vehicle_0",
            simulated=True,
            gym_mode=True,
        )

        self.assertFalse(hasattr(vehicle, "step"))

    def test_publisher_queue_is_created_on_connector_loop(self) -> None:
        """Create the queue on the connector loop without a worker."""
        loop, worker = self._start_loop()
        connector = _InspectableConnector(loop)

        try:
            with (
                patch.object(DTPS, "get_connector", return_value=connector),
                patch(
                    "duckietown.sdk.middleware.dtps.base.Queue",
                    _LegacyLoopBoundQueue,
                ),
            ):
                publisher = GenericDTPSPublisher(
                    "127.0.0.1",
                    7501,
                    "map_0/vehicle_0",
                    ("commands",),
                )

            self.assertIsInstance(publisher._queue, _LegacyLoopBoundQueue)
            if len(connector.futures) != 1:
                pytest.fail("Constructor started an extra publisher task.")
            created_queue = connector.futures[0].result(timeout=1)
            if not isinstance(created_queue, _LegacyLoopBoundQueue):
                pytest.fail("Queue was not created on the connector loop.")
        finally:
            self._stop_loop(loop, worker)

    def test_db21m_builds_world_entity_output(self) -> None:
        """Pack both wheel commands into the vehicle's world output."""
        vehicle = DB21M(
            "map_0/vehicle_0",
            simulated=True,
            gym_mode=True,
        )

        entity_output = vehicle.make_world_entity_output(0.3, 0.4)

        self.assertIsNotNone(entity_output.differential_pwm)
        self.assertEqual(entity_output.differential_pwm.left, 0.3)
        self.assertEqual(entity_output.differential_pwm.right, 0.4)

    def test_dtps_duckiebot_components_use_dtps_publishers(self) -> None:
        """Use DTPS publishers for motors, lights, and state reset."""
        vehicle = DB21M(
            "map_0/vehicle_0",
            simulated=True,
        )

        self.assertIs(
            type(vehicle.motors).publish,
            GenericDTPSPublisher.publish,
        )
        self.assertIs(
            type(vehicle.lights).publish,
            GenericDTPSPublisher.publish,
        )
        self.assertIs(
            type(vehicle.state_reset_flag).publish,
            GenericDTPSPublisher.publish,
        )
        self.assertIsNotNone(vehicle.motors.differential_pwm)
        self.assertIsNotNone(vehicle.lights.car_lights)
        self.assertIsNotNone(vehicle.state_reset_flag.boolean)

    def test_generic_vehicle_start_does_not_touch_delta_time(self) -> None:
        """Start map components without creating a time driver."""
        vehicle = GenericVehicle(
            "map_0/vehicle_0",
            simulated=True,
            gym_mode=True,
        )
        map_frames = Mock()
        map_tile_info = Mock()
        map_tiles = Mock()

        with (
            patch.object(
                GenericVehicle,
                "delta_time",
                new_callable=PropertyMock,
                side_effect=AssertionError,
            ),
            patch.object(
                GenericVehicle,
                "map_frames",
                new_callable=PropertyMock,
                return_value=map_frames,
            ),
            patch.object(
                GenericVehicle,
                "map_tile_info",
                new_callable=PropertyMock,
                return_value=map_tile_info,
            ),
            patch.object(
                GenericVehicle,
                "map_tiles",
                new_callable=PropertyMock,
                return_value=map_tiles,
            ),
        ):
            vehicle.start()
            vehicle.stop()

        map_frames.start.assert_called_once_with()
        map_tile_info.start.assert_called_once_with()
        map_tiles.start.assert_called_once_with()
        map_frames.stop.assert_called_once_with()
        map_tile_info.stop.assert_called_once_with()
        map_tiles.stop.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
