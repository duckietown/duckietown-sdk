"""Package configuration for the Duckietown SDK."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

from setuptools import find_packages, setup  # type: ignore[import-untyped]

# :==> Fill in your project data here
# The package name is the name on PyPI
# it is not the python module names.
package_name = "duckietown-sdk"
library_webpage = "http://github.com/duckietown/duckietown-sdk"
maintainer = "Andrea F. Daniele"
maintainer_email = "afdaniele@duckietown.com"
short_description = "The Duckietown Software Development Kit (SDK)"
full_description = """
The Duckietown Software Development Kit (SDK) for Python.
"""


# Read version from the __init__ file
def get_version_from_source(filename: str) -> str:
    """Read the package version without importing the package."""
    version_value = None
    source_path = Path(filename)
    with source_path.open(encoding="utf-8") as source_file:
        for line in source_file:
            if line.startswith("__version__"):
                assignment = ast.parse(line).body[0]
                if not isinstance(assignment, ast.Assign):
                    continue
                value = assignment.value
                if isinstance(value, ast.Constant) and isinstance(
                    value.value,
                    str,
                ):
                    version_value = value.value
                    break
        else:
            error_message = f"No version found in {filename!r}."
            raise ValueError(error_message)
    if version_value is None:
        raise ValueError(filename)
    return version_value


version = get_version_from_source("src/duckietown/sdk/__init__.py")

install_requires = [
    "duckietown-messages>=0.1.0,<0.2",
    "cbor2",
    "dtps-http>=1.6.1,<2",
    "matplotlib",
    "numpy",
]
# we require pillow on MacOS and PyTurboJPEG on Linux
if sys.platform == "linux":
    install_requires.append("PyTurboJPEG>=1.7.3,<2")
elif sys.platform == "darwin":
    install_requires.append("pillow")

# compile description
underline = "=" * (len(package_name) + len(short_description) + 2)
description = f"""
{package_name}: {short_description}
{underline}

{full_description}
"""

console_scripts: list[str] = []

# setup package
setup(
    name=package_name,
    author=maintainer,
    author_email=maintainer_email,
    url=library_webpage,
    install_requires=install_requires,
    package_dir={"": "src"},
    packages=[f"duckietown.{p}" for p in find_packages("./src/duckietown")],
    long_description=description,
    long_description_content_type="text/markdown",
    version=version,
    python_requires=">=3.12",
    entry_points={"console_scripts": console_scripts},
)
