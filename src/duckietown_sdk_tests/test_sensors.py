import time
from typing import Optional

from duckietown.sdk.middleware.base import WheelEncoderDriver

from duckietown.sdk.robots.duckiebot import DB21J
from duckietown.sdk.types import BGRImage

SIMULATED_ROBOT_NAME: str = "map_0/vehicle_0"
REAL_ROBOT_NAME: str = "db21j3"


# CAMERA ###############################################################################################################

# ---- Async -----------------------------------------------------------------------------------------------------------

def _camera_cb(data: BGRImage):
    print(f"Received image of shape: {data.shape}")


def _camera_async(robot: DB21J):
    robot.camera.attach(_camera_cb)
    robot.camera.start()
    time.sleep(2)
    print("Stopped.")
    robot.camera.stop()


def simulated_camera_async():
    robot: DB21J = DB21J(SIMULATED_ROBOT_NAME, simulated=True)
    _camera_async(robot)


def real_camera_async():
    robot: DB21J = DB21J(REAL_ROBOT_NAME)
    _camera_async(robot)


# ---- Sync ------------------------------------------------------------------------------------------------------------

def _camera_sync(robot: DB21J):
    robot.camera.start()
    stime: float = time.time()
    while time.time() - stime < 2:
        data = robot.camera.capture(block=True)
        _camera_cb(data)
    print("Stopped.")
    robot.camera.stop()


def simulated_camera_sync():
    robot: DB21J = DB21J(SIMULATED_ROBOT_NAME, simulated=True)
    _camera_sync(robot)


def real_camera_sync():
    robot: DB21J = DB21J(REAL_ROBOT_NAME)
    _camera_sync(robot)


# RANGE FINDER #########################################################################################################

# ---- Async -----------------------------------------------------------------------------------------------------------

def _range_finder_cb(data: Optional[float]):
    if data is None:
        print("Out of range.")
        return
    print(f"Range: {data} meters.")


def _range_finder_async(robot: DB21J):
    robot.range_finder.attach(_range_finder_cb)
    robot.range_finder.start()
    time.sleep(10)
    print("Stopped.")
    robot.range_finder.stop()


def simulated_range_finder_async():
    robot: DB21J = DB21J(SIMULATED_ROBOT_NAME, simulated=True)
    _range_finder_async(robot)


def real_range_finder_async():
    robot: DB21J = DB21J(REAL_ROBOT_NAME)
    _range_finder_async(robot)


# ---- Sync ------------------------------------------------------------------------------------------------------------

def _range_finder_sync(robot: DB21J):
    robot.range_finder.start()
    stime: float = time.time()
    while time.time() - stime < 2:
        data = robot.range_finder.capture(block=True)
        _range_finder_cb(data)
    print("Stopped.")
    robot.range_finder.stop()


def simulated_range_finder_sync():
    robot: DB21J = DB21J(SIMULATED_ROBOT_NAME, simulated=True)
    _range_finder_sync(robot)


def real_range_finder_sync():
    robot: DB21J = DB21J(REAL_ROBOT_NAME)
    _range_finder_sync(robot)


# WHEEL ENCODERS #########################################################################################################

# ---- Async -----------------------------------------------------------------------------------------------------------

def _wheel_encoder_cb(data: int):
    print(f"Ticks: {data}")


def _wheel_encoder_async(wheel_encoder: WheelEncoderDriver):
    wheel_encoder.attach(_wheel_encoder_cb)
    wheel_encoder.start()
    time.sleep(10)
    print("Stopped.")
    wheel_encoder.stop()


def simulated_left_wheel_encoder_async():
    robot: DB21J = DB21J(SIMULATED_ROBOT_NAME, simulated=True)
    _wheel_encoder_async(robot.left_wheel_encoder)


def real_left_wheel_encoder_async():
    robot: DB21J = DB21J(REAL_ROBOT_NAME)
    _wheel_encoder_async(robot.left_wheel_encoder)


def simulated_right_wheel_encoder_async():
    robot: DB21J = DB21J(SIMULATED_ROBOT_NAME, simulated=True)
    _wheel_encoder_async(robot.right_wheel_encoder)


def real_right_wheel_encoder_async():
    robot: DB21J = DB21J(REAL_ROBOT_NAME)
    _wheel_encoder_async(robot.right_wheel_encoder)


# ---- Sync ------------------------------------------------------------------------------------------------------------

def _wheel_encoder_sync(wheel_encoder: WheelEncoderDriver):
    wheel_encoder.start()
    stime: float = time.time()
    while time.time() - stime < 2:
        data = wheel_encoder.capture(block=True)
        _wheel_encoder_cb(data)
    print("Stopped.")
    wheel_encoder.stop()


def simulated_left_wheel_encoder_sync():
    robot: DB21J = DB21J(SIMULATED_ROBOT_NAME, simulated=True)
    _wheel_encoder_sync(robot.left_wheel_encoder)


def real_left_wheel_encoder_sync():
    robot: DB21J = DB21J(REAL_ROBOT_NAME)
    _wheel_encoder_sync(robot.left_wheel_encoder)


def simulated_right_wheel_encoder_sync():
    robot: DB21J = DB21J(SIMULATED_ROBOT_NAME, simulated=True)
    _wheel_encoder_sync(robot.right_wheel_encoder)


def real_right_wheel_encoder_sync():
    robot: DB21J = DB21J(REAL_ROBOT_NAME)
    _wheel_encoder_sync(robot.right_wheel_encoder)

########################################################################################################################


if __name__ == '__main__':
    pass

    # camera
    # - async
    # simulated_camera_async()
    # real_camera_async()
    # - sync
    # simulated_camera_sync()
    # real_camera_sync()

    # range finder
    # - async
    # simulated_range_finder_async()
    # real_range_finder_async()
    # - sync
    # simulated_range_finder_sync()
    # real_range_finder_sync()

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
