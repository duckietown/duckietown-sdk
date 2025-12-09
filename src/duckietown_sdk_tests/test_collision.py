"""Test collision."""

import time

from duckietown.sdk.robots.duckiebot import DB21J

SIMULATED_ROBOT_NAME = "map_0/vehicle_0"
robot = DB21J(SIMULATED_ROBOT_NAME, simulated=True)
robot.collision.start()
while True:
    collision = robot.collision.get(block=True)
    if collision is not None:
        print(collision)
    time.sleep(1)
