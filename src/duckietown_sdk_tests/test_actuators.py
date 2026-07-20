"""Test actuators."""

import time

from duckietown.sdk.robots.duckiebot import DB21J

SIMULATED_ROBOT_NAME = "map_0/vehicle_0"
REAL_ROBOT_NAME = "db21j3"


# MOTORS ###############################################################


def _motors(robot: DB21J) -> None:
    duration = 2
    speeds = (0.5, 0.5)
    robot.motors.start()
    try:
        start_time = time.time()
        while time.time() - start_time < duration:
            print(speeds)
            robot.motors.set(*speeds)
            time.sleep(0.25)
    finally:
        robot.motors.stop()
        print("Stopped.")


def simulated_motors() -> None:
    """Measure the simulated motors."""
    robot = DB21J(SIMULATED_ROBOT_NAME, simulated=True)
    _motors(robot)


def real_motors() -> None:
    """Measure the real motors."""
    robot = DB21J(REAL_ROBOT_NAME)
    _motors(robot)


# LIGHTS ###############################################################


def _lights(robot: DB21J) -> None:
    duration = 8
    frequency = 1.4
    off = (0.0, 0.0, 0.0, 0.0)
    amber = (1.0, 0.7, 0.0, 1.0)
    robot.lights.start()
    try:
        pattern = [amber, off]
        i = 0
        start_time = time.time()
        while time.time() - start_time < duration:
            rgba = pattern[i % 2]
            robot.lights.set(rgba, rgba, rgba, rgba)
            time.sleep(1 / frequency)
            i += 1
    finally:
        robot.lights.stop()
        print("Stopped.")


def simulated_lights() -> None:
    """Measure the simulated lights."""
    robot = DB21J(SIMULATED_ROBOT_NAME, simulated=True)
    _lights(robot)


def real_lights() -> None:
    """Measure the real lights."""
    robot = DB21J(REAL_ROBOT_NAME)
    _lights(robot)


def reset() -> None:
    """Reset the robot state."""
    robot = DB21J(SIMULATED_ROBOT_NAME, simulated=True)
    robot.state_reset_flag.start()
    try:
        robot.state_reset_flag.set()
        time.sleep(5)
    finally:
        robot.state_reset_flag.stop()
