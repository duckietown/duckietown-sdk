from typing import Dict, Optional

from dt_duckiematrix_protocols import Matrix
from dt_duckiematrix_protocols.robot import DB21M


class Duckiematrix:
    _engine: Optional[Matrix] = None
    _robots: Dict[str, DB21M] = {}

    @classmethod
    def get_instance(cls, host: str) -> Matrix:
        # cache first
        if cls._engine is None:
            # create engine to the matrix engine
            cls._engine = Matrix(host, auto_commit=True)
        return cls._engine

    @classmethod
    def get_robot(cls, host: str, robot_name: str) -> DB21M:
        # cache first
        if robot_name not in cls._robots:
            engine: Matrix = cls.get_instance(host)
            # create connection to the vehicle
            cls._robots[robot_name] = engine.robots.DB21M(robot_name)
        return cls._robots[robot_name]
