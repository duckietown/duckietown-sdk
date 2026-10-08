"""Map interpreter utilities."""

import math
from pathlib import Path
from typing import NamedTuple

import matplotlib.pyplot as plt
import numpy as np

from duckietown.sdk.utils.bezier import (
    get_bezier_closest_point_parameter,
    get_bezier_point,
    get_bezier_tangent_vector,
)
from duckietown.sdk.utils.common import (
    get_direction_vector,
    get_rotation_matrix,
)
from duckietown.sdk.utils.exceptions import (
    PointError,
    TangentVectorError,
    TileError,
)

STRAIGHT_POINTS = (
    (
        (-0.2, 0, -0.5),
        (-0.2, 0, -0.25),
        (-0.2, 0, 0.25),
        (-0.2, 0, 0.5),
    ),
    (
        (0.2, 0, 0.5),
        (0.2, 0, 0.25),
        (0.2, 0, -0.25),
        (0.2, 0, -0.5),
    ),
)
CURVE_POINTS = (
    (
        (-0.2, 0, -0.5),
        (-0.2, 0, 0),
        (0, 0, 0.2),
        (0.5, 0, 0.2),
    ),
    (
        (0.5, 0, -0.2),
        (0.3, 0, -0.2),
        (0.2, 0, -0.3),
        (0.2, 0, -0.5),
    ),
)
THREE_WAY_POINTS = (
    (
        (-0.2, 0, -0.5),
        (-0.2, 0, -0.25),
        (-0.2, 0, 0.25),
        (-0.2, 0, 0.5),
    ),
    (
        (0.2, 0, 0.5),
        (0.2, 0, 0.25),
        (0.2, 0, -0.25),
        (0.2, 0, -0.5),
    ),
    (
        (0.5, 0, 0.2),
        (0.25, 0, 0.2),
        (-0.25, 0, 0.2),
        (-0.5, 0, 0.2),
    ),
)
NUMBER_OF_CONTROL_POINTS = 4  # Need at least 4 points for a cubic Bezier curve
NUMBER_OF_SEGMENT_SAMPLES = 20  # 20 points per segment for smoothness
FIGURE_SIZE = (10, 10)
SAVED_FIGURE_DPI = 300


class LanePosition(NamedTuple):
    """Lane position."""

    distance: float
    dot_direction: float
    angle_deg: float
    angle_rad: float

    def as_dict(self) -> dict:
        """Return as dictionary.

        Returns:
            dict: Dictionary representation of the lane position.

        """
        return {
            "distance": self.distance,
            "dot_direction": self.dot_direction,
            "angle_deg": self.angle_deg,
            "angle_rad": self.angle_rad,
        }


