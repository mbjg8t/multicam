from __future__ import annotations

from dataclasses import dataclass
from threading import Condition, Event, RLock, Thread
from typing import Callable

from .backend import CameraDevice
from .frame import Frame


@dataclass(slots=True)
class CameraStreamState:
    camera_id: str
    running: bool = False
    frame_count: int = 0
    last_error: str | None = None


class FrameBroker:
    """
    Owns frame acquisition from open CameraDevice instances.

    One worker thread acquires frames from each camera.
    Consumers read the latest frame without directly accessing hardware.
    """

    def __init__(self):
        self._devices: dict[str, CameraDevice] = {}
        self._frames: dict[str, Frame] = {}
        self._states: dict[str, CameraStreamState] = {}

        self._threads: dict[str, Thread] = {}
        self._stop_events: dict[str, Event] = {}

        self._lock = RLock()
        self._condition = Condition(self._lock)

    def add_camera(self, device: CameraDevice) -> None:
        camera_id = device.id

        with self._lock:
            if camera_id in self._devices:
                return

            self._devices[camera_id] = device
            self._states[camera_id] = CameraStreamState(
                camera_id=camera_id
            )

    def remove_camera(self, camera_id: str) -> None:
        self.stop(camera_id)

        with self._lock:
            self._devices.pop(camera_id, None)
            self._frames.pop(camera_id, None)
            self._states.pop(camera_id, None)

    def start(self, camera_id: str) -> None:
        with self._lock:
            if camera_id not in self._devices:
                raise KeyError(camera_id)

            thread = self._threads.get(camera_id)

            if thread is not None and thread.is_alive():
                return

            stop_event = Event()
            self._stop_events[camera_id] = stop_event

            thread = Thread(
                target=self._acquisition_loop,
                args=(camera_id, stop_event),
                name=f"FrameBroker-{camera_id}",
                daemon=True,
            )

            self._threads[camera_id] = thread
            thread.start()

    def stop(self, camera_id: str) -> None:
        with self._lock:
            stop_event = self._stop_events.get(camera_id)
            thread = self._threads.get(camera_id)

        if stop_event is not None:
            stop_event.set()

        if thread is not None:
            thread.join(timeout=3.0)

        with self._lock:
            self._threads.pop(camera_id, None)
            self._stop_events.pop(camera_id, None)

    def start_all(self) -> None:
        with self._lock:
            camera_ids = list(self._devices)

        for camera_id in camera_ids:
            self.start(camera_id)

    def stop_all(self) -> None:
        with self._lock:
            camera_ids = list(self._devices)

        for camera_id in camera_ids:
            self.stop(camera_id)

    def get_latest(self, camera_id: str) -> Frame | None:
        with self._lock:
            return self._frames.get(camera_id)

    def wait_for_frame(
        self,
        camera_id: str,
        after_frame_number: int | None = None,
        timeout: float | None = None,
    ) -> Frame | None:
        def frame_ready() -> bool:
            frame = self._frames.get(camera_id)

            if frame is None:
                return False

            if after_frame_number is None:
                return True

            if frame.frame_number is None:
                return True

            return frame.frame_number > after_frame_number

        with self._condition:
            if not self._condition.wait_for(
                frame_ready,
                timeout=timeout,
            ):
                return None

            return self._frames.get(camera_id)

    def get_state(self, camera_id: str) -> CameraStreamState:
        with self._lock:
            state = self._states.get(camera_id)

            if state is None:
                return CameraStreamState(
                    camera_id=camera_id,
                    running=False,
                    frame_count=0,
                    last_error="Camera is not open or available",
                )

            return CameraStreamState(
                camera_id=state.camera_id,
                running=state.running,
                frame_count=state.frame_count,
                last_error=state.last_error,
            )

    def _acquisition_loop(
        self,
        camera_id: str,
        stop_event: Event,
    ) -> None:
        device = self._devices[camera_id]

        try:
            device.start()

            with self._condition:
                state = self._states[camera_id]
                state.running = True
                state.last_error = None
                self._condition.notify_all()

            while not stop_event.is_set():
                frame = device.get_frame(timeout=1.0)

                if frame is None:
                    continue

                with self._condition:
                    self._frames[camera_id] = frame

                    state = self._states[camera_id]
                    state.frame_count += 1

                    self._condition.notify_all()

        except Exception as exc:
            with self._condition:
                state = self._states[camera_id]
                state.last_error = repr(exc)
                self._condition.notify_all()

        finally:
            try:
                device.stop()
            finally:
                with self._condition:
                    state = self._states[camera_id]
                    state.running = False
                    self._condition.notify_all()
