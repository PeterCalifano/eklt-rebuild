# `eklt-rebuild` Python distribution

The Python project follows the root EKLT name:

- distribution: `eklt-rebuild`;
- generated native binding: `eklt_rebuild`;
- EKLT-specific transport and source modules: `eklt_bridge`;
- reusable event-data utilities: `event_vision_utils`.

These import namespaces are intentionally distinct, but they are installed and
versioned as one distribution. `event_vision_utils` keeps a dependency-light
public boundary so it can later move to EventDataGenerationLib or a dedicated
repository without changing its event representation or import API.

## Build

Build the generated binding and its exact native runtime artifacts first:

```bash
./build_lib.sh \
  --build-dir build/python-wrapper \
  --type Release \
  --python \
  --install \
  --define WARNINGS_ARE_ERRORS=ON
```

Create the unified wheel from the root Python project:

```bash
python3.12 -m pip wheel \
  --no-build-isolation \
  --no-deps \
  --wheel-dir build/python-wheel \
  ./python
```

The wheel includes the generated extension and only the runtime libraries named
by CMake. It omits checkout-only `_wrapper_build.py` metadata, caches, bytecode,
and unrelated native libraries.

## Import boundaries

Use the generated adapter directly when the native surface is required:

```python
import eklt_rebuild

print(eklt_rebuild.HAS_WRAPPER)
```

Use generic event utilities without importing the native binding:

```python
from event_vision_utils import EventArray

events = EventArray(
    x=[0],
    y=[0],
    p=[1],
    t_us=[5],
    width=1,
    height=1,
)
print(events.size)
```

Expected output:

```text
1
```

`event_vision_utils` does not re-export or convert the separate
`eklt_bridge.primitives.EventStream` representation. New event-processing code
uses `EventArray` directly instead of maintaining two public data models at one
API boundary.

## ROS bag bridge demo

The installed bridge runner starts one ROS1 bag replay, exposes ROS1 topics
through `ros1_bridge`, and shuts down every process it owns. Pass the built
catkin overlay rather than the ROS1 underlay so `eklt_rebuild` is discoverable:

```bash
eklt-run-rosbag-bridge-demo \
  --bag data/eklt_example/boxes_6dof.bag \
  --tracks-file /tmp/eklt_example/tracks.txt \
  --ros1-setup "$HOME/eklt_catkin_ws/devel/setup.bash" \
  --ros2-setup /opt/ros/jazzy/setup.bash \
  --mode frame-backed
```

Select the alternative event-only initialization with `--mode event-only`.
Use `--dry-run` to validate input paths and inspect all generated commands
without starting ROS processes.
