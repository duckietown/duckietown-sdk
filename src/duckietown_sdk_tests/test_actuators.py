import time
from typing import Tuple, List

from duckietown.sdk.robots.duckiebot import DB21J
from duckietown.sdk.types import LEDsPattern, RGBAColor

SIMULATED_ROBOT_NAME: str = "map_0/vehicle_0"
REAL_ROBOT_NAME: str = "db21j3"


# MOTORS ###############################################################################################################

def _motors(robot: DB21J):
    speeds: Tuple[float, float] = (0.5, 0.5)
    robot.motors.start()
    stime: float = time.time()
    while time.time() - stime < 2:
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
    off: RGBAColor = (0, 0, 0, 0.0)
    amber: RGBAColor = (1, 0.7, 0, 1.0)
    lights_on: LEDsPattern = LEDsPattern(front_left=amber, front_right=amber, rear_right=amber, rear_left=amber)
    lights_off: LEDsPattern = LEDsPattern(front_left=off, front_right=off, rear_right=off, rear_left=off)
    pattern: List[LEDsPattern] = [lights_on, lights_off]
    robot.lights.start()
    stime: float = time.time()
    i: int = 0
    while time.time() - stime < 8:
        lights: LEDsPattern = pattern[i % 2]
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
    simulated_motors()
    # real_motors()

    # lights
    # simulated_lights()
    # real_lights()

