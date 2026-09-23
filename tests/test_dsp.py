import time

import numpy as np
import pytest

from multicam.core.cameras import Frame
from multicam.core.imaging.dsp import DspConfig, DspPipeline, DspPipelineStore
from multicam.core.services import DspService
from multicam.core.services import LiveViewService
from multicam.core.state import (
    AlignmentStateStore,
    CameraLayer,
    RegistrationTransform,
    ViewStateStore,
)


class LatestFrameBroker:
    def __init__(self, frame):
        self.frame = frame

    def get_latest(self, camera_id):
        return self.frame if self.frame.camera_id == camera_id else None


class ProcessedFrameSource:
    def __init__(self, frame):
        self.frame = frame
        self.requests = []

    def get_frame(self, camera_id):
        self.requests.append(camera_id)
        return self.frame


def test_dsp_store_validates_and_revisions_configuration():
    store = DspPipelineStore()
    config = store.update(
        "camera:A",
        enabled=True,
        black_percentile=2.0,
        white_percentile=98.0,
        gamma=1.4,
        palette="iron",
    )

    assert config.enabled is True
    assert config.revision == 1
    assert store.get("camera:A") == config

    with pytest.raises(ValueError, match="between"):
        store.update(
            "camera:A",
            black_percentile=20.0,
            white_percentile=10.0,
        )

    with pytest.raises(ValueError, match="Unknown"):
        store.update("camera:A", imaginary_setting=True)


def test_dsp_pipeline_preserves_source_and_outputs_rgb8():
    source = np.asarray((
        (0, 1000, 2000),
        (3000, 4000, 5000),
        (6000, 7000, 8000),
    ), dtype=np.uint16)
    original = source.copy()
    output = DspPipeline.process(
        source,
        DspConfig(
            gamma_mode="gamma",
            gamma=1.2,
            sharpen_mode="unsharp",
            sharpen=1.0,
            palette="iron",
            invert=True,
        ),
    )

    assert output.shape == (3, 3, 3)
    assert output.dtype == np.uint8
    assert np.array_equal(source, original)
    assert np.ptp(output) > 0


def test_dsp_off_modes_preserve_uint8_pixels():
    source = np.asarray((
        ((10, 20, 30), (40, 50, 60)),
        ((70, 80, 90), (100, 110, 120)),
    ), dtype=np.uint8)

    output = DspPipeline.process(source, DspConfig())

    assert np.array_equal(output, source)


@pytest.mark.parametrize("edge_mode", ("sobel", "laplacian"))
def test_dsp_edge_algorithms_detect_a_line(edge_mode):
    source = np.zeros((16, 16), dtype=np.uint8)
    source[:, 8:] = 255

    output = DspPipeline.process(
        source,
        DspConfig(edge_mode=edge_mode, edge_strength=1.0),
    )

    assert output[:, 7:9].max() == 255
    assert np.all(output[:, 0] == 0)


def test_dsp_service_publishes_variant_without_replacing_broker_frame():
    source = np.arange(64, dtype=np.uint16).reshape(8, 8)
    frame = Frame(
        camera_id="camera:A",
        image=source,
        width=8,
        height=8,
        pixel_format="Mono16",
        bit_depth=16,
        frame_number=7,
    )
    broker = LatestFrameBroker(frame)
    store = DspPipelineStore()
    service = DspService(broker, store)

    try:
        service.configure(
            "camera:A",
            enabled=True,
            palette="grayscale",
            max_fps=60,
        )
        deadline = time.monotonic() + 1.0
        processed = None

        while time.monotonic() < deadline:
            processed = service.get_frame("camera:A")
            if processed is not frame:
                break
            time.sleep(0.01)

        assert processed is not None
        assert processed is not frame
        assert processed.image.shape == (8, 8, 3)
        assert processed.metadata["dsp"]["geometry_preserving"] is True
        assert broker.get_latest("camera:A") is frame
        assert frame.image is source

        service.configure("camera:A", enabled=False)
        assert service.get_frame("camera:A") is frame
    finally:
        service.stop_all()


def test_live_view_selects_dsp_variant_for_layer_compositing():
    raw = Frame(
        camera_id="camera:A",
        image=np.full((4, 4, 3), 25, dtype=np.uint8),
    )
    processed = Frame(
        camera_id="camera:A",
        image=np.full((4, 4, 3), 200, dtype=np.uint8),
    )
    broker = LatestFrameBroker(raw)
    dsp = ProcessedFrameSource(processed)
    state = ViewStateStore()
    state.add_layer(CameraLayer(camera_id="camera:A"))
    service = LiveViewService(
        manager=None,
        broker=broker,
        state=state,
        dsp_service=dsp,
    )

    output = service.get_composite()

    assert dsp.requests == ["camera:A"]
    assert np.all(output == 200)

    bypass_preview = service.get_camera_display("camera:A", raw)

    assert dsp.requests == ["camera:A"]
    assert np.all(bypass_preview == 25)


def test_dsp_camera_preview_excludes_other_composite_layers():
    selected = Frame(
        camera_id="camera:A",
        image=np.full((4, 4, 3), 25, dtype=np.uint8),
    )
    other = Frame(
        camera_id="camera:B",
        image=np.full((4, 4, 3), 200, dtype=np.uint8),
    )

    class MultiBroker:
        def get_latest(self, camera_id):
            return {"camera:A": selected, "camera:B": other}.get(camera_id)

    state = ViewStateStore()
    state.add_layer(CameraLayer(camera_id="camera:A", z_order=0))
    state.add_layer(CameraLayer(camera_id="camera:B", z_order=1))
    service = LiveViewService(manager=None, broker=MultiBroker(), state=state)

    composite = service.get_composite()
    preview = service.get_camera_preview("camera:A", selected)

    assert np.all(composite == 200)
    assert np.all(preview == 25)


def test_live_view_applies_alignment_only_after_accept():
    reference = Frame(
        camera_id="reference",
        image=np.zeros((6, 6, 3), dtype=np.uint8),
    )
    target_image = np.zeros((6, 6, 3), dtype=np.uint8)
    target_image[1, 1] = 255
    target = Frame(camera_id="target", image=target_image)

    class AlignmentBroker:
        def get_latest(self, camera_id):
            return {"reference": reference, "target": target}.get(camera_id)

    view = ViewStateStore()
    view.add_layer(CameraLayer(camera_id="target"))
    alignment = AlignmentStateStore()
    alignment.select("reference", "target")
    transform = RegistrationTransform(
        matrix=((1.0, 0.0, 2.0), (0.0, 1.0, 1.0), (0.0, 0.0, 1.0)),
        source_size=(6, 6),
        reference_size=(6, 6),
    )
    alignment.set_draft("target", transform)
    service = LiveViewService(
        manager=None,
        broker=AlignmentBroker(),
        state=view,
        alignment_state=alignment,
    )

    before_accept = service.get_composite()
    assert before_accept[1, 1].tolist() == [255, 255, 255]
    assert before_accept[2, 3].tolist() == [0, 0, 0]

    assert alignment.accept("target") is True
    after_accept = service.get_composite()
    assert after_accept[1, 1].tolist() == [0, 0, 0]
    assert after_accept[2, 3].tolist() == [255, 255, 255]
