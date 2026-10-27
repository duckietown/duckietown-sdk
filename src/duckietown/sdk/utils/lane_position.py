"""Lane geometry, trajectory sampling, and map visualization."""

import math
from importlib import import_module
from pathlib import Path
from typing import NamedTuple

import numpy as np

# Constants
CAMERA_FORWARD_DIST = 0.066  # Distance from camera to center of rotation
ROBOT_LENGTH = 0.18  # Total robot length
CUBIC_BEZIER_POINT_COUNT = 4
MIN_LANE_ALIGNMENT = math.cos(math.pi / 4)


# Named tuple for lane position information
class LanePosition0(NamedTuple):
    """Lane offset and alignment measurements."""

    dist: float
    dot_dir: float
    angle_deg: float
    angle_rad: float


class LanePosition(LanePosition0):
    """Lane measurements with a serializable representation."""

    def as_json_dict(self) -> dict[str, float]:
        """Serialization-friendly format."""
        return {
            "dist": self.dist,
            "dot_dir": self.dot_dir,
            "angle_deg": self.angle_deg,
            "angle_rad": self.angle_rad,
        }


class NotInLane(Exception):
    """Raised when the Duckiebot is not in a lane."""


class MapInterpreter:
    """Interpret tile geometry from the Duckiematrix map components."""

    def __init__(self, map: dict) -> None:
        """Initialize the interpreter from the map components.

        Args:
            map: Frame, tile, and tile-info messages for the map.

        """
        # Load YAML files

        self.frames_data = map["frames"]
        self.tiles_data = map["tiles"]
        self.tiles_maps_data = map["tile_info"]
        # Get tile size
        self.road_tile_size = self.tiles_maps_data["data"]["map_0"][
            "tile_size"
        ]["x"]

        # Initialize grid
        self.grid: dict[tuple[int, int], dict] = {}
        self.drivable_tiles: list[dict] = []

        self._process_tiles()

    def _process_tiles(self) -> None:
        """Process all tiles in the map and create the grid."""
        for tile_name, tile_info in self.tiles_data["data"].items():
            # Extract grid coordinates from the tile name.
            _, coords = tile_name.split("/")
            i, j = map(int, coords.split("_")[1:])

            # Get tile type and pose
            tile_type = tile_info["type"]
            pose = self.frames_data["data"][tile_name]["pose"]

            # Determine if tile is drivable
            drivable = tile_type in ["straight", "curve", "3way"]

            tile_obj = {
                "coords": (i, j),
                "kind": tile_type,
                "angle": pose["yaw"],
                "drivable": drivable,
                "pose": pose,
            }

            self.grid[(i, j)] = tile_obj

            if drivable:
                tile_obj["curves"] = self._get_curve(i, j)
                self.drivable_tiles.append(tile_obj)

    def get_tile(self, i: int, j: int) -> dict | None:
        """Get the tile at grid position (i,j)."""
        return self.grid.get((i, j))

    def _get_curve(self, i: int, j: int) -> np.ndarray:
        """Get the Bezier control points for every curve in a tile.

        Return an array of control points for each possible curve.
        """
        tile = self.get_tile(i, j)
        if tile is None:
            error_message = f"No tile at grid position {(i, j)}."
            raise ValueError(error_message)

        kind = tile["kind"]
        angle = tile["angle"]

        # Define control points for different tile types
        if kind == "straight":
            pts = (
                np.array(
                    [
                        [
                            [-0.20, 0, -0.50],
                            [-0.20, 0, -0.25],
                            [-0.20, 0, 0.25],
                            [-0.20, 0, 0.50],
                        ],
                        [
                            [0.20, 0, 0.50],
                            [0.20, 0, 0.25],
                            [0.20, 0, -0.25],
                            [0.20, 0, -0.50],
                        ],
                    ],
                )
                * self.road_tile_size
            )

        elif kind in ("curve", "3way"):
            tangent_factor = 4 / 3 * math.tan(math.pi / 8)
            pts = (
                np.array(
                    [
                        [
                            [0.20, 0, 0.50],
                            [0.20, 0, 0.50 - 0.70 * tangent_factor],
                            [-0.50 + 0.70 * tangent_factor, 0, -0.20],
                            [-0.50, 0, -0.20],
                        ],
                        [
                            [-0.50, 0, 0.20],
                            [-0.50 + 0.30 * tangent_factor, 0, 0.20],
                            [-0.20, 0, 0.50 - 0.30 * tangent_factor],
                            [-0.20, 0, 0.50],
                        ],
                    ],
                )
                * self.road_tile_size
            )

            if kind == "3way":
                opposite_turns = pts[:, ::-1, :] * np.array([-1, 1, 1])
                straight = (
                    np.array(
                        [
                            [
                                [0.50, 0, -0.20],
                                [0.25, 0, -0.20],
                                [-0.25, 0, -0.20],
                                [-0.50, 0, -0.20],
                            ],
                            [
                                [-0.50, 0, 0.20],
                                [-0.25, 0, 0.20],
                                [0.25, 0, 0.20],
                                [0.50, 0, 0.20],
                            ],
                        ],
                    )
                    * self.road_tile_size
                )
                pts = np.concatenate((straight, pts, opposite_turns))

        # Rotate and align each curve with its place in global frame
        mat = gen_rot_matrix(np.array([0, 1, 0]), angle)
        pts = np.matmul(pts, mat)

        # Add tile position offset
        pose = tile["pose"]
        pts += np.array(
            [
                pose["x"] * self.road_tile_size,
                0,
                pose["y"] * self.road_tile_size,
            ],
        )

        return pts

    def get_reference_trajectory(self) -> list[np.ndarray] | np.ndarray:
        """Sample a continuous reference Bezier trajectory.

        Connect the control points from each tile to create the curve.
        Return 3D points (x, y, z) along the road center line.
        """
        # Find all drivable tiles
        drivable_tiles = [t for t in self.drivable_tiles if t["drivable"]]
        if not drivable_tiles:
            return []

        # Start with a straight tile if possible
        start_tile = next(
            (t for t in drivable_tiles if t["kind"] == "straight"),
            drivable_tiles[0],
        )

        # Collect all control points for the Bezier curve
        control_points = []
        visited = set()
        current_tile = start_tile
        current_angle = current_tile["angle"]

        while current_tile and current_tile["coords"] not in visited:
            visited.add(current_tile["coords"])

            if current_tile["kind"] == "straight":
                # Add control points along the straight tile.
                pose = current_tile["pose"]
                center = np.array(
                    [
                        pose["x"] * self.road_tile_size,
                        0,
                        pose["y"] * self.road_tile_size,
                    ],
                )
                dir_vec = get_dir_vec(current_angle)

                # Add control points for straight section
                control_points.extend(
                    [
                        center - 0.25 * self.road_tile_size * dir_vec,
                        center,
                        center + 0.25 * self.road_tile_size * dir_vec,
                    ],
                )

                # Find next tile
                next_coords = self._get_next_tile_coords(
                    current_tile["coords"], current_angle,
                )
                next_tile = self.get_tile(*next_coords)
                if next_tile and next_tile["drivable"]:
                    current_tile = next_tile
                    current_angle = current_tile["angle"]
                else:
                    break

            elif current_tile["kind"] == "curve":
                # Use the curve's Bezier control points directly.
                curves = current_tile["curves"]
                # Find the curve that matches our current direction
                dir_vec = get_dir_vec(current_angle)
                curve_headings = curves[:, -1, :] - curves[:, 0, :]
                curve_headings = curve_headings / np.linalg.norm(
                    curve_headings,
                ).reshape(1, -1)
                dot_prods = np.dot(curve_headings, dir_vec)
                curve = curves[np.argmax(dot_prods)]

                # Add control points for curve
                control_points.extend(curve)

                # Update angle based on curve end point
                end_tangent = bezier_tangent(curve, 1.0)
                end_tangent = end_tangent / np.linalg.norm(end_tangent)
                current_angle = math.atan2(-end_tangent[2], end_tangent[0])

                # Find next tile
                end_point = bezier_point(curve, 1.0)
                next_coords = self._get_next_tile_coords_from_point(
                    end_point, current_angle,
                )
                next_tile = self.get_tile(*next_coords)
                if next_tile and next_tile["drivable"]:
                    current_tile = next_tile
                else:
                    break

            elif current_tile["kind"] == "3way":
                # Add the intersection's center as a control point.
                pose = current_tile["pose"]
                center = np.array(
                    [
                        pose["x"] * self.road_tile_size,
                        0,
                        pose["y"] * self.road_tile_size,
                    ],
                )

                # Add center point
                control_points.append(center)

                next_tile = self._get_next_intersection_tile(
                    current_tile["coords"],
                    current_angle,
                )
                if next_tile is not None:
                    current_tile = next_tile
                    current_angle = current_tile["angle"]
                else:
                    break

        return _sample_trajectory(control_points)

    def _get_next_tile_coords(
        self, current_coords: tuple[int, int], angle: float,
    ) -> tuple[int, int]:
        """Get the next tile coordinates from a position and heading."""
        i, j = current_coords
        # Convert angle to cardinal direction
        angle = angle % (2 * np.pi)
        if angle < np.pi / 4 or angle >= 7 * np.pi / 4:  # East
            return (i + 1, j)
        if angle < 3 * np.pi / 4:  # North
            return (i, j + 1)
        if angle < 5 * np.pi / 4:  # West
            return (i - 1, j)
        # South
        return (i, j - 1)

    def _get_next_intersection_tile(
        self,
        current_coords: tuple[int, int],
        angle: float,
    ) -> dict | None:
        for offset in (0, np.pi / 2, -np.pi / 2):
            next_coords = self._get_next_tile_coords(
                current_coords,
                angle + offset,
            )
            next_tile = self.get_tile(*next_coords)
            if next_tile and next_tile["drivable"]:
                return next_tile
        return None

    def _get_next_tile_coords_from_point(
        self, point: np.ndarray, angle: float,
    ) -> tuple[int, int]:
        """Get the next tile coordinates from a point and heading."""
        i = math.floor(point[0] / self.road_tile_size)
        j = math.floor(point[2] / self.road_tile_size)
        return self._get_next_tile_coords((i, j), angle)

    def get_reference_trajectory_with_tangents(
        self,
    ) -> list[tuple[np.ndarray, np.ndarray]]:
        """Get the reference trajectory and its tangent vectors.

        Returns a list of tuples (point, tangent) where:
        - point is a 3D point (x, y, z) on the trajectory
        - tangent is the normalized tangent vector at that point
        """
        trajectory = self.get_reference_trajectory()
        trajectory_with_tangents = []

        for i in range(len(trajectory)):
            point = trajectory[i]

            # Calculate tangent by looking at next point
            if i < len(trajectory) - 1:
                next_point = trajectory[i + 1]
                tangent = next_point - point
                tangent = tangent / np.linalg.norm(tangent)
            else:
                # For last point, use previous tangent
                prev_point = trajectory[i - 1]
                tangent = point - prev_point
                tangent = tangent / np.linalg.norm(tangent)

            trajectory_with_tangents.append((point, tangent))

        return trajectory_with_tangents

    def plot_trajectory_and_position(
        self,
        pos: np.ndarray,
        angle: float,
        lane_pos: LanePosition | None = None,
        output_dir: str = "plots",
        filename: str = "trajectory_position.png",
    ) -> str:
        """Save a plot of the reference trajectory and current position.

        Args:
            pos: Current position (x, y, z)
            angle: Current heading angle in radians
            lane_pos: Optional distance and heading measurements.
            output_dir: Directory to save the plot
            filename: Name of the output file

        """
        # Get reference trajectory
        trajectory = self.get_reference_trajectory()
        trajectory_points = np.array(trajectory)

        # Create figure
        plt = import_module("matplotlib.pyplot")
        plt.figure(figsize=(10, 10))

        # Plot reference trajectory
        plt.plot(
            trajectory_points[:, 0],
            trajectory_points[:, 2],
            "b-",
            label="Reference Trajectory",
            alpha=0.5,
        )

        # Plot current position
        plt.plot(pos[0], pos[2], "ro", label="Current Position", markersize=10)

        # Plot heading direction
        dir_vec = get_dir_vec(angle)
        arrow_length = 0.2
        plt.arrow(
            pos[0],
            pos[2],
            dir_vec[0] * arrow_length,
            dir_vec[2] * arrow_length,
            head_width=0.05,
            head_length=0.1,
            fc="r",
            ec="r",
            label="Heading",
        )

        # Add distance and angle information when available.
        if lane_pos is not None:
            # Find closest point on trajectory
            closest_point, closest_tangent = self.closest_curve_point(
                pos, angle,
            )
            if closest_point is not None and closest_tangent is not None:
                # Plot line to closest point
                plt.plot(
                    [pos[0], closest_point[0]],
                    [pos[2], closest_point[2]],
                    "g--",
                    label=f"Distance: {lane_pos.dist:.2f}m",
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
                    label=f"Angle: {lane_pos.angle_deg:.1f}°",
                )

        # Add legend and labels
        plt.legend()
        plt.xlabel("X (m)")
        plt.ylabel("Z (m)")
        plt.title("Map Trajectory and Position")
        plt.grid(visible=True)
        plt.axis("equal")

        return _save_plot(output_dir, filename)

    def plot_trajectory_with_tangents(
        self,
        output_dir: str = "plots",
        filename: str = "trajectory_tangents.png",
    ) -> str:
        """Save a plot of the reference trajectory and its tangents.

        Args:
            output_dir: Directory to save the plot
            filename: Name of the output file

        """
        trajectory_with_tangents = (
            self.get_reference_trajectory_with_tangents()
        )

        # Create figure
        plt = import_module("matplotlib.pyplot")
        plt.figure(figsize=(10, 10))

        # Extract points and tangents
        points = np.array([p for p, _ in trajectory_with_tangents])
        tangents = np.array([t for _, t in trajectory_with_tangents])

        # Plot trajectory
        plt.plot(
            points[:, 0], points[:, 2], "b-", label="Reference Trajectory",
        )

        # Plot tangent vectors
        arrow_length = 0.1
        for point, tangent in zip(points, tangents, strict=True):
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

        # Add legend and labels
        plt.legend()
        plt.xlabel("X (m)")
        plt.ylabel("Z (m)")
        plt.title("Reference Trajectory with Tangents")
        plt.grid(visible=True)
        plt.axis("equal")

        return _save_plot(output_dir, filename)

    def plot_tile_centers(
        self, output_dir: str = "plots", filename: str = "tile_centers.png",
    ) -> str:
        """Plot the centers of all tiles in 2D coordinates.

        Drivable tiles are green and non-drivable tiles are red.

        Args:
            output_dir: Directory to save the plot
            filename: Name of the output file

        """
        # Create figure
        plt = import_module("matplotlib.pyplot")
        plt.figure(figsize=(10, 10))

        self._plot_tile_centers()

        plt.grid(visible=True)
        plt.xlabel("X (m)")
        plt.ylabel("Y (m)")
        plt.title("Tile Centers (Green: Drivable, Red: Non-drivable)")
        plt.legend()
        plt.axis("equal")

        return _save_plot(output_dir, filename)

    def _plot_tile_centers(self, *, alpha: float | None = None) -> None:
        plt = import_module("matplotlib.pyplot")
        drivable_centers = []
        non_drivable_centers = []

        for tile in self.grid.values():
            pose = tile["pose"]
            center = np.array(
                [
                    pose["x"] * self.road_tile_size,
                    pose["y"] * self.road_tile_size,
                ],
            )

            if tile["drivable"]:
                drivable_centers.append(center)
            else:
                non_drivable_centers.append(center)

        # Convert to numpy arrays
        drivable_points = np.array(drivable_centers)
        non_drivable_points = np.array(non_drivable_centers)

        # Plot centers with different colors
        if len(drivable_points) > 0:
            plt.plot(
            drivable_points[:, 0],
            drivable_points[:, 1],
                "go",
                label="Drivable Tiles",
                markersize=8,
                alpha=alpha,
            )
        if len(non_drivable_points) > 0:
            plt.plot(
            non_drivable_points[:, 0],
            non_drivable_points[:, 1],
                "ro",
                label="Non-drivable Tiles",
                markersize=8,
                alpha=alpha,
            )

    def plot_track(
        self, output_dir: str = "plots", filename: str = "track.png",
    ) -> str | None:
        """Save a complete track plot connecting the drivable tiles.

        Use lines for straight tiles and Bezier curves for turns.

        Args:
            output_dir: Directory to save the plot
            filename: Name of the output file

        """
        # Create figure
        plt = import_module("matplotlib.pyplot")
        plt.figure(figsize=(10, 10))

        self._plot_tile_centers(alpha=0.3)

        # Find a starting point (preferably a straight tile)
        start_tile = next(
            (t for t in self.drivable_tiles if t["kind"] == "straight"),
            self.drivable_tiles[0] if self.drivable_tiles else None,
        )

        if start_tile is None:
            return None

        track_points = self._get_track_points(start_tile)
        if track_points:
            points = np.array(track_points)
            plt.plot(
                points[:, 0],
                points[:, 1],
                "b-",
                label="Track",
                linewidth=2,
            )

        plt.grid(visible=True)
        plt.xlabel("X (m)")
        plt.ylabel("Y (m)")
        plt.title("Complete Track")
        plt.legend()
        plt.axis("equal")

        return _save_plot(output_dir, filename)

    def _get_track_points(self, start_tile: dict) -> list[np.ndarray]:
        visited = set()
        current_tile = start_tile
        current_angle = current_tile["angle"]
        track_points = []

        while current_tile and current_tile["coords"] not in visited:
            visited.add(current_tile["coords"])
            pose = current_tile["pose"]
            center = np.array(
                [
                    pose["x"] * self.road_tile_size,
                    pose["y"] * self.road_tile_size,
                ],
            )

            if current_tile["kind"] == "straight":
                # For straight tiles, add points along the center line
                dir_vec = get_dir_vec(current_angle)
                start_point = center - 0.25 * self.road_tile_size * dir_vec
                end_point = center + 0.25 * self.road_tile_size * dir_vec
                track_points.extend([start_point, end_point])

                # Find next tile
                next_coords = self._get_next_tile_coords(
                    current_tile["coords"], current_angle,
                )
                next_tile = self.get_tile(*next_coords)
                if next_tile and next_tile["drivable"]:
                    current_tile = next_tile
                    current_angle = current_tile["angle"]
                else:
                    break

            elif current_tile["kind"] == "curve":
                # For curve tiles, use Bezier curve control points
                curves = current_tile["curves"]
                dir_vec = get_dir_vec(current_angle)
                curve_headings = curves[:, -1, :] - curves[:, 0, :]
                curve_headings = curve_headings / np.linalg.norm(
                    curve_headings,
                ).reshape(1, -1)
                dot_prods = np.dot(curve_headings, dir_vec)
                curve = curves[np.argmax(dot_prods)]

                # Sample points along the Bezier curve
                for t in np.linspace(0, 1, 20):
                    point = bezier_point(curve, t)
                    track_points.append(point[:2])  # Only use x,y coordinates

                # Update angle based on curve end point
                end_tangent = bezier_tangent(curve, 1.0)
                end_tangent = end_tangent / np.linalg.norm(end_tangent)
                current_angle = math.atan2(-end_tangent[2], end_tangent[0])

                # Find next tile
                end_point = bezier_point(curve, 1.0)
                next_coords = self._get_next_tile_coords_from_point(
                    end_point, current_angle,
                )
                next_tile = self.get_tile(*next_coords)
                if next_tile and next_tile["drivable"]:
                    current_tile = next_tile
                else:
                    break

            elif current_tile["kind"] == "3way":
                # Prefer the current direction at intersections.
                track_points.append(center[:2])  # Only use x,y coordinates

                next_tile = self._get_next_intersection_tile(
                    current_tile["coords"],
                    current_angle,
                )
                if next_tile is not None:
                    current_tile = next_tile
                    current_angle = current_tile["angle"]
                else:
                    break

        return track_points

    def plot_robot_on_tiles(
        self,
        pos: np.ndarray,
        angle: float,
        output_dir: str = "plots",
        filename: str = "robot_position.png",
    ) -> str:
        """Plot the robot's position and angle on the tile centers map.

        Args:
            pos: Robot position (x, y, z) in meters
            angle: Robot heading angle in radians
            output_dir: Directory to save the plot
            filename: Name of the output file

        """
        # Create figure
        plt = import_module("matplotlib.pyplot")
        plt.figure(figsize=(10, 10))

        self._plot_tile_centers(alpha=0.3)

        # Plot robot position
        plt.plot(pos[0], pos[2], "bo", label="Robot Position", markersize=10)

        # Plot robot heading
        dir_vec = get_dir_vec(angle)
        arrow_length = 0.2
        plt.arrow(
            pos[0],
            pos[2],
            dir_vec[0] * arrow_length,
            dir_vec[2] * arrow_length,
            head_width=0.05,
            head_length=0.1,
            fc="b",
            ec="b",
            label="Robot Heading",
        )

        # Add grid lines
        plt.grid(visible=True)

        # Add labels and title
        plt.xlabel("X (m)")
        plt.ylabel("Y (m)")
        plt.title("Robot Position on Map")
        plt.legend()
        plt.axis("equal")

        return _save_plot(output_dir, filename)


