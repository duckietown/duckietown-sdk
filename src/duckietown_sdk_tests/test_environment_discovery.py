"""Regression checks for explicit Duckiematrix replica discovery."""

import copy
import io
import unittest
from email.message import Message
from typing import Any, cast
from unittest.mock import patch
from urllib.error import HTTPError

import cbor2
import pytest

from duckietown.sdk.robots import discover_entities, discover_environments


def _manifest(count: int = 2) -> dict[str, dict[str, Any]]:
    manifest = {}
    for index in reversed(range(count)):
        identifier = f"environment_{index}"
        tile_map = f"{identifier}/map_0"
        vehicle = f"{tile_map}/vehicle_0"
        manifest[identifier] = {
            "index": index,
            "source_map": "loop",
            "isolation": "overlap-v1",
            "tile_map_keys": [tile_map],
            "vehicle_keys": [vehicle],
            "entity_keys": [tile_map, vehicle],
            "source_keys": {tile_map: "map_0", vehicle: "map_0/vehicle_0"},
            "pose": dict.fromkeys(
                ("x", "y", "z", "roll", "pitch", "yaw"), 0.0,
            ),
        }
    return manifest


def _check_equal(actual: object, expected: object) -> None:
    if actual != expected:
        pytest.fail(f"Expected {expected!r}, received {actual!r}.")


class EnvironmentDiscoveryTests(unittest.TestCase):
    """Use replica metadata alongside legacy entity discovery."""

    def test_numeric_order_and_configured_endpoint(self) -> None:
        """Order more than ten replicas using advertised indices."""
        response = io.BytesIO(cbor2.dumps({"data": _manifest(12)}))
        with patch(
            "duckietown.sdk.robots.environments.urllib.request.urlopen",
            return_value=response,
        ) as request:
            environments = discover_environments("engine.example", 7601)
        request.assert_called_once_with(
            "http://engine.example:7601/map/environments/", timeout=2,
        )
        _check_equal(
            [environment.index for environment in environments],
            list(range(12)),
        )
        _check_equal(environments[2].id, "environment_2")
        _check_equal(
            environments[2].vehicle_keys, ("environment_2/map_0/vehicle_0",),
        )
        _check_equal(
            environments[2].source_keys["environment_2/map_0/vehicle_0"],
            "map_0/vehicle_0",
        )
        with pytest.raises(TypeError):
            cast("dict[str, float]", environments[2].pose)["x"] = 1.0
        with pytest.raises(TypeError):
            cast("dict[str, str]", environments[2].source_keys)["new"] = "key"

    def test_missing_and_empty_legacy_metadata(self) -> None:
        """Allow legacy Engines without guessing a replica count."""
        headers = Message()
        with patch(
            "duckietown.sdk.robots.environments.urllib.request.urlopen",
            side_effect=HTTPError(
                "http://engine/", 404, "Missing", headers, None,
            ),
        ):
            environments = discover_environments()
            _check_equal(environments, ())
        with patch(
            "duckietown.sdk.robots.environments.urllib.request.urlopen",
            return_value=io.BytesIO(cbor2.dumps({"data": {}})),
        ):
            environments = discover_environments()
            _check_equal(environments, ())

    def test_unpublished_metadata_is_retryable(self) -> None:
        """Keep unpublished metadata distinct from legacy metadata."""
        with (
            patch(
                "duckietown.sdk.robots.environments.urllib.request.urlopen",
                return_value=io.BytesIO(b""),
            ),
            pytest.raises(ConnectionError, match="not ready"),
        ):
            discover_environments()

    def test_nonempty_truncated_metadata_is_rejected(self) -> None:
        """Reject nonempty truncated CBOR without retrying."""
        with (
            patch(
                "duckietown.sdk.robots.environments.urllib.request.urlopen",
                return_value=io.BytesIO(b"\xa1"),
            ),
            pytest.raises(cbor2.CBORDecodeError),
        ):
            discover_environments()

    def test_unreachable_and_server_errors_are_not_legacy(self) -> None:
        """Keep network failures distinct from legacy metadata."""
        headers = Message()
        for error in (
            OSError("Engine disconnected"),
            HTTPError("http://engine/", 503, "Not ready", headers, None),
        ):
            with (
                self.subTest(error=error),
                patch(
                    "duckietown.sdk.robots.environments.urllib.request.urlopen",
                    side_effect=error,
                ),
                pytest.raises(OSError, match=r"disconnected|503"),
            ):
                discover_environments()

    def test_rejects_malformed_manifests(self) -> None:
        """Reject unsafe ordering, mappings, placement or isolation."""
        cases: tuple[tuple[str, object], ...] = (
            ("index", True), ("index", -1), ("index", 3),
            ("source_map", ""), ("isolation", "unknown"),
            ("vehicle_keys", []),
            ("vehicle_keys", ["environment_1/map_0/vehicle_0"]),
            ("entity_keys", ["environment_0/map_0", "environment_0/map_0"]),
            ("source_keys", {}), ("pose", {}),
            ("pose", dict.fromkeys(
                ("x", "y", "z", "roll", "pitch", "yaw"), 1.0,
            )),
            ("pose", dict.fromkeys(
                ("x", "y", "z", "roll", "pitch", "yaw"), float("nan"),
            )),
        )
        for field, value in cases:
            manifest = copy.deepcopy(_manifest())
            manifest["environment_0"][field] = value
            with (
                self.subTest(field=field, value=value),
                patch(
                    "duckietown.sdk.robots.environments.urllib.request.urlopen",
                    return_value=io.BytesIO(cbor2.dumps({"data": manifest})),
                ),
                pytest.raises(
                    ValueError, match=r"Environment|environment|overlap-v1",
                ),
            ):
                discover_environments()

    def test_requires_dictionary_envelope(self) -> None:
        """Reject malformed discovery payloads."""
        messages: tuple[object, ...] = (
            None, [], {}, {"data": []}, {"data": {"environment_0": None}},
        )
        for message in messages:
            with (
                self.subTest(message=message),
                patch(
                    "duckietown.sdk.robots.environments.urllib.request.urlopen",
                    return_value=io.BytesIO(cbor2.dumps(message)),
                ),
                pytest.raises(TypeError),
            ):
                discover_environments()

    def test_entity_discovery_preserves_complete_runtime_keys(self) -> None:
        """Keep the tuple API and complete vehicle and static keys."""
        vehicle = "environment_2/map_0/vehicle_0"
        static = "environment_10/map_0/watchtower_0"
        topics = dict.fromkeys((
            f"robot/{vehicle}/in", f"robot/{vehicle}/out",
            f"robot/{static}/in", "robot/gym/in", "robot/gym/out",
        ))
        with patch(
            "duckietown.sdk.robots.entity.urllib.request.urlopen",
            return_value=io.BytesIO(cbor2.dumps({"topics": topics})),
        ):
            entities = discover_entities()
            _check_equal(entities, ([vehicle], [static]))
