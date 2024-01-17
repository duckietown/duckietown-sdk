import time
from types import NoneType
from typing import Any, Type, Set

from duckietown.sdk.middleware.base import GenericPublisher, GenericSubscriber

from duckietown.sdk.robots.duckiebot import DB21M
from duckietown.sdk.types import BGRImage, LEDsPattern, RGBAColor


def _process(data: Any, allowed: Set[Type] = None) -> int:
    if type(data) not in allowed:
        print(f"Received unexpected type: {type(data)}")
        return 0
    # print data
    if isinstance(data, BGRImage):
        print(f"Received image of shape: {data.shape}")
    elif isinstance(data, float):
        print(f"Received float: {data}")
    # ---
    return 1


def _measure_sensor_async(robot: DB21M, component: str, allowed: Set[Type]):
    duration: int = 10
    i: int = 0

    def callback(data: Any):
        nonlocal i
        i += _process(data, allowed=allowed)

    print("Attaching...")
    source: GenericSubscriber = getattr(robot, component)
    source.attach(callback)
    print("Attached.")
    source.start()
    time.sleep(duration)
    print("Stopped.")
    print(f"Measured: {round(i / duration)}Hz")


def _measure_sensor_sync(robot: DB21M, component: str, allowed: Set[Type]):
    duration: int = 10
    i: int = 0
    print("Attaching...")
    source: GenericSubscriber = getattr(robot, component)
    source.start()
    stime: float = time.time()
    while time.time() - stime < duration:
        data = source.capture(block=True)
        i += _process(data, allowed=allowed)
    print("Stopped.")
    print(f"Measured: {round(i / duration)}Hz")


def _publish(robot: DB21M, component: str, data: Any, period: float):
    duration: int = 4
    sink: GenericPublisher = getattr(robot, component)
    sink.start()
    stime: float = time.time()
    while time.time() - stime < duration:
        sink.publish(data)
        time.sleep(period)


def simulated_camera_async():
    robot: DB21M = DB21M("map_0/vehicle_0", simulated=True)
    _measure_sensor_async(robot, "camera", {BGRImage})


def real_camera_async():
    robot: DB21M = DB21M("db21j3")
    _measure_sensor_async(robot, "camera", {BGRImage})


def simulated_camera_sync():
    robot: DB21M = DB21M("map_0/vehicle_0", simulated=True)
    _measure_sensor_sync(robot, "camera", {BGRImage})


def real_camera_sync():
    robot: DB21M = DB21M("db21j3")
    _measure_sensor_async(robot, "camera", {BGRImage})


def simulated_range_finder_async():
    robot: DB21M = DB21M("map_0/vehicle_0", simulated=True)
    _measure_sensor_async(robot, "range_finder", {float, NoneType})


def real_range_finder_async():
    robot: DB21M = DB21M("db21j3")
    _measure_sensor_async(robot, "range_finder", {float, NoneType})


def simulated_range_finder_sync():
    robot: DB21M = DB21M("map_0/vehicle_0", simulated=True)
    _measure_sensor_sync(robot, "range_finder", {float, NoneType})


def real_range_finder_sync():
    robot: DB21M = DB21M("db21j3")
    _measure_sensor_async(robot, "range_finder", {float, NoneType})


def simulated_left_wheel_encoder_async():
    robot: DB21M = DB21M("map_0/vehicle_0", simulated=True)
    _measure_sensor_async(robot, "left_wheel_encoder", {float})


def real_left_wheel_encoder_async():
    robot: DB21M = DB21M("db21j3")
    _measure_sensor_async(robot, "left_wheel_encoder", {float})


def simulated_left_wheel_encoder_sync():
    robot: DB21M = DB21M("map_0/vehicle_0", simulated=True)
    _measure_sensor_sync(robot, "left_wheel_encoder", {float})


def real_left_wheel_encoder_sync():
    robot: DB21M = DB21M("db21j3")
    _measure_sensor_async(robot, "left_wheel_encoder", {float})


def simulated_right_wheel_encoder_async():
    robot: DB21M = DB21M("map_0/vehicle_0", simulated=True)
    _measure_sensor_async(robot, "right_wheel_encoder", {float})


def real_right_wheel_encoder_async():
    robot: DB21M = DB21M("db21j3")
    _measure_sensor_async(robot, "right_wheel_encoder", {float})


def simulated_right_wheel_encoder_sync():
    robot: DB21M = DB21M("map_0/vehicle_0", simulated=True)
    _measure_sensor_sync(robot, "right_wheel_encoder", {float})


def real_right_wheel_encoder_sync():
    robot: DB21M = DB21M("db21j3")
    _measure_sensor_async(robot, "right_wheel_encoder", {float})


def simulated_motors():
    robot: DB21M = DB21M("map_0/vehicle_0", simulated=True)
    _publish(robot, "motors", (0.5, 0.5), 0.1)


def real_motors():
    robot: DB21M = DB21M("db21j3")
    _publish(robot, "motors", (0.5, 0.5), 0.1)


def simulated_lights():
    robot: DB21M = DB21M("map_0/vehicle_0", simulated=True)
    amber: RGBAColor = (1, 0.7, 0, 1.0)
    lights: LEDsPattern = LEDsPattern(front_left=amber, front_right=amber, rear_right=amber, rear_left=amber)
    _publish(robot, "lights", lights, 0.1)


def real_lights():
    robot: DB21M = DB21M("db21j3")
    amber: RGBAColor = (1, 0.7, 0, 1.0)
    lights: LEDsPattern = LEDsPattern(front_left=amber, front_right=amber, rear_right=amber, rear_left=amber)
    _publish(robot, "lights", lights, 1.0)


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

