# FIBAR C++ Core

`event_recon_fibar_core` is the C++ facade over the vendored upstream FIBAR
implementation in `lib/fibar_lib`. The Eigen-backed
`event_recon_fibar_adapters` boundary belongs to the same native library.

## Build Target

The native library requires the pinned FIBAR checkout:

```bash
git submodule update --init lib/fibar_lib
./build_lib.sh
```

Both APIs compile into `libeklt-rebuild`. Plain CMake consumers link the
canonical installed target:

- `eklt_rebuild::eklt-rebuild`

The package also retains logical API targets for focused consumers:

- `eklt_rebuild::event_recon_fibar_core`
- `eklt_rebuild::event_recon_fibar_adapters`

The two targets resolve to the same native binary; they do not create separate
core and adapter shared libraries.

## API

Header:

```cpp
#include "event_recon_fibar_core/fibar_reconstructor.h"
```

Config:

```cpp
event_recon_fibar_core::SFibarConfig config;
config.width = 240;
config.height = 180;
config.cutoff_time_us = 10000;
config.fill_ratio = 0.5;
config.use_spatial_filter = true;
```

Event input uses struct-of-arrays views:

```cpp
event_recon_fibar_core::SEventBatchView batch{
    x.data(), y.data(), p.data(), t_us.data(), x.size(), width, height};
reconstructor.acceptEvents(batch);
```

Output paths:

- `requestImage(t_us)` returns the latest causal finite `float` image.
- `makeDisplayImage(t_us)` returns an 8-bit normalized visualization image.
- `requestPatch(x, y, radius, t_us)` returns local intensity, gradients,
  valid mask, valid fraction, and gradient energy.

## Verification

Current host verification covers:

- finite full-frame image readout,
- latest-causal timestamp checks,
- local patch shape, masks, gradients, and quality,
- display normalization kept separate from float reconstruction.

Full ROS1 runtime verification still requires a sourced ROS1/catkin workspace.
Use `./build_ros1.sh` for that independent build.
