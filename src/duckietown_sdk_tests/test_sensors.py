"""Test sensors."""

import time

import numpy as np

from duckietown.sdk.middleware.components import WheelEncoder
from duckietown.sdk.robots.duckiebot import DB21J

SIMULATED_ROBOT_NAME = "map_0/vehicle_0"
REAL_ROBOT_NAME = "db21j3"


# CAMERA ###############################################################

# ---- Async -----------------------------------------------------------


def _camera_cb(data: np.ndarray | None) -> None:
    if data is None:
        print("No image received.")
        return
    print(f"Received image of shape: {data.shape}")


def _camera_async(robot: DB21J) -> None:
    robot.camera.attach(_camera_cb)
    try:
        robot.camera.start()
        time.sleep(2)
    finally:
        print("Stopped.")
        robot.camera.stop()


def simulated_camera_async() -> None:
    """Measure the simulated camera asynchronously."""
    robot = DB21J(SIMULATED_ROBOT_NAME, simulated=True)
    _camera_async(robot)


def real_camera_async() -> None:
    """Measure the real camera asynchronously."""
    robot = DB21J(REAL_ROBOT_NAME)
    _camera_async(robot)


# ---- Sync ------------------------------------------------------------


def _camera_sync(robot: DB21J) -> None:
    duration = 2
    robot.camera.start()
    try:
        start_time = time.time()
        while time.time() - start_time < duration:
            data = robot.camera.get(block=True)
            _camera_cb(data)
    finally:
        print("Stopped.")
        robot.camera.stop()


def simulated_camera_sync() -> None:
    """Measure the simulated camera synchronously."""
    robot = DB21J(SIMULATED_ROBOT_NAME, simulated=True)
    _camera_sync(robot)


def real_camera_sync() -> None:
    """Measure the real camera synchronously."""
    robot = DB21J(REAL_ROBOT_NAME)
    _camera_sync(robot)


# TIME-OF-FLIGHT SENSOR ################################################

# ---- Async -----------------------------------------------------------


def _time_of_flight_cb(data: float | None) -> None:
    if data is None:
        print("No time-of-flight data received.")
        return
    print(f"Range: {data} meters.")


def _time_of_flight_async(robot: DB21J) -> None:
    robot.time_of_flight_sensor.attach(_time_of_flight_cb)
    try:
        robot.time_of_flight_sensor.start()
        time.sleep(10)
    finally:
        print("Stopped.")
        robot.time_of_flight_sensor.stop()


def simulated_time_of_flight_async() -> None:
    """Measure the time-of-flight sensor asynchronously."""
    robot = DB21J(SIMULATED_ROBOT_NAME, simulated=True)
    _time_of_flight_async(robot)


def real_time_of_flight_async() -> None:
    """Measure the time-of-flight sensor asynchronously."""
    robot = DB21J(REAL_ROBOT_NAME)
    _time_of_flight_async(robot)


# ---- Sync ------------------------------------------------------------


def _time_of_flight_sync(robot: DB21J) -> None:
    duration = 2
    robot.time_of_flight_sensor.start()
    try:
        start_time = time.time()
        while time.time() - start_time < duration:
            data = robot.time_of_flight_sensor.get(block=True)
            _time_of_flight_cb(data)
    finally:
        print("Stopped.")
        robot.time_of_flight_sensor.stop()


def simulated_time_of_flight_sync() -> None:
    """Measure the time-of-flight sensor synchronously."""
    robot = DB21J(SIMULATED_ROBOT_NAME, simulated=True)
    _time_of_flight_sync(robot)


def real_time_of_flight_sync() -> None:
    """Measure the time-of-flight sensor synchronously."""
    robot = DB21J(REAL_ROBOT_NAME)
    _time_of_flight_sync(robot)


# WHEEL ENCODERS #######################################################

# ---- Async -----------------------------------------------------------


def _wheel_encoder_cb(data: int | None) -> None:
    if data is None:
        print("No wheel encoder data received.")
        return
    print(f"Ticks: {data}")


def _wheel_encoder_async(wheel_encoder: WheelEncoder) -> None:
    wheel_encoder.attach(_wheel_encoder_cb)
    try:
        wheel_encoder.start()
        time.sleep(10)
    finally:
        print("Stopped.")
        wheel_encoder.stop()


def simulated_left_wheel_encoder_async() -> None:
    """Measure the left wheel encoder asynchronously."""
    robot = DB21J(SIMULATED_ROBOT_NAME, simulated=True)
    _wheel_encoder_async(robot.left_wheel_encoder)


def real_left_wheel_encoder_async() -> None:
    """Measure the left wheel encoder asynchronously."""
    robot = DB21J(REAL_ROBOT_NAME)
    _wheel_encoder_async(robot.left_wheel_encoder)


