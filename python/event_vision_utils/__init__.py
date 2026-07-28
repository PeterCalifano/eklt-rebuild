"""Reusable event-vision utilities with an explicit extraction boundary.

This namespace is distributed with EKLT so its stable generic data contract can
be validated against real consumers before extraction. Core imports stay
independent of EKLT, ROS, FIBAR, and project-local scripts so the namespace can
move to EventDataGenerationLib or a dedicated repository without changing its
public event representation. Native reconstruction adaptation remains in its
own optional subpackage, so importing :class:`EventArray` requires only NumPy.

Example:
    from event_vision_utils import EventArray

    events = EventArray(
        x=[0], y=[0], p=[1], t_us=[5], width=1, height=1
    )
    print(events.size)

Output:
    1
"""

from event_vision_utils.core.event_array import EventArray

__all__ = ["EventArray"]
