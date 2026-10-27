# The Duckietown SDK

This repository contains the Duckietown SDK for Python.

## Requirements and Compatibility

SDK 0.3.0 requires Python 3.12 or newer. CI and the Docker image use
Python 3.12. This release breaks the 0.2.x API: replace sensor `capture()`
calls with `get()`, actuator setters such as `set_pwm()` with `set()`, and
import Duckiebot models from `duckietown.sdk.robots.duckiebot`.

The matching `duckietown-messages>=0.1.0,<0.2` release must be available
before installing this SDK from PyPI. Development builds need the matching
messages package installed locally until that release is published.
DTPS transport requires `dtps-http>=1.6.1,<2`. Linux also requires the
`libturbojpeg0` system library.

## Component Lifecycle

Call `start()` before publishing and `stop()` explicitly in a `finally`
block when finished. Subscriber `get()` starts the subscriber automatically;
use `clean_up=True` for a single reading or stop it explicitly afterwards.
Object destruction does not stop components or wait for transport cleanup.

Blocking transport operations time out after 10 seconds and cancel their
pending work. `DTPSConnector.arun()` accepts a `timeout` override. Network
publishing drops new messages when its bounded queue is full; SHM publishing
waits for delivery and reports publisher failures to the caller.

## Gym Sessions and Worker Processes

Gym sensor data and actions use environment-owned `WorldInput`/`WorldOutput`
sessions. Individual vehicle drivers use direct DTPS topics and are not
wired into those Gym sessions: calling their `get()`/`set()` methods does
not replace `GymEnvironment.step()`. Base actuator `publish()` methods are
no-ops; use transport-specific drivers outside the Gym session path.

World-input callbacks reject malformed, duplicate, and older session IDs.
Callbacks for one component are serialized, keeping its current session
stable until each callback completes. Restarting a world-input component
resets its session guard for a new simulation run.

DTPS shares one event loop per process; network callbacks execute on that
loop. Use separate worker processes for independent, blocking environments,
and prefer the multiprocessing `spawn` start method. Construct components
inside each worker. Forked workers create fresh DTPS caches and loops;
inherited component connectors are rejected rather than reused.

## Tests

Install the dependencies in `requirements.txt`, then run `make test`.
This runs the offline session and native-SHM regressions with pytest and
coverage. Live sensor and actuator probes are excluded. Use
`make test-parallel TEST_WORKERS=2` for isolated pytest workers, or set
`PYTHON=/path/to/python` to choose an interpreter. Pytest combines worker
coverage automatically; `make coverage-combine` reports the combined data.