def simulated_right_wheel_encoder_async() -> None:
    """Measure the right wheel encoder asynchronously."""
    robot = DB21J(SIMULATED_ROBOT_NAME, simulated=True)
    _wheel_encoder_async(robot.right_wheel_encoder)


def real_right_wheel_encoder_async() -> None:
    """Measure the right wheel encoder asynchronously."""
    robot = DB21J(REAL_ROBOT_NAME)
    _wheel_encoder_async(robot.right_wheel_encoder)


# ---- Sync ------------------------------------------------------------


def _wheel_encoder_sync(wheel_encoder: WheelEncoder) -> None:
    duration = 2
    wheel_encoder.start()
    try:
        start_time = time.time()
        while time.time() - start_time < duration:
            data = wheel_encoder.get(block=True)
            _wheel_encoder_cb(data)
    finally:
        print("Stopped.")
        wheel_encoder.stop()


def simulated_left_wheel_encoder_sync() -> None:
    """Measure the left wheel encoder synchronously."""
    robot = DB21J(SIMULATED_ROBOT_NAME, simulated=True)
    _wheel_encoder_sync(robot.left_wheel_encoder)


def real_left_wheel_encoder_sync() -> None:
    """Measure the real left wheel encoder synchronously."""
    robot = DB21J(REAL_ROBOT_NAME)
    _wheel_encoder_sync(robot.left_wheel_encoder)


def simulated_right_wheel_encoder_sync() -> None:
    """Measure the right wheel encoder synchronously."""
    robot = DB21J(SIMULATED_ROBOT_NAME, simulated=True)
    _wheel_encoder_sync(robot.right_wheel_encoder)


def real_right_wheel_encoder_sync() -> None:
    """Measure the right wheel encoder synchronously."""
    robot = DB21J(REAL_ROBOT_NAME)
    _wheel_encoder_sync(robot.right_wheel_encoder)


# INERTIAL MEASUREMENT UNIT ############################################

# ---- Async -----------------------------------------------------------


def _inertial_measurement_unit_cb(data: dict | None) -> None:
    if data is None:
        print("No inertial measurement data received.")
        return
    print(f"Inertial Measurement Unit data: {data}")


def _inertial_measurement_unit_async(robot: DB21J) -> None:
    robot.inertial_measurement_unit.attach(
        _inertial_measurement_unit_cb,
    )
    try:
        robot.inertial_measurement_unit.start()
        time.sleep(10)
    finally:
        print("Stopped.")
        robot.inertial_measurement_unit.stop()


def simulated_inertial_measurement_unit_async() -> None:
    """Measure the inertial measurement unit asynchronously."""
    robot = DB21J(SIMULATED_ROBOT_NAME, simulated=True)
    _inertial_measurement_unit_async(robot)


def real_inertial_measurement_unit_async() -> None:
    """Measure the inertial measurement unit asynchronously."""
    robot = DB21J(REAL_ROBOT_NAME)
    _inertial_measurement_unit_async(robot)


# ---- Sync ------------------------------------------------------------


def _inertial_measurement_unit_sync(robot: DB21J) -> None:
    duration = 2
    robot.inertial_measurement_unit.start()
    try:
        start_time = time.time()
        while time.time() - start_time < duration:
            data = robot.inertial_measurement_unit.get(block=True)
            _inertial_measurement_unit_cb(data)
    finally:
        print("Stopped.")
        robot.inertial_measurement_unit.stop()


def simulated_inertial_measurement_unit_sync() -> None:
    """Measure the inertial measurement unit synchronously."""
    robot = DB21J(SIMULATED_ROBOT_NAME, simulated=True)
    _inertial_measurement_unit_sync(robot)


def real_inertial_measurement_unit_sync() -> None:
    """Measure the inertial measurement unit synchronously."""
    robot = DB21J(REAL_ROBOT_NAME)
    _inertial_measurement_unit_sync(robot)


########################################################################


if __name__ == "__main__":
    pass

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

    # wheel encoder - left
    # - async
    # simulated_left_wheel_encoder_async()
    # real_left_wheel_encoder_async()
    # - sync
    # simulated_left_wheel_encoder_sync()
    # real_left_wheel_encoder_sync()

    # wheel encoder - right
    # - async
    # simulated_right_wheel_encoder_async()
    # real_right_wheel_encoder_async()
    # - sync
    # simulated_right_wheel_encoder_sync()
    # real_right_wheel_encoder_sync()

    # inertial measurement unit
    # - async
    # simulated_inertial_measurement_unit_async()
    # real_inertial_measurement_unit_async()
    # - sync
    # simulated_inertial_measurement_unit_sync()
    # real_inertial_measurement_unit_sync()
