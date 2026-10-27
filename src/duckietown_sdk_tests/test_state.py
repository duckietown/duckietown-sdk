"""Test state."""

import time
from typing import Any

from duckietown.sdk.robots.duckiebot import DB21J

SIMULATED_ROBOT_NAME = "map_0/vehicle_0"


def _print_pose(pose: dict[str, Any] | None) -> None:
    if pose is None:
        print("No pose received.")
        return
    position = pose["position"]
    rotation = pose["rotation"]
    print(
        {
            "position": {
                "x": position["x"],
                "y": position["y"],
                "z": position["z"],
            },
            "rotation": {
                "w": rotation["w"],
                "x": rotation["x"],
                "y": rotation["y"],
                "z": rotation["z"],
            },
        },
    )


def simulated_state_reset() -> None:
    """Print the simulated pose, trigger a reset, and print it again."""
    robot = DB21J(SIMULATED_ROBOT_NAME, simulated=True)
    robot.pose.start()
    robot.state_reset_flag.start()
    try:
        _print_pose(robot.pose.get(block=True))
        robot.state_reset_flag.set()
        time.sleep(5)
        _print_pose(robot.pose.get(block=True))
    finally:
        robot.pose.stop()
        robot.state_reset_flag.stop()


if __name__ == "__main__":
    simulated_state_reset()
