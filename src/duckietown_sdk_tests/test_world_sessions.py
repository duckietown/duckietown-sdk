"""Regression tests for world-side session propagation in the SDK."""

import unittest

from duckietown.sdk.middleware.dtps.components import DTPSWorldInput
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

    def test_generic_vehicle_prepares_world_output_from_world_input(
        self,
    ) -> None:
        vehicle = GenericVehicle(
            "map_0/vehicle_0",
            simulated=True,
            gym_mode=True,
        )
        vehicle._world_input.current_session_id = 12

        vehicle._prepare_world_output(123.0)

        self.assertEqual(vehicle.world_output.header.timestamp, 123.0)
        self.assertEqual(vehicle.world_output.session_id, 12)

    def test_generic_vehicle_requires_world_session_before_output(
        self,
    ) -> None:
        vehicle = GenericVehicle(
            "map_0/vehicle_0",
            simulated=True,
            gym_mode=True,
        )

        with self.assertRaisesRegex(RuntimeError, "with a session_id"):
            vehicle._prepare_world_output(123.0)


if __name__ == "__main__":
    unittest.main()