def _sample_trajectory(
    control_points: list[np.ndarray],
) -> list[np.ndarray] | np.ndarray:
    if len(control_points) < CUBIC_BEZIER_POINT_COUNT:
        return []
    points = np.array(control_points).reshape(-1, 3)
    trajectory = []
    for index in range(0, len(points) - 3, 3):
        segment = points[index : index + CUBIC_BEZIER_POINT_COUNT]
        for parameter in np.linspace(0, 1, 20):
            point = bezier_point(segment, parameter)
            trajectory.append(point)
    return np.array(trajectory).reshape(-1, 3)


def _save_plot(output_dir: str, filename: str) -> str:
    plt = import_module("matplotlib.pyplot")
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    output_path = directory / filename
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()
    return str(output_path)


def gen_rot_matrix(axis: np.ndarray, angle: float) -> np.ndarray:
    """Generate a rotation matrix around an axis by an angle."""
    # Numerical edge cases may need a more robust implementation.
    c = math.cos(angle)
    s = math.sin(angle)
    x, y, z = axis
    return np.array(
        [
            [
                c + x * x * (1 - c),
                x * y * (1 - c) - z * s,
                x * z * (1 - c) + y * s,
            ],
            [
                y * x * (1 - c) + z * s,
                c + y * y * (1 - c),
                y * z * (1 - c) - x * s,
            ],
            [
                z * x * (1 - c) - y * s,
                z * y * (1 - c) + x * s,
                c + z * z * (1 - c),
            ],
        ],
    )