class MapInterpreter:
    """Map interpreter."""

    drivable_tiles: list
    frames_data: dict
    grid: dict
    road_tile_size: float
    tiles_data: dict
    tiles_info_data: dict

    def __init__(self, map_: dict) -> None:
        """Initialize the map interpreter.

        Args:
            map_ (dict): Map.

        """
        self.frames_data = map_["frames"]
        self.tiles_data = map_["tiles"]
        self.tiles_info_data = map_["tile_info"]
        self.road_tile_size = self.tiles_info_data["data"]["map_0"][
            "tile_size"
        ]["x"]
        self.grid = {}
        self.drivable_tiles = []
        self._process_tiles()

    def _get_control_points(self, start_tile: dict) -> list[np.ndarray]:  # noqa: PLR0912, PLR0915
        control_points = []
        visited = set()
        current_tile = start_tile
        current_angle = current_tile["angle"]
        while current_tile and current_tile["coords"] not in visited:
            visited.add(current_tile["coords"])
            if current_tile["kind"] == "straight":
                # For straight tiles, create control points for a
                # straight line
                pose = current_tile["pose"]
                center = (
                    pose["x"] * self.road_tile_size,
                    0,
                    pose["y"] * self.road_tile_size,
                )
                center_array = np.array(center)
                direction_vector = get_direction_vector(current_angle)
                # Add control points for straight section
                control_point = [
                    center_array
                    - 0.25 * self.road_tile_size * direction_vector,
                    center_array,
                    center_array
                    + 0.25 * self.road_tile_size * direction_vector,
                ]
                control_points.extend(control_point)
                # Find next tile
                next_tile_coordinates = self._get_next_tile_coordinates(
                    current_tile["coords"],
                    current_angle,
                )
                next_tile = self.get_tile(*next_tile_coordinates)
                if next_tile and next_tile["drivable"]:
                    current_tile = next_tile
                    current_angle = current_tile["angle"]
                else:
                    break
            elif current_tile["kind"] == "curve":
                # For curve tiles, use Bezier control points directly
                curves = current_tile["curves"]
                # Find the curve that matches our current direction
                direction_vector = get_direction_vector(current_angle)
                curve_headings = curves[:, -1, :] - curves[:, 0, :]
                norm = np.linalg.norm(curve_headings)
                curve_headings /= norm.reshape(1, -1)
                dot_products = np.dot(curve_headings, direction_vector)
                argmax = np.argmax(dot_products)
                curve = curves[argmax]
                # Add control points for curve
                control_points.extend(curve)
                # Update angle based on curve end point
                t = 1
                end_tangent = get_bezier_tangent_vector(curve, t)
                end_tangent /= np.linalg.norm(end_tangent)
                current_angle = math.atan2(-end_tangent[2], end_tangent[0])
                # Find next tile
                end_point = get_bezier_point(curve, t)
                next_tile_coordinates = (
                    self._get_next_tile_coordinates_from_point(
                        end_point,
                        current_angle,
                    )
                )
                next_tile = self.get_tile(*next_tile_coordinates)
                if next_tile and next_tile["drivable"]:
                    current_tile = next_tile
                else:
                    break
            else:
                # For 3way intersections, add control points for each
                # possible path
                pose = current_tile["pose"]
                center = (
                    pose["x"] * self.road_tile_size,
                    0,
                    pose["y"] * self.road_tile_size,
                )
                center_array = np.array(center)
                # Add center point
                control_points.append(center_array)
                # Try to continue in the current direction first
                next_tile_coordinates = self._get_next_tile_coordinates(
                    current_tile["coords"],
                    current_angle,
                )
                next_tile = self.get_tile(*next_tile_coordinates)
                if next_tile and next_tile["drivable"]:
                    current_tile = next_tile
                    current_angle = current_tile["angle"]
                else:
                    # Try right turn
                    angle = current_angle + np.pi / 2
                    next_tile_coordinates = self._get_next_tile_coordinates(
                        current_tile["coords"],
                        angle,
                    )
                    next_tile = self.get_tile(*next_tile_coordinates)
                    if next_tile and next_tile["drivable"]:
                        current_tile = next_tile
                        current_angle = current_tile["angle"]
                    else:
                        # Try left turn
                        angle = current_angle - np.pi / 2
                        next_tile_coordinates = (
                            self._get_next_tile_coordinates(
                                current_tile["coords"],
                                angle,
                            )
                        )
                        next_tile = self.get_tile(*next_tile_coordinates)
                        if next_tile and next_tile["drivable"]:
                            current_tile = next_tile
                            current_angle = current_tile["angle"]
                        else:
                            break
        return control_points

    def _get_curve(self, i: int, j: int) -> np.ndarray:
        tile = self.get_tile(i, j)
        if tile is None:
            message = f"Tile not found at ({i}, {j})."
            raise TileError(message)
        kind = tile["kind"]
        angle = tile["angle"]
        # Define control points for different tile types
        points: tuple
        if kind == "straight":
            points = STRAIGHT_POINTS
        elif kind == "curve":
            points = CURVE_POINTS
        else:
            points = THREE_WAY_POINTS
        points_array = np.array(points) * self.road_tile_size
        # Rotate and align each curve with its place in global frame
        axis = np.array([0, 1, 0])
        rotation_matrix = get_rotation_matrix(axis, angle)
        points_array = np.matmul(points_array, rotation_matrix)
        # Add tile position offset
        pose = tile["pose"]
        point = (
            pose["x"] * self.road_tile_size,
            0,
            pose["y"] * self.road_tile_size,
        )
        points_array += np.array(point)
        return points_array

    def _get_grid_coordinates(self, abs_pos: np.ndarray) -> tuple[int, int]:
        x, _, z = abs_pos
        i = math.floor(x / self.road_tile_size)
        j = math.floor(z / self.road_tile_size)
        return int(i), int(j)

    def _get_next_tile_coordinates(
        self,
        current_coordinates: tuple[int, int],
        angle: float,
    ) -> tuple[int, int]:
        i, j = current_coordinates
        # Convert angle to cardinal direction
        angle %= 2 * np.pi
        limit_angle = np.pi / 4
        # Check if facing east
        if angle < limit_angle or angle >= 7 * limit_angle:
            return (i + 1, j)
        # Check if facing north
        if angle < 3 * limit_angle:
            return (i, j + 1)
        # Check if facing west
        if angle < 5 * limit_angle:
            return (i - 1, j)
        return (i, j - 1)

    def _get_next_tile_coordinates_from_point(
        self,
        point: np.ndarray,
        angle: float,
    ) -> tuple[int, int]:
        i = math.floor(point[0] / self.road_tile_size)
        j = math.floor(point[2] / self.road_tile_size)
        return self._get_next_tile_coordinates((i, j), angle)

    def _update_track_points_from_curve_tile(
        self,
        track_points: list[np.ndarray],
        current_tile: dict,
        current_angle: float,
    ) -> tuple[list[np.ndarray], np.ndarray]:
        # For curve tiles, use Bezier curve control points
        curves = current_tile["curves"]
        direction_vector = get_direction_vector(current_angle)
        curve_headings = curves[:, -1, :] - curves[:, 0, :]
        norm = np.linalg.norm(curve_headings)
        curve_headings /= norm.reshape(1, -1)
        dot_prods = np.dot(curve_headings, direction_vector)
        argmax = np.argmax(dot_prods)
        curve = curves[argmax]
        # Sample points along the Bezier curve
        for t in np.linspace(0, 1, NUMBER_OF_SEGMENT_SAMPLES):
            point = get_bezier_point(curve, t)
            track_points.append(point[:2])  # Only use x,y coordinates
        return track_points, curve

    def _update_track_points_from_straight_tile(
        self,
        track_points: list[np.ndarray],
        current_angle: float,
        center_array: np.ndarray,
    ) -> list[np.ndarray]:
        # For straight tiles, add points along the center line
        direction_vector = get_direction_vector(current_angle)
        start_point = (
            center_array - 0.25 * self.road_tile_size * direction_vector
        )
        end_point = (
            center_array + 0.25 * self.road_tile_size * direction_vector
        )
        track_points.extend((start_point, end_point))
        return track_points

    @staticmethod
    def _get_output_path(output_directory: str, filename: str) -> str:
        path = Path(output_directory)
        path.mkdir(parents=True, exist_ok=True)
        output_path = (path / filename).as_posix()
        plt.savefig(output_path, dpi=SAVED_FIGURE_DPI, bbox_inches="tight")
        plt.close()
        return output_path

    @staticmethod
    def _get_reference_trajectory(
        control_points: list[np.ndarray],
    ) -> np.ndarray:
        # Create a smooth trajectory by sampling points along the Bezier
        # curve
        if len(control_points) < NUMBER_OF_CONTROL_POINTS:
            return np.array(())
        # Convert control points to numpy array and reshape to (N, 3)
        control_points_array = np.array(control_points)
        control_points_array = control_points_array.reshape(-1, 3)
        trajectory = []
        # Create segments of cubic Bezier curves
        control_points_array_length = len(control_points_array)
        for i in range(0, control_points_array_length - 3, 3):
            segment = control_points_array[i : i + 4]
            # Sample points along this segment
            for t in np.linspace(0, 1, NUMBER_OF_SEGMENT_SAMPLES):
                point = get_bezier_point(segment, t)
                trajectory.append(point)
        # Convert trajectory to numpy array and reshape to (N, 3)
        trajectory_array = np.array(trajectory)
        return trajectory_array.reshape(-1, 3)

    def _get_track_points(self, start_tile: dict) -> list[np.ndarray]:  # noqa: PLR0912, PLR0915
        visited = set()
        current_tile = start_tile
        current_angle = current_tile["angle"]
        track_points: list[np.ndarray] = []
        while current_tile and current_tile["coords"] not in visited:
            visited.add(current_tile["coords"])
            pose = current_tile["pose"]
            center = (
                pose["x"] * self.road_tile_size,
                pose["y"] * self.road_tile_size,
            )
            center_array = np.array(center)
            if current_tile["kind"] == "straight":
                track_points = self._update_track_points_from_straight_tile(
                    track_points,
                    current_angle,
                    center_array,
                )
                # Find next tile
                next_coordinates = self._get_next_tile_coordinates(
                    current_tile["coords"],
                    current_angle,
                )
                next_tile = self.get_tile(*next_coordinates)
                if next_tile and next_tile["drivable"]:
                    current_tile = next_tile
                    current_angle = current_tile["angle"]
                else:
                    break
            elif current_tile["kind"] == "curve":
                track_points, curve = (
                    self._update_track_points_from_curve_tile(
                        track_points,
                        current_tile,
                        current_angle,
                    )
                )
                # Update angle based on curve end point
                t = 1
                end_tangent = get_bezier_tangent_vector(curve, t)
                end_tangent /= np.linalg.norm(end_tangent)
                current_angle = math.atan2(-end_tangent[2], end_tangent[0])
                # Find next tile
                end_point = get_bezier_point(curve, t)
                next_coordinates = self._get_next_tile_coordinates_from_point(
                    end_point,
                    current_angle,
                )
                next_tile = self.get_tile(*next_coordinates)
                if next_tile and next_tile["drivable"]:
                    current_tile = next_tile
                else:
                    break
            else:
                # For 3way intersections, try to continue in current
                # direction
                track_points.append(center_array[:2])
                # Try to continue in the current direction first
                next_coordinates = self._get_next_tile_coordinates(
                    current_tile["coords"],
                    current_angle,
                )
                next_tile = self.get_tile(*next_coordinates)
                if next_tile and next_tile["drivable"]:
                    current_tile = next_tile
                    current_angle = current_tile["angle"]
                else:
                    # Try right turn
                    angle = current_angle + np.pi / 2
                    next_coordinates = self._get_next_tile_coordinates(
                        current_tile["coords"],
                        angle,
                    )
                    next_tile = self.get_tile(*next_coordinates)
                    if next_tile and next_tile["drivable"]:
                        current_tile = next_tile
                        current_angle = current_tile["angle"]
                    else:
                        # Try left turn
                        angle = current_angle - np.pi / 2
                        next_coordinates = self._get_next_tile_coordinates(
                            current_tile["coords"],
                            angle,
                        )
                        next_tile = self.get_tile(*next_coordinates)
                        if next_tile and next_tile["drivable"]:
                            current_tile = next_tile
                            current_angle = current_tile["angle"]
                        else:
                            break
        return track_points

    @staticmethod
    def _plot(title: str, x_label: str, y_label: str) -> None:
        plt.legend()
        plt.xlabel(x_label)
        plt.ylabel(y_label)
        plt.title(title)
        plt.grid(visible=True)
        plt.axis("equal")

    def _process_tiles(self) -> None:
        for tile_name, tile_info in self.tiles_data["data"].items():
            # Extract coordinates from tile name
            # (e.g., "map_0/tile_1_2" -> (1, 2))
            _, coordinates = tile_name.split("/")
            split_coordinates = coordinates.split("_")
            i, j = map(int, split_coordinates[1:])
            # Get tile type and pose
            tile_type = tile_info["type"]
            pose = self.frames_data["data"][tile_name]["pose"]
            # Determine if tile is drivable
            drivable = tile_type in ("straight", "curve", "3way")
            tile = {
                "coords": (i, j),
                "kind": tile_type,
                "angle": pose["yaw"],
                "drivable": drivable,
                "pose": pose,
            }
            self.grid[(i, j)] = tile
            if drivable:
                tile["curves"] = self._get_curve(i, j)
                self.drivable_tiles.append(tile)

    def get_closest_curve_point(
        self,
        position: np.ndarray,
        angle: float,
    ) -> tuple[np.ndarray | None, np.ndarray | None]:
        """Get the closest point and tangent vector on the lane curve.

        Args:
            position (np.ndarray): The position to check.
            angle (float): The heading angle.

        Returns:
            (tuple[np.ndarray | None, np.ndarray | None]): The closest
            point and tangent vector on the lane curve.

        """
        i, j = self._get_grid_coordinates(position)
        tile = self.get_tile(i, j)
        if tile is None or not tile["drivable"]:
            return None, None
        # Find curve with largest dotproduct with heading
        curves = tile["curves"]
        curve_headings = curves[:, -1, :] - curves[:, 0, :]
        norm = np.linalg.norm(curve_headings)
        curve_headings /= norm.reshape(1, -1)
        direction_vector = get_direction_vector(angle)
        dot_products = np.dot(curve_headings, direction_vector)
        # Closest curve = one with largest dotprod
        argmax = np.argmax(dot_products)
        control_points = curves[argmax]
        # Find closest point and tangent vector to this curve
        t = get_bezier_closest_point_parameter(control_points, position)
        point = get_bezier_point(control_points, t)
        tangent_vector = get_bezier_tangent_vector(control_points, t)
        return point, tangent_vector

    def get_lane_position(
        self,
        position: np.ndarray,
        angle: float,
    ) -> LanePosition:
        """Get the lane position of the agent.

        Args:
            position (np.ndarray): Absolute position of the agent
            `(x, y, z)`.
            angle (float): Heading angle of the agent in radians.

        Raises:
            PointError: If the point could not be found.
            TangentVectorError: If the tangent vector could not be
            found.

        Returns:
            LanePosition: The lane position of the agent.

        """
        # Get the closest point along the right lane's Bezier curve,
        # and the tangent at that point
        point, tangent_vector = self.get_closest_curve_point(position, angle)
        if point is None:
            message = f"Point not found at position={position}, angle={angle}."
            raise PointError(message)
        if tangent_vector is None:
            message = (
                f"Tangent vector not found at position={position}, "
                f"angle={angle}."
            )
            raise TangentVectorError(message)
        # Compute the alignment of the agent direction with the curve
        # tangent
        direction_vector = get_direction_vector(angle)
        dot_direction = np.dot(direction_vector, tangent_vector)
        dot_direction = min(dot_direction, 1)
        dot_direction = max(dot_direction, -1)
        # Compute the signed distance to the curve
        # Right of the curve is negative, left is positive
        position_vector = position - point
        up_vector = np.array([0, 1, 0])
        right_vector = np.cross(tangent_vector, up_vector)
        signed_distance = np.dot(position_vector, right_vector)
        # Compute the signed angle between the direction and curve
        # tangent
        # Right of the tangent is negative, left is positive
        angle_rad = math.acos(dot_direction)
        if np.dot(direction_vector, right_vector) < 0:
            angle_rad *= -1
        angle_deg = np.rad2deg(angle_rad)
        return LanePosition(
            distance=signed_distance,
            dot_direction=dot_direction,
            angle_deg=angle_deg,
            angle_rad=angle_rad,
        )

    def get_reference_trajectory(self) -> np.ndarray:
        """Get the reference trajectory as a list of 3D points.

        Returns:
            np.ndarray: The reference trajectory as a list of 3D points.

        """
        # Find all drivable tiles
        drivable_tiles = [
            tile for tile in self.drivable_tiles if tile["drivable"]
        ]
        if not drivable_tiles:
            return np.array(())
        # Start with a straight tile if possible
        iterator = (
            tile for tile in drivable_tiles if tile["kind"] == "straight"
        )
        start_tile = next(iterator, drivable_tiles[0])
        # Collect all control points for the Bezier curve
        control_points = self._get_control_points(start_tile)
        return self._get_reference_trajectory(control_points)

    def get_reference_trajectory_with_tangents(
        self,
    ) -> list[tuple[np.ndarray, np.ndarray]]:
        """Get the reference trajectory with tangents.

        Returns:
            (list[tuple[np.ndarray, np.ndarray]]): The reference
            trajectory with tangents.

        """
        trajectory = self.get_reference_trajectory()
        trajectory_with_tangents = []
        trajectory_length = len(trajectory)
        for i in range(trajectory_length):
            point = trajectory[i]
            # Calculate tangent by looking at next point
            if i < len(trajectory) - 1:
                next_point = trajectory[i + 1]
                tangent = next_point - point
                tangent /= np.linalg.norm(tangent)
            else:
                # For last point, use previous tangent
                previous_point = trajectory[i - 1]
                tangent = point - previous_point
                tangent /= np.linalg.norm(tangent)
            trajectory_with_tangents.append((point, tangent))
        return trajectory_with_tangents

    def get_tile(self, i: int, j: int) -> dict | None:
        """Get tile at grid position `(i, j)`.

        Args:
            i (int): The `x`-coordinate of the tile.
            j (int): The `y`-coordinate of the tile.

        Returns:
            (dict | None): The tile at the specified grid position, or
            `None` if it doesn't exist.

        """
        return self.grid.get((i, j))

    def plot_robot_on_tiles(
        self,
        position: np.ndarray,
        angle: float,
        output_directory: str = "plots",
        filename: str = "robot_position.png",
    ) -> str:
        """Plot robot position on tiles.

        Args:
            position (np.ndarray): Robot position `(x, y, z)` in meters.
            angle (float): Robot heading angle in radians.
            output_directory (str, optional): Directory to save the
            plot.
            Defaults to `"plots"`.
            filename (str, optional): Name of the output file. Defaults
            to `"robot_position.png"`.

        Returns:
            str: Path to the saved plot file.

        """
        # Create figure
        plt.figure(figsize=FIGURE_SIZE)
        # Collect tile centers, separating drivable and non-drivable
        # tiles
        drivable_centers = []
        non_drivable_centers = []
        for tile in self.grid.values():
            pose = tile["pose"]
            center = (
                pose["x"] * self.road_tile_size,
                pose["y"] * self.road_tile_size,
            )
            center_array = np.array(center)
            if tile["drivable"]:
                drivable_centers.append(center_array)
            else:
                non_drivable_centers.append(center_array)
        # Convert to numpy arrays
        drivable_centers_array = (
            np.array(drivable_centers) if drivable_centers else np.array(())
        )
        non_drivable_centers_array = (
            np.array(non_drivable_centers)
            if non_drivable_centers
            else np.array(())
        )
        # Plot centers with different colors
        if len(drivable_centers_array) > 0:
            plt.plot(
                drivable_centers_array[:, 0],
                drivable_centers_array[:, 1],
                "go",
                label="Drivable Tiles",
                markersize=8,
                alpha=0.3,
            )
        if len(non_drivable_centers_array) > 0:
            plt.plot(
                non_drivable_centers_array[:, 0],
                non_drivable_centers_array[:, 1],
                "ro",
                label="Non-drivable Tiles",
                markersize=8,
                alpha=0.3,
            )
        # Plot robot position
        plt.plot(
            position[0],
            position[2],
            "bo",
            label="Robot Position",
            markersize=10,
        )
        # Plot robot heading
        direction_vector = get_direction_vector(angle)
        arrow_length = 0.2
        plt.arrow(
            position[0],
            position[2],
            direction_vector[0] * arrow_length,
            direction_vector[2] * arrow_length,
            head_width=0.05,
            head_length=0.1,
            fc="b",
            ec="b",
            label="Robot Heading",
        )
        self._plot("Robot Position on Map", "x (m)", "y (m)")
        return self._get_output_path(output_directory, filename)

    def plot_tile_centers(
        self,
        output_directory: str = "plots",
        filename: str = "tile_centers.png",
    ) -> str:
        """Plot tile centers.

        Args:
            output_directory (str, optional): Directory to save the
            plot. Defaults to `"plots"`.
            filename (str, optional): Name of the output file. Defaults
            to `"tile_centers.png"`.

        Returns:
            str: Path to the saved plot file.

        """
        # Create figure
        plt.figure(figsize=FIGURE_SIZE)
        # Collect tile centers, separating drivable and non-drivable
        # tiles
        drivable_centers = []
        non_drivable_centers = []
        for tile in self.grid.values():
            pose = tile["pose"]
            center = (
                pose["x"] * self.road_tile_size,
                pose["y"] * self.road_tile_size,
            )
            center_array = np.array(center)
            if tile["drivable"]:
                drivable_centers.append(center_array)
            else:
                non_drivable_centers.append(center_array)
        # Convert to numpy arrays
        drivable_centers_array = (
            np.array(drivable_centers) if drivable_centers else np.array(())
        )
        non_drivable_centers_array = (
            np.array(non_drivable_centers)
            if non_drivable_centers
            else np.array(())
        )
        # Plot centers with different colors
        if len(drivable_centers_array) > 0:
            plt.plot(
                drivable_centers_array[:, 0],
                drivable_centers_array[:, 1],
                "go",
                label="Drivable Tiles",
                markersize=8,
            )
        if len(non_drivable_centers_array) > 0:
            plt.plot(
                non_drivable_centers_array[:, 0],
                non_drivable_centers_array[:, 1],
                "ro",
                label="Non-drivable Tiles",
                markersize=8,
            )
        self._plot(
            "Tile Centers (Green: Drivable, Red: Non-drivable)",
            "x (m)",
            "y (m)",
        )
        return self._get_output_path(output_directory, filename)

    def plot_track(
        self,
        output_directory: str = "plots",
        filename: str = "track.png",
    ) -> str:
        """Plot track.

        Args:
            output_directory (str, optional): Directory to save the
            plot. Defaults to `"plots"`.
            filename (str, optional): Name of the output file. Defaults
            to `"track.png"`.

        Returns:
            str: Path to the saved plot file.

        """
        # Create figure
        plt.figure(figsize=FIGURE_SIZE)
        # First plot all tile centers for reference
        drivable_centers = []
        non_drivable_centers = []
        for tile in self.grid.values():
            pose = tile["pose"]
            center = (
                pose["x"] * self.road_tile_size,
                pose["y"] * self.road_tile_size,
            )
            center_array = np.array(center)
            if tile["drivable"]:
                drivable_centers.append(center_array)
            else:
                non_drivable_centers.append(center_array)
        # Convert to numpy arrays
        drivable_centers_array = (
            np.array(drivable_centers) if drivable_centers else np.array(())
        )
        non_drivable_centers_array = (
            np.array(non_drivable_centers)
            if non_drivable_centers
            else np.array(())
        )
        # Plot centers with different colors
        if len(drivable_centers_array) > 0:
            plt.plot(
                drivable_centers_array[:, 0],
                drivable_centers_array[:, 1],
                "go",
                label="Drivable Tiles",
                markersize=8,
                alpha=0.3,
            )
        if len(non_drivable_centers_array) > 0:
            plt.plot(
                non_drivable_centers_array[:, 0],
                non_drivable_centers_array[:, 1],
                "ro",
                label="Non-drivable Tiles",
                markersize=8,
                alpha=0.3,
            )
        # Find a starting point (preferably a straight tile)
        iterable = (
            tile for tile in self.drivable_tiles if tile["kind"] == "straight"
        )
        start_tile = next(
            iterable,
            self.drivable_tiles[0] if self.drivable_tiles else None,
        )
        if start_tile is None:
            return ""
        # Get track points
        track_points = self._get_track_points(start_tile)
        # Convert track points to numpy array and plot
        if track_points:
            track_points_array = np.array(track_points)
            plt.plot(
                track_points_array[:, 0],
                track_points_array[:, 1],
                "b-",
                label="Track",
                linewidth=2,
            )
        self._plot("Map Trajectory and Position", "x (m)", "z (m)")
        return self._get_output_path(output_directory, filename)

    def plot_trajectory_and_position(
        self,
        position: np.ndarray,
        angle: float,
        lane_position: LanePosition | None = None,
        output_directory: str = "plots",
        filename: str = "trajectory_position.png",
    ) -> str:
        """Plot trajectory and position, and save to file `filename`.

        Args:
            position (np.ndarray): Current position `(x, y, z)`.
            angle (float): Current heading angle in radians.
            lane_position (LanePosition | None, optional): Lane position
            information. Defaults to None.
            output_directory (str, optional): Directory to save the
            plot. Defaults to `"plots"`.
            filename (str, optional): Name of the output file. Defaults
            to `"trajectory_position.png"`.

        Returns:
            str: Path to the saved plot file.

        """
        # Get reference trajectory
        trajectory = self.get_reference_trajectory()
        trajectory_points = np.array(trajectory)
        # Create figure
        plt.figure(figsize=FIGURE_SIZE)
        # Plot reference trajectory
        plt.plot(
            trajectory_points[:, 0],
            trajectory_points[:, 2],
            "b-",
            label="Reference Trajectory",
            alpha=0.5,
        )
        # Plot current position
        plt.plot(
            position[0],
            position[2],
            "ro",
            label="Current Position",
            markersize=10,
        )
        # Plot heading direction
        direction_vector = get_direction_vector(angle)
        arrow_length = 0.2
        plt.arrow(
            position[0],
            position[2],
            direction_vector[0] * arrow_length,
            direction_vector[2] * arrow_length,
            head_width=0.05,
            head_length=0.1,
            fc="r",
            ec="r",
            label="Heading",
        )
        # If lane position is provided, add distance/angle information
        if lane_position is not None:
            # Find closest point on trajectory
            closest_point, closest_tangent = self.get_closest_curve_point(
                position,
                angle,
            )
            if closest_point is not None and closest_tangent is not None:
                # Plot line to closest point
                plt.plot(
                    [position[0], closest_point[0]],
                    [position[2], closest_point[2]],
                    "g--",
                    label=f"Distance: {lane_position.distance:.2f}m",
                )
                # Plot angle
                angle_arrow_length = 0.15
                plt.arrow(
                    closest_point[0],
                    closest_point[2],
                    closest_tangent[0] * angle_arrow_length,
                    closest_tangent[2] * angle_arrow_length,
                    head_width=0.05,
                    head_length=0.1,
                    fc="g",
                    ec="g",
                    label=f"Angle: {lane_position.angle_deg:.1f} deg",
                )
        self._plot("Map Trajectory and Position", "x (m)", "z (m)")
        return self._get_output_path(output_directory, filename)

    def plot_trajectory_with_tangents(
        self,
        output_directory: str = "plots",
        filename: str = "trajectory_tangents.png",
    ) -> str:
        """Plot trajectory with tangents, and save to file `filename`.

        Args:
            output_directory (str, optional): Directory to save the
            plot. Defaults to `"plots"`.
            filename (str, optional): Name of the output file. Defaults
            to `"trajectory_tangents.png"`.

        Returns:
            str: Path to the saved plot file.

        """
        trajectory_with_tangents = (
            self.get_reference_trajectory_with_tangents()
        )
        # Create figure
        plt.figure(figsize=FIGURE_SIZE)
        # Extract points and tangents
        iterable = (p for p, _ in trajectory_with_tangents)
        points = np.array(iterable)
        iterable = (t for _, t in trajectory_with_tangents)
        tangents = np.array(iterable)
        # Plot trajectory
        plt.plot(
            points[:, 0],
            points[:, 2],
            "b-",
            label="Reference Trajectory",
        )
        # Plot tangent vectors
        arrow_length = 0.1
        for point, tangent in zip(points, tangents, strict=False):
            plt.arrow(
                point[0],
                point[2],
                tangent[0] * arrow_length,
                tangent[2] * arrow_length,
                head_width=0.02,
                head_length=0.05,
                fc="g",
                ec="g",
            )
        self._plot("Reference Trajectory with Tangents", "x (m)", "z (m)")
        return self._get_output_path(output_directory, filename)
