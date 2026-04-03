"""Test all."""

import time
from collections.abc import Callable
from types import NoneType
from typing import TYPE_CHECKING, Any

import numpy as np
from duckietown_messages.actuators import CarLights, DifferentialPWM
from duckietown_messages.colors import RGBA

from duckietown.sdk.robots.duckiebot import DB21M

if TYPE_CHECKING:
    from duckietown.sdk.middleware.base import (
        GenericPublisher,
        GenericSubscriber,
    )

SIMULATED_ROBOT_NAME = "map_0/vehicle_0"
REAL_ROBOT_NAME = "db21j3"


def _process(data: Any, allowed: set[type] | None = None) -> int:
    if allowed is not None and type(data) not in allowed:
        print(f"Received unexpected type: {type(data)}")
        return 0
    # print data
    if isinstance(data, np.ndarray):
        print(f"Received image of shape: {data.shape}")
    elif isinstance(data, float):
        print(f"Received float: {data}")
    # ---
    return 1


def _get_callback(i: int, allowed: set[type]) -> Callable[[Any], None]:
    def callback(data: Any) -> None:
        nonlocal i
        i += _process(data, allowed=allowed)

    return callback


def _measure_sensor_async(
    robot: DB21M,
    component: str,
    allowed: set[type],
) -> None:
    duration = 10
    i = 0
    print("Attaching...")
    source: GenericSubscriber = getattr(robot, component)
    callback = _get_callback(i, allowed)
    source.attach(callback)
    print("Attached.")
    source.start()
    time.sleep(duration)
    print("Stopped.")
    frequency = round(i / duration)
    print(f"Measured: {frequency}Hz")


def _measure_sensor_sync(
    robot: DB21M,
    component: str,
    allowed: set[type],
) -> None:
    duration = 10
    i = 0
    print("Attaching...")
    source: GenericSubscriber = getattr(robot, component)
    source.start()
    start_time = time.time()
    while time.time() - start_time < duration:
        data = source.get(block=True)
        i += _process(data, allowed=allowed)
    print("Stopped.")
    print(f"Measured: {round(i / duration)}Hz")


def _publish(robot: DB21M, component: str, data: Any, period: float) -> None:
    duration = 4
    sink: GenericPublisher = getattr(robot, component)
    sink.start()
    start_time = time.time()
    while time.time() - start_time < duration:
        sink.publish(data=data)
        time.sleep(period)


def simulated_camera_async() -> None:
    """Measure the simulated camera asynchronously."""
    robot = DB21M(SIMULATED_ROBOT_NAME, simulated=True)
    _measure_sensor_async(robot, "camera", {np.ndarray})


def real_camera_async() -> None:
    """Measure the real camera asynchronously."""
    robot = DB21M(REAL_ROBOT_NAME)
    _measure_sensor_async(robot, "camera", {np.ndarray})


def simulated_camera_sync() -> None:
    """Measure the simulated camera synchronously."""
    robot = DB21M(SIMULATED_ROBOT_NAME, simulated=True)
    _measure_sensor_sync(robot, "camera", {np.ndarray})


def real_camera_sync() -> None:
    """Measure the real camera synchronously."""
    robot = DB21M(REAL_ROBOT_NAME)
    _measure_sensor_sync(robot, "camera", {np.ndarray})


def simulated_time_of_flight_async() -> None:
    """Measure the simulated time-of-flight sensor asynchronously."""
    robot = DB21M(SIMULATED_ROBOT_NAME, simulated=True)
    _measure_sensor_async(robot, "time_of_flight", {float, NoneType})


def real_time_of_flight_async() -> None:
    """Measure the real time-of-flight sensor asynchronously."""
    robot = DB21M(REAL_ROBOT_NAME)
    _measure_sensor_async(robot, "time_of_flight", {float, NoneType})


def simulated_time_of_flight_sync() -> None:
    """Measure the simulated time-of-flight sensor synchronously."""
    robot = DB21M(SIMULATED_ROBOT_NAME, simulated=True)
    _measure_sensor_sync(robot, "time_of_flight", {float, NoneType})


def real_time_of_flight_sync() -> None:
    """Measure the real time-of-flight sensor synchronously."""
    robot = DB21M(REAL_ROBOT_NAME)
    _measure_sensor_sync(robot, "time_of_flight", {float, NoneType})


