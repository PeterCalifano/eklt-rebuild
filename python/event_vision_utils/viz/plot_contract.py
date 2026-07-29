"""Define reader-facing metadata shared by analytical plots.

The contract keeps plot titles and axis units machine-readable for artifact
validation without prescribing one rendering implementation.

Example:
    contract = PlotContract(
        title="Event Rate over Time",
        subtitle="Counts use fixed 10 ms bins.",
        x_label="Time Since First Event [s]",
        y_label="Event Rate [events/s]",
    )
    print(contract.as_dict()["title"])

Output:
    Event Rate over Time
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PlotContract:
    """Describe the visible labels required by one analytical plot.

    Attributes:
        title: Neutral reader-facing plot title.
        subtitle: Sampling, scope, or interpretation detail.
        x_label: Horizontal quantity with units or an explicit scale.
        y_label: Vertical quantity with units or an explicit scale.

    Example:
        contract = PlotContract(
            title="Event Count",
            subtitle="Counts use fixed time bins.",
            x_label="Time [s]",
            y_label="Events [events]",
        )
        print(contract.title)

    Output:
        Event Count
    """

    title: str
    subtitle: str
    x_label: str
    y_label: str

    def __post_init__(self) -> None:
        """Reject incomplete, lowercase, or unitless reader-facing labels."""
        _validate_capitalized_text(self.title, "title")
        _validate_capitalized_text(self.subtitle, "subtitle")
        _validate_axis_label(self.x_label, "horizontal")
        _validate_axis_label(self.y_label, "vertical")

    def as_dict(self) -> dict[str, str]:
        """Return stable JSON-compatible metadata.

        Returns:
            Plot labels keyed by their artifact-schema field names.

        Example:
            contract = PlotContract(
                title="Event Count",
                subtitle="Counts use fixed time bins.",
                x_label="Time [s]",
                y_label="Events [events]",
            )
            print(contract.as_dict()["x_label"])

        Output:
            Time [s]
        """
        return {
            "title": self.title,
            "subtitle": self.subtitle,
            "x_label": self.x_label,
            "y_label": self.y_label,
        }


def _validate_axis_label(label: str, axis_name: str) -> None:
    """Require a capitalized quantity followed by a bracketed unit or scale."""
    _validate_capitalized_text(label, f"{axis_name} axis label")
    if "[" not in label or not label.endswith("]"):
        raise ValueError(
            f"{axis_name} axis label must end with a bracketed unit or scale"
        )


def _validate_capitalized_text(text: str, field_name: str) -> None:
    """Require nonempty text whose first alphabetic character is uppercase."""
    normalized = text.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")

    first_letter = next(
        (character for character in normalized if character.isalpha()),
        None,
    )
    if first_letter is None or not first_letter.isupper():
        raise ValueError(
            f"{field_name} must start with a capital letter"
        )
