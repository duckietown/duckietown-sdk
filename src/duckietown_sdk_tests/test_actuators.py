import time
from typing import Tuple, List

from duckietown.sdk.robots.duckiebot import DB21J
from duckietown_messages.actuators import CarLights
from duckietown_messages.colors import RGBA

SIMULATED_ROBOT_NAME: str = "map_0/vehicle_0"
REAL_ROBOT_NAME: str = "db21j3"


# MOTORS ###############################################################################################################

def _motors(robot: DB21J):
    speeds: Tuple[float, float] = (0.5, 0.5)
    robot.motors.start()
    stime: float = time.time()
    while time.time() - stime < 2:
        print(speeds)
        robot.motors.publish(speeds)
        time.sleep(0.25)
    robot.motors.stop()
    print("Stopped.")


def simulated_motors():
    robot: DB21J = DB21J(SIMULATED_ROBOT_NAME, simulated=True)
    _motors(robot)


def real_motors():
    robot: DB21J = DB21J(REAL_ROBOT_NAME)
    _motors(robot)


# LIGHTS ###############################################################################################################

def _lights(robot: DB21J):
    frequency: float = 1.4
    off: RGBA = RGBA(r=0, g=0, b=0, a=0.0)
    amber: RGBA = RGBA(r=1, g=0.7, b=0, a=1.0)
    lights_on: CarLights = CarLights(front_left=amber, front_right=amber, back_right=amber, back_left=amber)
    lights_off: CarLights = CarLights(front_left=off, front_right=off, back_right=off, back_left=off)
    robot.lights.start()
    pattern: List[CarLights] = [lights_on, lights_off]
    stime: float = time.time()
    i: int = 0
    while time.time() - stime < 8:
        lights: CarLights = pattern[i % 2]
        robot.lights.publish(lights)
        time.sleep(1. / frequency)
        i += 1
    robot.lights.stop()
    print("Stopped.")


def simulated_lights():
    robot: DB21J = DB21J(SIMULATED_ROBOT_NAME, simulated=True)
    _lights(robot)


def real_lights():
    robot: DB21J = DB21J(REAL_ROBOT_NAME)
    _lights(robot)


if __name__ == '__main__':
    pass

    # motors
    # simulated_motors()
    # real_motors()

    # lights
    simulated_lights()
    # real_lights()

