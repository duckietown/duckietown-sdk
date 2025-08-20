"""Test state."""

import time

from duckietown.sdk.robots.duckiebot import DB21J

SIMULATED_ROBOT_NAME = "map_0/vehicle_0"
robot = DB21J(SIMULATED_ROBOT_NAME, simulated=True)
robot.pose.start()
pose = robot.pose.capture(block=True)
if pose is not None:
    position = pose["position"]
    rotation = pose["rotation"]
    print({
        "position": {
            "x": position["x"],
            "y": position["y"],
            "z": position["z"]
        },
        "rotation": {
            "w": rotation["w"],
            "x": rotation["x"],
            "y": rotation["y"],
            "z": rotation["z"]
        }
    })
robot.reset_flag.start()
robot.reset_flag.publish(True)
time.sleep(1)
robot.reset_flag.stop()
pose = robot.pose.capture(block=True)
if pose is not None:
    position = pose["position"]
    rotation = pose["rotation"]
    print({
        "position": {
            "x": position["x"],
            "y": position["y"],
            "z": position["z"]
        },
        "rotation": {
            "w": rotation["w"],
            "x": rotation["x"],
            "y": rotation["y"],
            "z": rotation["z"]
        }
    })
robot.pose.stop()
