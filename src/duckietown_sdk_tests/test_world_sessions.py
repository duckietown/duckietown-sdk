"""Regression tests for world-side session propagation in the SDK."""

import asyncio
import threading
import unittest
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Any, cast
from unittest.mock import Mock, PropertyMock, patch

from duckietown.sdk.middleware.dtps.base import (
    DTPS,
    DTPSConnector,
    GenericDTPSPublisher,
    _attach_dtps_timing_metadata,
    _strip_dtps_timing_metadata,
)
from duckietown.sdk.middleware.dtps.components import DTPSWorldInput
from duckietown.sdk.robots.duckiebot import DB21M
from duckietown.sdk.robots.generic_vehicle import GenericVehicle


class _LegacyLoopBoundQueue:
    def __init__(self, maxsize: int) -> None:
        self._loop = asyncio.get_event_loop()
        self._items: list[Any] = []
        self._getters: list[asyncio.Future[Any]] = []
        self._maxsize = maxsize

    def _assert_loop(self) -> None:
        if asyncio.get_running_loop() is not self._loop:
            message = "Task got Future attached to a different loop"
            raise RuntimeError(message)

    async def get(self):
        self._assert_loop()
        if self._items:
            return self._items.pop(0)
        future = self._loop.create_future()
        self._getters.append(future)
        return await future

    async def put(self, item) -> None:
        self._assert_loop()
        if self._getters:
            getter = self._getters.pop(0)
            if not getter.done():
                getter.set_result(item)
            return
        self._items.append(item)


class _FakePublisher:
    async def publish(self, _raw_data) -> None:
        return None


class _FakePublisherContext:
    async def __aenter__(self) -> _FakePublisher:
        return _FakePublisher()

    async def __aexit__(self, exc_type, exc, traceback_) -> None:  # noqa: ANN001
        return None


class _FakeTopic:
    def publisher_context(self) -> _FakePublisherContext:
        return _FakePublisherContext()


class _FakeContext:
    def navigate(self, *_args) -> _FakeTopic:
        return _FakeTopic()


class _InspectableConnector(DTPSConnector):
    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        super().__init__(cast("Any", _FakeContext()), loop)
        self.futures: list[Any] = []

    def arun(self, coroutine, *, block: bool = False):  # noqa: ANN001
        coroutine = self._task(coroutine)
        future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        self.futures.append(future)
        if block:
            return future.result(timeout=1)
        return None


class WorldSessionTests(unittest.TestCase):
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

    def test_dtps_timing_metadata_round_trips_cleanly(self) -> None:
        payload = {"session_id": 7, "payload": "ok"}

        enriched = _attach_dtps_timing_metadata(
            payload,
            engine_send_called_ns=123,
        )

        self.assertEqual(enriched["session_id"], 7)
        self.assertEqual(enriched["payload"], "ok")
        self.assertIn("__dtps_timing__", enriched)
        self.assertEqual(
            enriched["__dtps_timing__"]["engine_send_called_ns"],
            123,
        )
        self.assertEqual(_strip_dtps_timing_metadata(enriched), payload)

    def test_world_input_tracks_current_session_id(self) -> None:
        world_input = DTPSWorldInput(
            "127.0.0.1",
            7501,
            "map_0/vehicle_0",
            "",
        )

        payload = {"session_id": 7, "payload": "ok"}
        unpacked = world_input._unpack(payload)
        self.assertIs(unpacked, payload)
        self.assertEqual(world_input.current_session_id, 7)

        world_input._unpack({"payload": "missing"})
        self.assertIsNone(world_input.current_session_id)

    def test_generic_vehicle_does_not_expose_gym_attach_api(self) -> None:
        vehicle = GenericVehicle(
            "map_0/vehicle_0",
            simulated=True,
            gym_mode=True,
        )

        self.assertFalse(hasattr(vehicle, "attach"))

    def test_db21m_does_not_expose_per_vehicle_gym_step(self) -> None:
        vehicle = DB21M(
            "map_0/vehicle_0",
            simulated=True,
            gym_mode=True,
        )

        self.assertFalse(hasattr(vehicle, "step"))

    def test_publisher_queue_is_created_on_connector_loop(self) -> None:
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
            self.assertEqual(len(connector.futures), 2)
            with self.assertRaises(FutureTimeoutError):
                connector.futures[-1].result(timeout=0.2)
        finally:
            self._stop_loop(loop, worker)

    def test_db21m_builds_world_entity_output(self) -> None:
        vehicle = DB21M(
            "map_0/vehicle_0",
            simulated=True,
            gym_mode=True,
        )

        entity_output = vehicle.make_world_entity_output(0.3, 0.4)

        self.assertIsNotNone(entity_output.differential_pwm)
        self.assertEqual(entity_output.differential_pwm.left, 0.3)
        self.assertEqual(entity_output.differential_pwm.right, 0.4)

    def test_generic_vehicle_start_does_not_touch_delta_time(self) -> None:
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
