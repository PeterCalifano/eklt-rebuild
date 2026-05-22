"""v2e-backed frame-sequence source adapter."""

from __future__ import annotations

from ..config import SequenceSettings, V2EEmulatorSettings
from ..primitives import EventStream, FrameEventStep, FrameSample
from ..sequence import iter_frame_samples


class V2EFrameSequenceSource:
    """Generate event batches from a frame sequence using v2e."""

    def __init__(self, sequence: SequenceSettings, v2e_settings: V2EEmulatorSettings) -> None:
        self._samples = iter_frame_samples(sequence)
        self._settings = v2e_settings

    @property
    def samples(self) -> list[FrameSample]:
        """Loaded frame samples."""

        return self._samples

    def build_steps(self) -> list[FrameEventStep]:
        """Return frame steps with v2e-generated event batches."""

        if not self._samples:
            return []

        emulator = self._build_emulator()
        steps: list[FrameEventStep] = []

        for index, sample in enumerate(self._samples):
            timestamp_s = float(sample.timestamp_ns) / 1.0e9
            events = emulator.generate_events(sample.image_mono8, timestamp_s)
            event_batch = None
            if index > 0:
                event_batch = EventStream.from_v2e_events(
                    events,
                    width=sample.image_mono8.shape[1],
                    height=sample.image_mono8.shape[0],
                    header_timestamp_ns=sample.timestamp_ns,
                )
            steps.append(FrameEventStep(frame=sample, events=event_batch))

        if hasattr(emulator, "cleanup"):
            emulator.cleanup()

        return steps

    def _build_emulator(self):
        try:
            from v2ecore.emulator import EventEmulator
        except ImportError as exc:
            raise RuntimeError(
                "source.kind='v2e_sequence' requires v2e in the active Python environment."
            ) from exc

        return EventEmulator(
            pos_thres=self._settings.pos_thres,
            neg_thres=self._settings.neg_thres,
            sigma_thres=self._settings.sigma_thres,
            cutoff_hz=self._settings.cutoff_hz,
            leak_rate_hz=self._settings.leak_rate_hz,
            refractory_period_s=self._settings.refractory_period_s,
            shot_noise_rate_hz=self._settings.shot_noise_rate_hz,
            photoreceptor_noise=self._settings.photoreceptor_noise,
            leak_jitter_fraction=self._settings.leak_jitter_fraction,
            noise_rate_cov_decades=self._settings.noise_rate_cov_decades,
            seed=self._settings.seed,
            device=self._settings.device,
        )
