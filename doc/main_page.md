# EKLT {#mainpage}

EKLT provides the original ROS1 event-based KLT tracker together with a
ROS-free C++17 implementation, FIBAR event reconstruction, generated wrappers,
and an experimental ROS2 EventPacket overlay.

Start with the repository README, then use the focused guides:

- [Event-only EKLT](eklt_events_only.md)
- [ROS2 event-only overlay](ros2_event_only.md)
- [FIBAR C++ core](fibar_cpp_core.md)
- [`eklt-rebuild` Python distribution](eklt_rebuild_python_wrapper.md)
- [FIBAR Python facade](fibar_python_wrapper.md)
- [FIBAR MATLAB wrapper](fibar_matlab_wrapper.md)
- [Event tuple format](event_tuple_format.md)
- [Single-sequence ELOPE artifacts](elope_single_sequence_pipeline.md)
- [Known limitations](known_limitations.md)

The wrapper API uses Eigen matrices and vectors through the shared gtwrap
interface. Python targets version 3.12 or newer, and MATLAB targets R2024b.

Current upgrade and future streaming work is tracked in:

- [Template-upgrade checkpoint plan](developments/cpp_cuda_template_upgrade_plan.md)
- [Multi-dataset and online-streaming plan](developments/dataset_and_online_streaming_plan.md)

Completed or superseded implementation plans live under
`doc/developments/archive/` and are retained only as historical records.
