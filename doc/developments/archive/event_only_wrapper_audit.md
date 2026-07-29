# Event-Only EKLT Wrapper Audit

> **Archived Stage 0 audit.** The pybind11/setuptools strategy below was
> superseded by the accepted gtwrap Python and MATLAB path from parent-template
> v1.12.1. Current wrapper ownership and packaging are documented in
> `doc/eklt_rebuild_python_wrapper.md` and `doc/fibar_matlab_wrapper.md`.

## Status

- [x] Local wrapper examples inspected.
- [x] Python wrapper strategy selected.
- [x] MATLAB wrapper strategy selected.
- [x] C ABI rejected for v1.
- [x] Wrapper implementation deferred to Stage 3.

## Local Wrapper Findings

### `EventDataGenerationLib/cmake/HandleWrapper.cmake`

- [x] Provides common wrapper helper scaffolding.
- [x] Searches for `.i` files.
- [x] Has MATLAB gtwrap path through `wrap_and_install_library`.
- [x] Has Python gtwrap path but currently stops with fatal error: Python wrapper handling requires update.
- [x] Has placeholder `.i` files in `src/wrap_interface.i` and `src/wrapped_impl/wrapper_placeholder.i`.

Assessment:

- [x] Good reference for `.i` file layout and MATLAB gtwrap path.
- [x] Not ready as Python wrapper path for this task without repair.

### `EventVision_for_SpaceNav/CMakeLists.txt`

- [x] Has older inline gtwrap/MATLAB setup.
- [x] Fetches `wrap` submodule when missing.
- [x] Expects explicit `WRAPPER_INTERFACE_FILES`.
- [x] Includes `MatlabWrap`.
- [x] Has placeholder `src/wrap_interface.i`.

Assessment:

- [x] Useful MATLAB gtwrap reference.
- [x] Not ideal for FIBAR Python wrapper because Python wrapper section is incomplete.

### `SuperEvent`

- [x] Environment references `pybind11` and `nanobind`.
- [x] Local package depends on PyTorch, with optional ONNX export/runtime tooling.
- [x] No direct local C++ extension pattern was selected from this repo for FIBAR.

Assessment:

- [x] Confirms pybind/nanobind dependencies exist in event-repo ecosystem.
- [x] Relevant to future detector-only sparse feature provider design.
- [x] Not part of current implementation; do not add SuperEvent/PyTorch/ONNX dependencies to EKLT core.
- [x] Not enough local build pattern to copy directly.

## Selected Wrapper Strategy

Python:

- [x] Use direct C++ binding with pybind11 plus setuptools C++ extension.
- [x] Expose a small Python class mirroring C++ facade.
- [x] Accept contiguous NumPy arrays for `x`, `y`, `p`, `t_us`.
- [x] Copy C++ image buffer into NumPy output for v1.
- [x] Catch C++ exceptions at binding boundary and translate to Python exceptions.
- [x] Add `.i` file for documentation/portable interface description, but do not depend on gtwrap for Python until helper is fixed.
- [x] Add Python wrapper-facing import path and pybind11 source.

MATLAB:

- [x] Use gtwrap/MEX path if MATLAB and `wrap` are available.
- [x] Keep wrapper interface file separate from Python binding implementation.
- [x] Document build steps even when MATLAB is absent.
- [x] Do not block CI on MATLAB.

C ABI:

- [x] Do not add C ABI in v1.
- [x] Reconsider only if MATLAB/Python toolchain cannot bind C++ class directly.

## C++ Facade Must Be Wrapper-Friendly

Required shape:

- [x] Plain structs for config and event views.
- [x] Explicit ownership and copy semantics.
- [x] No ROS types in public facade.
- [x] No OpenCV types in wrapper-facing method signatures unless needed for C++ callers.
- [x] No exceptions escaping uncaught through wrappers.

Target C++ concepts:

```cpp
struct SEventBatchView {
  const uint16_t* x;
  const uint16_t* y;
  const int8_t* p;
  const int64_t* t_us;
  size_t size;
  int width;
  int height;
};

struct SFibarConfig {
  int width;
  int height;
  int cutoff_num_events;
  bool use_spatial_filter;
};

class CFibarReconstructor {
public:
  explicit CFibarReconstructor(const SFibarConfig& config);
  void reset();
  void acceptEvents(const SEventBatchView& events);
  bool hasImageFor(int64_t t_us) const;
  SReconstructedImageView requestImage(int64_t t_us);
  void copyImageTo(float* output, size_t output_size) const;
};
```

## Wrapper Tests

- [x] Python accepts non-contiguous arrays by copying or rejects with clear error.
- [x] Python accepts contiguous arrays without extra per-event Python loops.
- [x] Python returns `float32` HxW image.
- [x] Python output timestamp is `<= requested_t_us`.
- [x] MATLAB example documents same config and output conventions.
- [x] Wrapper tests do not require ROS.

## Build Commands To Document Later

Python direct wrapper:

```bash
cd python
python setup.py build_ext --inplace
pytest
```

MATLAB wrapper if available:

```bash
cmake -S . -B build -DEKLT_BUILD_MATLAB_WRAPPER=ON
cmake --build build --target matlab_wrapper
```

MATLAB target names remain future optional work.
