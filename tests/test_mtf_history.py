import json
from types import SimpleNamespace

import numpy as np

from multicam.core.services.mtf_history import MtfHistoryStore


def frame(timestamp=1234567890):
    return SimpleNamespace(
        timestamp_ns=timestamp, camera_id="cam/1", frame_number=7,
        pixel_format="RGB888", bit_depth=8,
        metadata={"capture_quality": "maximum_sensor_resolution", "ExposureTime": 1000},
    )


def test_capture_is_stored_once_and_reused(tmp_path):
    store = MtfHistoryStore(tmp_path)
    image = np.zeros((40, 60, 3), dtype=np.uint8)
    camera = {"id": "cam/1", "name": "OV64", "model": "ov64a40", "backend": "picamera2"}
    result = {"mode": "usaf_bar", "valid": True, "modulation": .75, "roi_pixels": [2, 3, 30, 35]}
    one = store.save_measurement(frame=frame(), image=image, camera=camera, mode="usaf_bar", roi=[2,3,30,35], quadrilateral=None, result=result)
    two = store.save_measurement(frame=frame(), image=image, camera=camera, mode="usaf_bar", roi=[4,5,32,36], quadrilateral=None, result=result)
    assert one["capture_id"] == two["capture_id"]
    assert len(list((tmp_path / "captures").glob("*.png"))) == 1
    assert len(store.list_measurements()) == 2


def test_history_survives_new_store_instance(tmp_path):
    store = MtfHistoryStore(tmp_path)
    image = np.zeros((40, 60), dtype=np.uint8)
    result = {"mode": "slanted_edge", "valid": False, "mtf50_cycles_per_pixel": .2, "roi_pixels": [1,2,30,35]}
    saved = store.save_measurement(frame=frame(), image=image, camera={"id":"cam/1","name":"Cam"}, mode="slanted_edge", roi=[1,2,30,35], quadrilateral=None, result=result)
    reopened = MtfHistoryStore(tmp_path)
    item = reopened.get_measurement(saved["measurement_id"])
    assert item["summary"] == "MTF50 0.2000 cy/px"
    assert item["validity"] == "review"
    assert reopened.capture_image_path(item["capture_id"]).exists()
    assert reopened.annotated_image_path(item["measurement_id"]).exists()