def get_dir_vec(angle: float) -> np.ndarray:
    """Return the direction in which the agent is looking."""
    x = math.cos(angle)
    z = -math.sin(angle)
    return np.array([x, 0, z])


def get_right_vec(angle: float) -> np.ndarray:
    """Return the direction to the right of the agent."""
    x = math.sin(angle)
    z = math.cos(angle)
    return np.array([x, 0, z])


def _actual_center(pos: np.ndarray, angle: float) -> np.ndarray:
    """Calculate the position of the geometric center of the agent.

    The value of pos is the center of rotation.
    """
    dir_vec = get_dir_vec(angle)
    return (
        pos + (CAMERA_FORWARD_DIST - (0.18 / 2)) * dir_vec
    )  # 0.18 is ROBOT_LENGTH


class LanePositionCalculator:
    """Calculate lane-relative position and heading from a map."""

    def __init__(self, map_interpreter: MapInterpreter) -> None:
        """Use the supplied map interpreter's tile geometry."""
        self.map_interpreter = map_interpreter
        self.road_tile_size = map_interpreter.road_tile_size

    def get_grid_coords(self, abs_pos: np.ndarray) -> tuple[int, int]:
        """Compute the tile indices (i,j) for a world position (x,_,z).

        x-axis maps to increasing i indices
        z-axis maps to increasing j indices
        """
        x, _, z = abs_pos
        i = math.floor(x / self.road_tile_size + 0.5)
        j = math.floor(z / self.road_tile_size + 0.5)
        return int(i), int(j)

    def closest_curve_point(
        self,
        pos: np.ndarray,
        angle: float,
    ) -> tuple[np.ndarray | None, np.ndarray | None]:
        """Get the closest point on the curve to a given point.

        Also returns the tangent at that point.
        Prefer routes within 45 degrees of the heading; otherwise use
        the nearest route. Returns None, None for non-drivable tiles.
        """
        coords = self.get_grid_coords(pos)
        tile = self.map_interpreter.get_tile(*coords)

        if tile is None or not tile["drivable"]:
            return None, None

        curves = tile["curves"]
        parameters = [bezier_closest(curve, pos) for curve in curves]
        points = np.array(
            [
                bezier_point(curve, parameter)
                for curve, parameter in zip(curves, parameters, strict=True)
            ],
        )
        tangents = np.array(
            [
                bezier_tangent(curve, parameter)
                for curve, parameter in zip(curves, parameters, strict=True)
            ],
        )
        tangents /= np.linalg.norm(
            tangents,
            axis=1,
            keepdims=True,
        )
        direction = get_dir_vec(angle)
        alignments = np.dot(tangents, direction)
        distances = np.linalg.norm(points - pos, axis=1)
        aligned = alignments >= MIN_LANE_ALIGNMENT
        if np.any(aligned):
            distances[~aligned] = np.inf
        index = np.lexsort((-alignments, distances))[0]
        return points[index], tangents[index]

    def get_lane_pos2(self, pos: np.ndarray, angle: float) -> LanePosition:
        """Get the agent's position relative to the right lane center.

        Raises NotInLane if the Duckiebot is not in a lane.
        """
        # Get the closest point along the right lane's Bezier curve,
        # and the tangent at that point
        point, tangent = self.closest_curve_point(pos, angle)
        if point is None or tangent is None:
            msg = f"Point not in lane: {pos}"
            raise NotInLane(msg)

        # Align the agent's direction with the curve tangent.
        direction = get_dir_vec(angle)
        alignment = np.dot(direction, tangent)
        alignment = max(-1, min(1, alignment))

        # Compute the signed distance to the curve
        # Right of the curve is positive, left is negative
        position_offset = pos - point
        up_vector = np.array([0, 1, 0])
        right_vector = np.cross(tangent, up_vector)
        signed_distance = np.dot(position_offset, right_vector)

        # Compute the signed angle relative to the curve tangent.
        # Right of the tangent is positive, left is negative
        angle_rad = math.acos(alignment)

        if np.dot(direction, right_vector) < 0:
            angle_rad *= -1

        angle_deg = np.rad2deg(angle_rad)

        return LanePosition(
            dist=signed_distance,
            dot_dir=alignment,
            angle_deg=angle_deg,
            angle_rad=angle_rad,
        )

    def plot_trajectory_and_position(
        self,
        pos: np.ndarray,
        angle: float,
        lane_pos: LanePosition | None = None,
        output_dir: str = "plots",
        filename: str = "trajectory_position.png",
    ) -> str:
        """Save a plot of the reference trajectory and current position.

        Args:
            pos: Current position (x, y, z)
            angle: Current heading angle in radians
            lane_pos: Optional distance and heading measurements.
            output_dir: Directory to save the plot
            filename: Name of the output file

        """
        # Get reference trajectory
        trajectory = self.map_interpreter.get_reference_trajectory()
        if isinstance(trajectory, list):
            trajectory = np.array(trajectory)
        if len(trajectory.shape) == 1:
            trajectory = trajectory.reshape(-1, 3)

        # Create figure
        plt = import_module("matplotlib.pyplot")
        plt.figure(figsize=(10, 10))

        # Plot reference trajectory
        plt.plot(
            trajectory[:, 0],
            trajectory[:, 2],
            "b-",
            label="Reference Trajectory",
            alpha=0.5,
        )

        # Plot current position
        plt.plot(pos[0], pos[2], "ro", label="Current Position", markersize=10)

        # Plot heading direction
        dir_vec = get_dir_vec(angle)
        arrow_length = 0.2
        plt.arrow(
            pos[0],
            pos[2],
            dir_vec[0] * arrow_length,
            dir_vec[2] * arrow_length,
            head_width=0.05,
            head_length=0.1,
            fc="r",
            ec="r",
            label="Heading",
        )

        # Add distance and angle information when available.
        if lane_pos is not None:
            # Find closest point on trajectory
            closest_point, closest_tangent = self.closest_curve_point(
                pos, angle,
            )
            if closest_point is not None and closest_tangent is not None:
                # Plot line to closest point
                plt.plot(
                    [pos[0], closest_point[0]],
                    [pos[2], closest_point[2]],
                    "g--",
                    label=f"Distance: {lane_pos.dist:.2f}m",
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
                    label=f"Angle: {lane_pos.angle_deg:.1f}°",
                )

        # Add legend and labels
        plt.legend()
        plt.xlabel("X (m)")
        plt.ylabel("Z (m)")
        plt.title("Map Trajectory and Position")
        plt.grid(visible=True)
        plt.axis("equal")

        return _save_plot(output_dir, filename)

    def plot_trajectory_with_tangents(
        self,
        output_dir: str = "plots",
        filename: str = "trajectory_tangents.png",
    ) -> str:
        """Save a plot of the reference trajectory and its tangents.

        Args:
            output_dir: Directory to save the plot
            filename: Name of the output file

        """
        trajectory = self.map_interpreter.get_reference_trajectory()
        if isinstance(trajectory, list):
            trajectory = np.array(trajectory)
        if len(trajectory.shape) == 1:
            trajectory = trajectory.reshape(-1, 3)

        # Create figure
        plt = import_module("matplotlib.pyplot")
        plt.figure(figsize=(10, 10))

        # Plot trajectory
        plt.plot(
            trajectory[:, 0],
            trajectory[:, 2],
            "b-",
            label="Reference Trajectory",
        )

        # Calculate and plot tangent vectors
        for i in range(len(trajectory) - 1):
            point = trajectory[i]
            next_point = trajectory[i + 1]
            tangent = next_point - point
            tangent = tangent / np.linalg.norm(tangent)

            # Plot tangent vector
            arrow_length = 0.1
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

        # Add legend and labels
        plt.legend()
        plt.xlabel("X (m)")
        plt.ylabel("Z (m)")
        plt.title("Reference Trajectory with Tangents")
        plt.grid(visible=True)
        plt.axis("equal")

        return _save_plot(output_dir, filename)


