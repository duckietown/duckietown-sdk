"""Test gym mode."""

import time
from threading import Event

from duckietown.sdk.robots.duckiebot import DB21J

SIMULATED_ROBOT_NAME = "map_0/vehicle_0"
MAX_COUNT = 100


class GymModeTest:
    """Gym mode test."""

    def __init__(self, robot: DB21J, max_count: int) -> None:
        """Initialize the gym mode test."""
        self.robot = robot
        self.max_count = max_count
        self.frequencies: list[float] = []
        self.count = 0
        self.start_time: float = 0.0
        self.event = Event()

    def _callback(self, _: dict | None) -> None:
        if self.count < self.max_count:
            self.robot.step(0.5, 0.5)
            delta_time = time.time() - self.start_time
            self.frequencies.append(1 / delta_time)
            print(f"Callback frequency: {self.frequencies[-1]} Hz")
            self.count += 1
            self.start_time = time.time()
        elif self.count == self.max_count:
            self.robot.stop()
            self.event.set()

    def run(self) -> None:
        """Run the test."""
        self.robot.attach(self._callback)
        self.start_time = time.time()
        self.robot.start()
        self.event.wait()
        avg_freq = sum(self.frequencies) / len(self.frequencies)
        print(f"Average frequency: {avg_freq} Hz")


if __name__ == "__main__":
    robot = DB21J(SIMULATED_ROBOT_NAME, simulated=True, gym_mode=True)
    test = GymModeTest(robot, MAX_COUNT)
    test.run()
