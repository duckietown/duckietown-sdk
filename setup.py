import sys

from setuptools import find_packages, setup

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
def get_version_from_source(filename):
    import ast

    version = None
    with open(filename) as f:
        for line in f:
            if line.startswith("__version__"):
                version = ast.parse(line).body[0].value.s
                break
        else:
            raise ValueError("No version found in %r." % filename)
    if version is None:
        raise ValueError(filename)
    return version


version = get_version_from_source("src/duckietown/sdk/__init__.py")

install_requires = [
    "dt-duckiematrix-protocols-ente>=0.1.8,<1",
    "roslibpy>=1.6.0,<2",
]
tests_require = []

# we require pillow on MacOS and PyTurboJPEG on Linux
if sys.platform == "linux":
    install_requires.append("PyTurboJPEG>=1.7.3,<2")
elif sys.platform == "darwin":
    install_requires.append("pillow")

# compile description
underline = "=" * (len(package_name) + len(short_description) + 2)
description = """
{name}: {short}
{underline}

{long}
""".format(
    name=package_name,
    short=short_description,
    long=full_description,
    underline=underline,
)

console_scripts = []

# setup package
setup(
    name=package_name,
    author=maintainer,
    author_email=maintainer_email,
    url=library_webpage,
    tests_require=tests_require,
    install_requires=install_requires,
    package_dir={"": "src"},
    packages=[f"duckietown.{p}" for p in find_packages('./src/duckietown')],
    long_description=description,
    version=version,
    entry_points={"console_scripts": console_scripts},
)
