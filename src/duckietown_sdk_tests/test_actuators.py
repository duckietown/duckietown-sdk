"""Test actuators."""

import time

from duckietown_messages.actuators import CarLights
from duckietown_messages.colors import RGBA

from duckietown.sdk.robots.duckiebot import DB21J

SIMULATED_ROBOT_NAME = "map_0/vehicle_0"
REAL_ROBOT_NAME = "db21j3"


# MOTORS ###############################################################


def _motors(robot: DB21J) -> None:
    duration = 2
    speeds = (0.5, 0.5)
    robot.motors.start()
    start_time = time.time()
    while time.time() - start_time < duration:
        print(speeds)
        robot.motors.set(*speeds)
        time.sleep(0.25)
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
    off = RGBA(r=0, g=0, b=0, a=0)
    amber = RGBA(r=1, g=0.7, b=0, a=1)
    lights_on = CarLights(
        front_left=amber,
        front_right=amber,
        back_right=amber,
        back_left=amber,
    )
    lights_off = CarLights(
        front_left=off,
        front_right=off,
        back_right=off,
        back_left=off,
    )
    robot.lights.start()
    pattern = [lights_on, lights_off]
    i = 0
    start_time = time.time()
    while time.time() - start_time < duration:
        lights = pattern[i % 2]
        robot.lights.publish(lights)
        time.sleep(1 / frequency)
        i += 1
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
    robot.state_reset_flag.set()
    time.sleep(5)