# Bezier curve utility functions
def bezier_closest(control_points: np.ndarray, point: np.ndarray) -> float:
    """Find the Bezier parameter nearest the given point."""
    # Numerical edge cases may need a more robust implementation.
    # that handles edge cases and uses numerical optimization
    t = 0.5  # Start with middle point
    for _ in range(10):  # 10 iterations of Newton's method
        p = bezier_point(control_points, t)
        tangent = bezier_tangent(control_points, t)
        error = p - point
        t = t - np.dot(error, tangent) / np.dot(tangent, tangent)
        t = max(0, min(1, t))  # Clamp to [0,1]
    return t


def bezier_point(control_points: np.ndarray, t: float) -> np.ndarray:
    """Calculate a point on a Bezier curve at parameter t."""
    n = len(control_points) - 1
    point = np.zeros(3)
    for i, p in enumerate(control_points):
        point += p * math.comb(n, i) * (t**i) * ((1 - t) ** (n - i))
    return point


def bezier_tangent(control_points: np.ndarray, t: float) -> np.ndarray:
    """Calculate a tangent vector on a Bezier curve at parameter t."""
    n = len(control_points) - 1
    tangent = np.zeros(3)
    for i in range(n):
        p = control_points[i + 1] - control_points[i]
        tangent += p * math.comb(n - 1, i) * (t**i) * ((1 - t) ** (n - 1 - i))
    return tangent * n
