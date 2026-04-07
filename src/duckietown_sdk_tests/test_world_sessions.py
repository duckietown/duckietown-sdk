"""Regression tests for world-side session propagation in the SDK."""

import unittest
from unittest.mock import Mock, PropertyMock, patch

from duckietown.sdk.middleware.dtps.components import DTPSWorldInput
from duckietown.sdk.robots.duckiebot import DB21M
from duckietown.sdk.robots.generic_vehicle import GenericVehicle


class WorldSessionTests(unittest.TestCase):
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
