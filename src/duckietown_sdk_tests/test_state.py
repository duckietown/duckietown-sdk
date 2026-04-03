"""Test state."""

import time

from duckietown.sdk.robots.duckiebot import DB21J

SIMULATED_ROBOT_NAME = "map_0/vehicle_0"
robot = DB21J(SIMULATED_ROBOT_NAME, simulated=True)
robot.pose.start()
robot.state_reset_flag.start()
pose = robot.pose.get(block=True)
if pose is not None:
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
robot.state_reset_flag.set()
time.sleep(5)
pose = robot.pose.get(block=True)
if pose is not None:
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
robot.pose.stop()
robot.state_reset_flag.stop()
