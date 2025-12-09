"""Common utilities."""

import math

import numpy as np

CAMERA_FORWARD_DIST = 0.066  # Distance from camera to center of rotation
ROBOT_LENGTH = 0.18  # Total robot length


def get_center(position: np.ndarray, angle: float) -> np.ndarray:
    """Get the center position of the robot based on its current position and orientation.

    Args:
        position (np.ndarray): The current position of the robot.
        angle (float): The current orientation of the robot in radians.

    Returns:
        np.ndarray: The center position of the robot.

    """
    direction_vector = get_direction_vector(angle)
    return (
        position + (CAMERA_FORWARD_DIST - ROBOT_LENGTH / 2) * direction_vector
    )


def get_direction_vector(angle: float) -> np.ndarray:
    """Return vector pointing in the direction the agent is looking.

    Args:
        angle (float): Angle of the agent's heading in radians.

    Returns:
        np.ndarray: Direction vector the agent is looking at.

    """
    x = math.cos(angle)
    z = -math.sin(angle)
    return np.array((x, 0, z))


def get_right_vector(angle: float) -> np.ndarray:
    """Return vector pointing to the right of the agent.

    Args:
        angle (float): Angle of the agent's heading in radians.

    Returns:
        np.ndarray: Direction vector pointing to the right of the agent.

    """
    x = math.sin(angle)
    z = math.cos(angle)
    return np.array((x, 0, z))


def get_rotation_matrix(axis: np.ndarray, angle: float) -> np.ndarray:
    """Return rotation matrix for rotation around axis by angle.

    Args:
        axis (np.ndarray): Axis of rotation `(x, y, z)`.
        angle (float): Angle of rotation in radians.

    Returns:
        np.ndarray: Rotation matrix for rotation around axis by angle.

    """
    # This is a simplified version - in practice you would want a more
    # robust implementation
    cosine_angle = math.cos(angle)
    sine_angle = math.sin(angle)
    x, y, z = axis
    difference = 1 - cosine_angle
    y_difference = y * difference
    z_difference = z * difference
    x_y_difference = x * y_difference
    x_z_difference = x * z_difference
    y_z_difference = y * z_difference
    x_sine_angle = x * sine_angle
    y_sine_angle = y * sine_angle
    z_sine_angle = z * sine_angle
    x_row = (
        cosine_angle + x**2 * difference,
        x_y_difference - z_sine_angle,
        x_z_difference + y_sine_angle,
    )
    y_row = (
        x_y_difference + z_sine_angle,
        cosine_angle + y * y_difference,
        y_z_difference - x_sine_angle,
    )
    z_row = (
        x_z_difference - y_sine_angle,
        y_z_difference + x_sine_angle,
        cosine_angle + z * z_difference,
    )
    return np.array((x_row, y_row, z_row))
