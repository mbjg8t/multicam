from __future__ import annotations

from dataclasses import asdict, dataclass
from threading import Event, RLock, Thread, current_thread
import time

from multicam.core.cameras import Frame, FrameBroker
from multicam.core.imaging.dsp import DspConfig, DspPipeline, DspPipelineStore


@dataclass(slots=True)
class DspStatus:
    camera_id: str
    running: bool = False
    processed_frames: int = 0
    actual_fps: float = 0.0
    latency_ms: float | None = None
    last_error: str | None = None
    source_frame_number: int | None = None
    config_revision: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


class DspService:
    """Processes broker frames without owning or modifying camera hardware."""

    def __init__(
        self,
        broker: FrameBroker,
        store: DspPipelineStore,
        pipeline: type[DspPipeline] = DspPipeline,
    ):
        self.broker = broker
        self.store = store
        self.pipeline = pipeline
        self._outputs: dict[str, Frame] = {}
        self._statuses: dict[str, DspStatus] = {}
        self._threads: dict[str, Thread] = {}
        self._stops: dict[str, Event] = {}
        self._lock = RLock()

    def configure(self, camera_id: str, **changes) -> DspConfig:
        config = self.store.update(camera_id, **changes)

        if config.enabled:
            self.start(camera_id)
        else:
            self.stop(camera_id)
            with self._lock:
                self._outputs.pop(camera_id, None)

        return config

    def start(self, camera_id: str) -> None:
        with self._lock:
            thread = self._threads.get(camera_id)

            if thread is not None and thread.is_alive():
                return

            stop = Event()
            self._stops[camera_id] = stop
            self._statuses[camera_id] = DspStatus(
                camera_id=camera_id,
                running=True,
                config_revision=self.store.get(camera_id).revision,
            )
            thread = Thread(
                target=self._run,
                args=(camera_id, stop),
                name=f"DspService-{camera_id}",
                daemon=True,
            )
            self._threads[camera_id] = thread
            thread.start()

    def stop(self, camera_id: str) -> None:
        with self._lock:
            stop = self._stops.get(camera_id)
            thread = self._threads.get(camera_id)

        if stop is not None:
            stop.set()
        if thread is not None and thread is not current_thread():
            thread.join(timeout=2.0)

        with self._lock:
            self._threads.pop(camera_id, None)
            self._stops.pop(camera_id, None)
            status = self._statuses.get(camera_id)
            if status is not None:
                status.running = False

    def stop_all(self) -> None:
        with self._lock:
            camera_ids = list(self._threads)

        for camera_id in camera_ids:
            self.stop(camera_id)

    def get_frame(self, camera_id: str, *, processed: bool = True) -> Frame | None:
        if processed and self.store.get(camera_id).enabled:
            with self._lock:
                output = self._outputs.get(camera_id)

            if output is not None:
                return output

        return self.broker.get_latest(camera_id)

    def get_status(self, camera_id: str) -> DspStatus:
        with self._lock:
            status = self._statuses.get(camera_id)
            if status is None:
                return DspStatus(camera_id=camera_id)
            return DspStatus(**status.as_dict())

    def _run(self, camera_id: str, stop: Event) -> None:
        last_key = None
        last_process_time = 0.0
        fps_started = time.monotonic()
        fps_count = 0

        try:
            while not stop.is_set():
                config = self.store.get(camera_id)
                if not config.enabled:
                    break

                minimum_interval = 1.0 / config.max_fps
                remaining = minimum_interval - (time.monotonic() - last_process_time)
                if remaining > 0 and stop.wait(min(remaining, 0.05)):
                    break

                frame = self.broker.get_latest(camera_id)
                if frame is None:
                    stop.wait(0.05)
                    continue

                key = (
                    frame.frame_number,
                    frame.monotonic_timestamp_ns,
                    config.revision,
                )
                if key == last_key:
                    stop.wait(0.01)
                    continue

                started = time.perf_counter()
                image = self.pipeline.process(frame.image, config)
                latency_ms = (time.perf_counter() - started) * 1000.0
                metadata = dict(frame.metadata)
                metadata["dsp"] = {
                    "pipeline": "display",
                    "revision": config.revision,
                    "geometry_preserving": True,
                }
                output = Frame(
                    camera_id=frame.camera_id,
                    image=image,
                    timestamp_ns=frame.timestamp_ns,
                    monotonic_timestamp_ns=frame.monotonic_timestamp_ns,
                    device_timestamp_ns=frame.device_timestamp_ns,
                    width=image.shape[1],
                    height=image.shape[0],
                    pixel_format="RGB8",
                    bit_depth=8,
                    frame_number=frame.frame_number,
                    metadata=metadata,
                )
                last_process_time = time.monotonic()
                last_key = key
                fps_count += 1
                elapsed = last_process_time - fps_started
                actual_fps = fps_count / elapsed if elapsed > 0 else 0.0

                if elapsed >= 2.0:
                    fps_started = last_process_time
                    fps_count = 0

                with self._lock:
                    self._outputs[camera_id] = output
                    status = self._statuses[camera_id]
                    status.running = True
                    status.processed_frames += 1
                    status.actual_fps = actual_fps
                    status.latency_ms = latency_ms
                    status.last_error = None
                    status.source_frame_number = frame.frame_number
                    status.config_revision = config.revision
        except Exception as exc:
            with self._lock:
                status = self._statuses.setdefault(
                    camera_id,
                    DspStatus(camera_id=camera_id),
                )
                status.last_error = str(exc)
        finally:
            with self._lock:
                status = self._statuses.get(camera_id)
                if status is not None:
                    status.running = False
