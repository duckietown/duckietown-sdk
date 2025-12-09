"""Bezier curve utilities."""

import math

import numpy as np

START_POINT = 0.5  # Middle point
NUMBER_OF_ITERATIONS = 10


def get_bezier_closest_point_parameter(
    control_points: np.ndarray,
    point: np.ndarray,
) -> float:
    """Return the parameter value `t` that gives the closest point on the Bezier curve to the given point.

    Args:
        control_points (np.ndarray): Control points of the Bezier curve.
        point (np.ndarray): Point to find the closest point on the
        curve.

    Returns:
        float: The parameter value `t` that gives the closest point on
        the Bezier curve to the given point.

    """
    # This is a simplified version - in practice you'd want a more
    # robust implementation
    # that handles edge cases and uses numerical optimization
    t = START_POINT
    for _ in range(NUMBER_OF_ITERATIONS):
        bezier_point = get_bezier_point(control_points, t)
        bezier_tangent_vector = get_bezier_tangent_vector(control_points, t)
        error = bezier_point - point
        t -= np.dot(error, bezier_tangent_vector) / np.dot(
            bezier_tangent_vector,
            bezier_tangent_vector,
        )
        # Clamp to [0,1]
        t = min(t, 1)
        t = max(t, 0)
    return t


def get_bezier_point(control_points: np.ndarray, t: float) -> np.ndarray:
    """Return point on Bezier curve at parameter `t`.

    Args:
        control_points (np.ndarray): Control points of the Bezier curve.
        t (float): Parameter value (`0 <= t <= 1`).

    Returns:
        np.ndarray: Point on the Bezier curve at parameter `t`.

    """
    point = np.zeros(3)
    n = len(control_points) - 1
    for i, control_point in enumerate(control_points):
        point += control_point * math.comb(n, i) * t**i * (1 - t) ** (n - i)
    return point


def get_bezier_tangent_vector(
    control_points: np.ndarray,
    t: float,
) -> np.ndarray:
    """Return tangent vector on Bezier curve at parameter `t`.

    Args:
        control_points (np.ndarray): Control points of the Bezier curve.
        t (float): Parameter value (`0 <= t <= 1`).

    Returns:
        np.ndarray: Tangent vector on the Bezier curve at parameter `t`.

    """
    tangent_vector = np.zeros(3)
    n = len(control_points) - 1
    for i in range(n):
        p = control_points[i + 1] - control_points[i]
        tangent_vector += (
            p * math.comb(n - 1, i) * t**i * (1 - t) ** (n - 1 - i)
        )
    return tangent_vector * n
