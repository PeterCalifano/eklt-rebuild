# `eklt-rebuild` Python Distribution

The root Python distribution combines the generated Eigen-backed FIBAR adapter,
EKLT bridge modules, and reusable event-vision utilities. The native binding
still comes from the same `libeklt-rebuild` target used by C++ consumers.

The distribution and import surfaces intentionally use distinct spellings:

- distribution: `eklt-rebuild`, inherited from the root CMake project name;
- generated import package and native extension: `eklt_rebuild`, normalized for
  Python identifiers;
- EKLT-specific bridge namespace: `eklt_bridge`;
- reusable, extraction-ready namespace: `event_vision_utils`.

All three namespaces are owned by the repository-level `python/` project and
are installed and versioned together. Their internal contracts remain explicit
so `event_vision_utils` can later be extracted without renaming its public API.

## Build and test

Initialize the two read-only external checkouts, then build the wrapper:

```bash
git submodule update --init lib/fibar_lib lib/wrap
./build_lib.sh \
  --build-dir build/python-wrapper \
  --type Release \
  --python \
  --install \
  --define WARNINGS_ARE_ERRORS=ON
```

The ordinary CTest run includes the wrapper import and the focused Python API
test under `python/tests/`. The root Python test job covers the bridge and
event-utility namespaces.

The CMake install remains prefix-relative:

```text
build/python-wrapper/install/lib/python3.12/site-packages/
├── eklt_rebuild/
├── eklt_bridge/
└── event_vision_utils/
```

The generated extension and `libeklt-rebuild` are co-located under
`eklt_rebuild/` when the native library is shared. A static build links the
native implementation into the extension and therefore installs no separate
EKLT runtime library.

## Build a wheel

Build the wheel only after the CMake wrapper target has generated its exact
artifact metadata:

```bash
python3 -m pip wheel \
  --no-build-isolation \
  --no-deps \
  --wheel-dir build/python-wheel \
  ./python
```

The root package setup reads the explicit wrapper and runtime paths produced by
CMake. It does not scan a build directory for native libraries. The resulting
wheel excludes `_wrapper_build.py`, caches, bytecode, and unrelated shared
libraries.

On Linux, both the extension and co-located EKLT runtime use `$ORIGIN`. Validate
the wheel outside the checkout and without `LD_LIBRARY_PATH`:

```bash
wheel_path="$(find build/python-wheel -maxdepth 1 -name '*.whl' -print -quit)"
relocated_root="$(mktemp -d)"
trap 'rm -rf -- "${relocated_root}"' EXIT

python3 - "${wheel_path}" "${relocated_root}" <<'PY'
from pathlib import Path
import sys
from zipfile import ZipFile

wheel_path = Path(sys.argv[1])
relocated_root = Path(sys.argv[2])
with ZipFile(wheel_path) as wheel:
    wheel.extractall(relocated_root)
PY

env -u LD_LIBRARY_PATH \
  PYTHONPATH="${relocated_root}" \
  python3 - <<'PY'
import numpy as np
import eklt_rebuild

reconstructor = eklt_rebuild.CFibarReconstructorAdapter(4, 3, 1000, 0.5, False)
reconstructor.acceptEvents(np.array([1.0, 2.0]),
                           np.array([1.0, 1.0]),
                           np.array([1.0, -1.0]),
                           np.array([10.0, 20.0]))
print(reconstructor.requestImage(20).shape)
PY
```

Expected output:

```text
(3, 4)
```

## API

Import the generated adapter directly:

```python
import numpy as np
import eklt_rebuild

reconstructor = eklt_rebuild.CFibarReconstructorAdapter(200, 200, 1000, 0.5, False)
reconstructor.acceptEvents(x, y, polarity, timestamps_us)
image = np.asarray(reconstructor.requestImage(int(timestamps_us[-1])))
patch = reconstructor.requestPatch(50, 50, 5, int(timestamps_us[-1]))
```

The four event arrays must have equal lengths. Coordinates, polarities, and
microsecond timestamps cross the generated Eigen boundary as floating-point
arrays, then the native adapter requires finite values that are exactly
representable by their integer contracts. Batch validation is atomic.