def simulated_left_wheel_encoder_async() -> None:
    """Measure the simulated left wheel encoder asynchronously."""
    robot = DB21M(SIMULATED_ROBOT_NAME, simulated=True)
    _measure_sensor_async(robot, "left_wheel_encoder", {float})


def real_left_wheel_encoder_async() -> None:
    """Measure the real left wheel encoder asynchronously."""
    robot = DB21M(REAL_ROBOT_NAME)
    _measure_sensor_async(robot, "left_wheel_encoder", {float})


def simulated_left_wheel_encoder_sync() -> None:
    """Measure the simulated left wheel encoder synchronously."""
    robot = DB21M(SIMULATED_ROBOT_NAME, simulated=True)
    _measure_sensor_sync(robot, "left_wheel_encoder", {float})


def real_left_wheel_encoder_sync() -> None:
    """Measure the real left wheel encoder synchronously."""
    robot = DB21M(REAL_ROBOT_NAME)
    _measure_sensor_sync(robot, "left_wheel_encoder", {float})


def simulated_right_wheel_encoder_async() -> None:
    """Measure the simulated right wheel encoder asynchronously."""
    robot = DB21M(SIMULATED_ROBOT_NAME, simulated=True)
    _measure_sensor_async(robot, "right_wheel_encoder", {float})


def real_right_wheel_encoder_async() -> None:
    """Measure the real right wheel encoder asynchronously."""
    robot = DB21M(REAL_ROBOT_NAME)
    _measure_sensor_async(robot, "right_wheel_encoder", {float})


def simulated_right_wheel_encoder_sync() -> None:
    """Measure the simulated right wheel encoder synchronously."""
    robot = DB21M(SIMULATED_ROBOT_NAME, simulated=True)
    _measure_sensor_sync(robot, "right_wheel_encoder", {float})


def real_right_wheel_encoder_sync() -> None:
    """Measure the real right wheel encoder synchronously."""
    robot = DB21M(REAL_ROBOT_NAME)
    _measure_sensor_sync(robot, "right_wheel_encoder", {float})


def simulated_motors() -> None:
    """Measure the simulated motors."""
    robot = DB21M(SIMULATED_ROBOT_NAME, simulated=True)
    differential_pwm = DifferentialPWM(left=0.5, right=0.5)
    _publish(robot, "motors", differential_pwm, 0.1)


def real_motors() -> None:
    """Measure the real motors."""
    robot = DB21M(REAL_ROBOT_NAME)
    differential_pwm = DifferentialPWM(left=0.5, right=0.5)
    _publish(robot, "motors", differential_pwm, 0.1)


def simulated_lights() -> None:
    """Measure the simulated lights."""
    robot = DB21M(SIMULATED_ROBOT_NAME, simulated=True)
    amber = RGBA(r=1, g=0.7, b=0, a=1)
    lights = CarLights(
        front_left=amber,
        front_right=amber,
        back_left=amber,
        back_right=amber,
    )
    _publish(robot, "lights", lights, 0.1)


def real_lights() -> None:
    """Measure the real lights."""
    robot = DB21M(REAL_ROBOT_NAME)
    amber = RGBA(r=1, g=0.7, b=0, a=1)
    lights = CarLights(
        front_left=amber,
        front_right=amber,
        back_left=amber,
        back_right=amber,
    )
    _publish(robot, "lights", lights, 1)


if __name__ == "__main__":
    # camera
    # - async
    # simulated_camera_async()
    # real_camera_async()
    # - sync
    # simulated_camera_sync()
    # real_camera_sync()

    # time-of-flight sensor
    # - async
    # simulated_time_of_flight_async()
    # real_time_of_flight_async()
    # - sync
    # simulated_time_of_flight_sync()
    # real_time_of_flight_sync()

    # left wheel encoder
    # - async
    # simulated_left_wheel_encoder_async()
    # real_left_wheel_encoder_async()
    # - sync
    # simulated_left_wheel_encoder_sync()
    # real_left_wheel_encoder_sync()

    # right wheel encoder
    # - async
    # simulated_right_wheel_encoder_async()
    # real_right_wheel_encoder_async()
    # - sync
    # simulated_right_wheel_encoder_sync()
    # real_right_wheel_encoder_sync()

    # motors
    # simulated_motors()
    # real_motors()

    # lights
    # simulated_lights()
    real_lights()
