# The Duckietown SDK 🦆🤖

The **Duckietown Software Development Kit (SDK)** for Python provides a simple and powerful interface to control Duckiebots, both real and simulated. Whether you're a student, researcher, or robotics enthusiast, this SDK makes it easy to get started with autonomous vehicle development.

## ✨ Features

- 🚗 **Motor Control**: Drive your Duckiebot forward, backward, and turn
- 💡 **LED Control**: Create beautiful light patterns and signals
- 📷 **Camera Access**: Capture and process images from the robot's camera
- 📊 **Sensor Data**: Read wheel encoders, time-of-flight sensors, and more
- 🌍 **Pose Tracking**: Get real-time position and orientation data
- 🎮 **Simulation Support**: Test your code safely in simulation first
- 🔗 **Easy Integration**: Simple Python API that just works

## 🚀 Quick Start

### Installation

Install the Duckietown SDK using pip:

```bash
pip install duckietown-sdk
```

For development or to get the latest features:

```bash
git clone https://github.com/duckietown/duckietown-sdk.git
cd duckietown-sdk
pip install -e .
```

### Your First Robot Program

Here's a simple "Hello World" example that makes your Duckiebot move and blink its lights:

```python
from duckietown.sdk.robots.duckiebot import DB21J
from duckietown_messages.actuators import CarLights
from duckietown_messages.colors import RGBA
import time

# Connect to robot (simulation)
robot = DB21J("map_0/vehicle_0", simulated=True)

# For real robot, use:
# robot = DB21J("your_robot_name")

# Move forward for 2 seconds
print("🚀 Moving forward...")
robot.motors.start()
robot.motors.publish((0.3, 0.3))  # (left_speed, right_speed)
time.sleep(2.0)
robot.motors.publish((0.0, 0.0))  # Stop
robot.motors.stop()

# Blink the lights
print("✨ Light show!")
robot.lights.start()

# Create amber lights
amber = RGBA(r=1, g=0.7, b=0, a=1.0)
lights_on = CarLights(front_left=amber, front_right=amber, 
                     back_right=amber, back_left=amber)

# Create lights off
off = RGBA(r=0, g=0, b=0, a=0.0)
lights_off = CarLights(front_left=off, front_right=off, 
                      back_right=off, back_left=off)

# Blink pattern
for i in range(6):
    robot.lights.publish(lights_on if i % 2 == 0 else lights_off)
    time.sleep(0.5)

robot.lights.stop()
print("🎉 Done! Your Duckiebot says hello!")
```

## 📚 Learning Resources

### Interactive Tutorial

Check out our comprehensive Jupyter notebook tutorial:
- **[notebooks/00-hello.ipynb](notebooks/00-hello.ipynb)** - Complete interactive guide with examples

### Examples

Explore more examples in the `src/duckietown_sdk_tests/` directory:
- **Motor control**: `test_actuators.py`
- **Sensor reading**: `test_sensors.py`  
- **State management**: `test_state.py`

## 🤖 Robot Compatibility

The SDK supports the following Duckiebot models:
- **DB21J** - The newest Jetson-based Duckiebot
- **DB21M** - The middle-tier Duckiebot model

## 🔧 API Overview

### Core Components

```python
# Import the main robot class
from duckietown.sdk.robots.duckiebot import DB21J

# Create robot instance
robot = DB21J("robot_name", simulated=True)  # or False for real robot
```

### Motor Control
```python
robot.motors.start()
robot.motors.publish((left_speed, right_speed))  # Values: -1.0 to 1.0
robot.motors.stop()
```

### LED Control
```python
from duckietown_messages.actuators import CarLights
from duckietown_messages.colors import RGBA

robot.lights.start()
lights = CarLights(front_left=RGBA(1,0,0,1), ...)  # Red front left
robot.lights.publish(lights)
robot.lights.stop()
```

### Sensor Access
```python
# Camera
robot.camera.start()
image = robot.camera.capture(block=True)
robot.camera.stop()

# Wheel encoders
robot.left_wheel_encoder.start()
reading = robot.left_wheel_encoder.capture(block=True)
robot.left_wheel_encoder.stop()

# Pose (position + orientation)
robot.pose.start()
pose = robot.pose.capture(block=True)
position = pose["position"]  # {x, y, z}
rotation = pose["rotation"]  # {w, x, y, z} quaternion
robot.pose.stop()
```

## 🎯 Real vs Simulation

### Simulation Mode
Perfect for development, testing, and learning:
```python
robot = DB21J("map_0/vehicle_0", simulated=True)
```

### Real Robot Mode
When you're ready for the real thing:
```python
robot = DB21J("your_robot_hostname")  # e.g., "db21j3"
```

## 🛠️ Development

### Requirements
- Python 3.7+
- Linux (Ubuntu 18.04+) or macOS
- For real robots: Network access to your Duckiebot

### Testing
```bash
# Run basic tests
make test

# Build documentation
make docs
```

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Getting Help

- **Documentation**: [docs.duckietown.org](https://docs.duckietown.org/)
- **Community**: [duckietown.org](https://www.duckietown.org/)
- **Issues**: [GitHub Issues](https://github.com/duckietown/duckietown-sdk/issues)
- **Discussions**: [GitHub Discussions](https://github.com/duckietown/duckietown-sdk/discussions)

## 🏆 Acknowledgments

The Duckietown SDK is developed and maintained by the [Duckietown Community](https://www.duckietown.org/). Special thanks to all contributors who make this project possible!

---

Ready to start your Duckietown journey? 🚀 [Try the tutorial notebook](notebooks/00-hello.ipynb) and join our amazing community of developers, researchers, and robotics enthusiasts!
