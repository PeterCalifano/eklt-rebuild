# EKLT: Asynchronous, Photometric Feature Tracking using Events and Frames

[<img src="images/thumbnail.png" width="400">](https://youtu.be/ZyD1YPW1h4U)

This repository implements the 2019 IJCV paper
[**EKLT: Asynchronous, Photometric Feature Tracking using Events and
Frames**](http://rpg.ifi.uzh.ch/docs/IJCV19_Gehrig.pdf) by
[Daniel Gehrig](https://danielgehrig18.github.io/),
[Henri Rebecq](http://henri.rebecq.fr),
[Guillermo Gallego](http://www.guillermogallego.es), and
[Davide Scaramuzza](http://rpg.ifi.uzh.ch/people_scaramuzza.html).
The original feature-tracking evaluation package is available
[here](https://github.com/uzh-rpg/rpg_feature_tracking_analysis).

## Citation

If you use this code, please cite:

```bibtex
@Article{Gehrig19ijcv,
  author        = {Daniel Gehrig and Henri Rebecq and Guillermo Gallego and
                  Davide Scaramuzza},
  title         = {{EKLT}: Asynchronous, Photometric Feature Tracking using Events and Frames},
  journal       = "Int. J. Comput. Vis.",
  year          = 2019,
}
```

## Overview

EKLT tracks frame-initialized features asynchronously between images using
events. This repository preserves that original ROS1 frame-backed path and also
provides:

- one ROS-free C++17 `libeklt-rebuild` containing EKLT orchestration, FIBAR
  reconstruction, visualization, and wrapper adapters;
- an alternative FIBAR-backed event-only initialization path;
- a unified Python 3.12 distribution and MATLAB R2024b gtwrap interface;
- an experimental ROS2 Jazzy EventPacket overlay;
- a validated single-sequence ELOPE reconstruction and tracking pipeline.

The frame-backed and event-only initialization modes are first-class
alternatives. The ROS1 and ROS2 layers remain transport adapters around the
shared native implementation.

## Build and install

Initialize the required FIBAR checkout and build the ROS-free native library
out of source:

```bash
git submodule update --init lib/fibar_lib
./build_lib.sh --docs --install --package --source-package
```

`--clean` removes only a named `build/<name>` directory whose CMake cache
belongs to this checkout. It rejects the repository root, the aggregate
`build/` directory, symlink escape, non-CMake directories, and foreign build
trees.

Profiling and cross-toolchain configuration are explicit:

```bash
./build_lib.sh --profile
./build_lib.sh \
  --toolchain cmake/toolchains/defaults/aarch64-linux-gnu.cmake \
  --skip-tests
```

Cross compilers, sysroots, and target dependencies remain
environment-provided.

### Python 3.12 and MATLAB R2024b

Initialize gtwrap, then build either generated interface:

```bash
git submodule update --init lib/wrap
./build_lib.sh --python
./build_lib.sh --matlab
```

Build a relocatable Python wheel only after CMake has generated the exact
native-artifact manifest:

```bash
python3.12 -m pip wheel --no-build-isolation --no-deps \
  --wheel-dir build/wheels python
```

The shared wheel contains the generated extension and only its required
`libeklt-rebuild` runtime, with loader-relative paths. The static wheel contains
only the extension. See the
[`eklt-rebuild` Python distribution guide](doc/eklt_rebuild_python_wrapper.md)
and the [FIBAR Python facade guide](doc/fibar_python_wrapper.md).

MATLAB support targets R2024b and requires the documented system C++ runtime
preload. See the [MATLAB wrapper guide](doc/fibar_matlab_wrapper.md).

### ROS1 Noetic

Build the original tracker in an independently managed catkin workspace:

```bash
./build_ros1.sh \
  --workspace "$HOME/eklt_catkin_ws" \
  --import-dependencies \
  --jobs 1
source "$HOME/eklt_catkin_ws/devel/setup.bash"
```

Download `boxes_6dof.bag` from the
[Event Camera Dataset](http://rpg.ifi.uzh.ch/davis_data.html), then run the
frame-backed tracker:

```bash
roslaunch eklt_rebuild eklt.launch \
  bag:=/path/to/boxes_6dof.bag \
  tracks_file_txt:=/tmp/eklt_tracks.txt \
  v:=1
```

Enable the alternative event-only initialization explicitly:

```bash
roslaunch eklt_rebuild eklt.launch \
  bag:=/path/to/boxes_6dof.bag \
  event_only_mode:=true \
  bootstrap:=events \
  tracks_file_txt:=/tmp/eklt_event_only_tracks.txt
```

View the available gflags in a sourced workspace with:

```bash
rosrun eklt_rebuild eklt_node --help
```

The default paper configuration keeps `min_corners=0`. Raise it, for example
to `50`, when continuous feature replenishment is required.

### ROS2 Jazzy and official ELOPE

Build the independent overlay:

```bash
./build_ros2.sh --workspace "$PWD/eklt_ros2_ws" --jobs 1
source "$PWD/eklt_ros2_ws/install/setup.bash"
```

After building the Python wrapper, run one official ELOPE sequence through
FIBAR diagnostics, EventPacket conversion, ROS2 EKLT tracking, analysis, and
video generation:

```bash
scripts/download_elope_dataset.sh --output-dir data/elope --first-only
scripts/run_official_elope_event_only_pipeline_demo.sh \
  --input data/elope/test/0028.npz \
  --output-dir outputs/official_elope_event_only \
  --overlay-setup "$PWD/eklt_ros2_ws/install/setup.bash"
```

The pipeline validates its JSON, CSV, track, plot, and video artifacts. Its
stable contract and accepted full-sequence evidence are documented in:

- [Single-sequence ELOPE artifact contract](doc/elope_single_sequence_pipeline.md)
- [Official ELOPE acceptance report](doc/developments/official_elope_acceptance_report.md)
- [ROS2 event-only guide](doc/ros2_event_only.md)
- [Event-only architecture guide](doc/eklt_events_only.md)
- [Known limitations](doc/known_limitations.md)

## Track format and evaluation

Track files contain one whitespace-delimited observation per row:

| feature id | timestamp [s] | x [px] | y [px] |
| ---: | ---: | ---: | ---: |
| 0 | 1468940293.922985274 | 187.032 | 132.671 |
| 2 | 1468940293.958816290 | 204.603 | 105.360 |
| 1 | 1468940293.957388878 | 222.378 | 104.176 |

The Stage 19 readers require a nonnegative integer feature ID, finite
coordinates and timestamp, and nondecreasing time per feature. Strictly
validate generated example artifacts with:

```bash
PYTHONPATH=python python3.12 scripts/evaluate_outputs.py \
  outputs/official_elope_event_only/tracking
```

The original
[feature-tracking analysis package](https://github.com/uzh-rpg/rpg_feature_tracking_analysis)
can consume the same track representation for dataset-specific error
evaluation.

## Visualization

The ROS1 tracker publishes its feature overlay on `/feature_tracks`. The ROS2
overlay publishes the equivalent bounded `bgr8` image on
`/eklt/feature_tracks` for standard tools such as `rqt_image_view`.

<img src="images/feature_tracks_preview.png" width="600">

The overlay shows feature centers, flow directions, and optionally IDs and
patch outlines. No repository-owned GUI is required.

## Additional event-camera resources

- [Event-based Vision Survey](http://rpg.ifi.uzh.ch/docs/EventVisionSurvey.pdf)
- [Event-based Vision Resources](https://github.com/uzh-rpg/event-based_vision_resources)
- [Event Camera Dataset](http://rpg.ifi.uzh.ch/davis_data.html)
- [Event Camera Simulator](http://rpg.ifi.uzh.ch/esim)
- [RPG event-camera research](http://rpg.ifi.uzh.ch/research_dvs.html)
- [EKLT ECCV 2018 paper](http://rpg.ifi.uzh.ch/docs/ECCV18_Gehrig.pdf)
