from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any
import json
import os

import numpy as np
from PIL import Image, ImageDraw


class MtfHistoryStore:
    """Persistent MTF captures and measurements.

    A capture is stored once (lossless PNG). Multiple measurements can reference
    it, keeping 64 MP camera sessions from duplicating the source image.
    """

    def __init__(self, root: str | Path | None = None):
        base = root or os.environ.get("MULTICAM_MTF_DATA", "data/mtf")
        self.root = Path(base)
        self.captures = self.root / "captures"
        self.measurements = self.root / "measurements"
        self.captures.mkdir(parents=True, exist_ok=True)
        self.measurements.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    @staticmethod
    def _jsonable(value: Any) -> Any:
        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, dict):
            return {str(k): MtfHistoryStore._jsonable(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [MtfHistoryStore._jsonable(v) for v in value]
        return value

    @staticmethod
    def _utc_stamp(timestamp_ns: int) -> str:
        return datetime.fromtimestamp(timestamp_ns / 1e9, tz=timezone.utc).isoformat()

    @staticmethod
    def _image_for_pil(image: np.ndarray) -> Image.Image:
        values = np.asarray(image)
        if values.dtype == np.uint16 and values.ndim == 2:
            return Image.fromarray(values, mode="I;16")
        if values.dtype != np.uint8:
            lo, hi = float(np.min(values)), float(np.max(values))
            if hi > lo:
                values = ((values - lo) * (255.0 / (hi - lo))).clip(0, 255).astype(np.uint8)
            else:
                values = np.zeros(values.shape, dtype=np.uint8)
        return Image.fromarray(values)

    def ensure_capture(self, *, frame, image: np.ndarray, camera: dict[str, Any]) -> dict[str, Any]:
        capture_id = f"cap_{frame.timestamp_ns}_{self._safe(frame.camera_id)}"
        metadata_path = self.captures / f"{capture_id}.json"
        image_path = self.captures / f"{capture_id}.png"
        with self._lock:
            if not image_path.exists():
                self._image_for_pil(image).save(image_path, format="PNG", compress_level=4)
            if not metadata_path.exists():
                payload = {
                    "capture_id": capture_id,
                    "camera_id": frame.camera_id,
                    "camera": camera,
                    "timestamp_ns": frame.timestamp_ns,
                    "timestamp": self._utc_stamp(frame.timestamp_ns),
                    "frame_number": frame.frame_number,
                    "width": int(image.shape[1]),
                    "height": int(image.shape[0]),
                    "pixel_format": frame.pixel_format,
                    "bit_depth": frame.bit_depth,
                    "capture_quality": frame.metadata.get("capture_quality", "live_frame_fallback"),
                    "frame_metadata": self._jsonable(frame.metadata),
                    "source_image": image_path.name,
                }
                metadata_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            return json.loads(metadata_path.read_text(encoding="utf-8"))

    def save_measurement(self, *, frame, image: np.ndarray, camera: dict[str, Any], mode: str,
                         roi, quadrilateral, result: dict[str, Any]) -> dict[str, Any]:
        capture = self.ensure_capture(frame=frame, image=image, camera=camera)
        with self._lock:
            seq = self._next_sequence()
            measurement_id = f"mtf_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{seq:04d}"
            annotated_name = f"{measurement_id}_annotated.jpg"
            annotated_path = self.measurements / annotated_name
            self._save_annotated_preview(image, annotated_path, roi, result)
            valid = self._validity(result)
            summary = self._summary(result)
            payload = {
                "measurement_id": measurement_id,
                "sequence": seq,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "capture_id": capture["capture_id"],
                "camera": camera,
                "width": capture["width"], "height": capture["height"],
                "pixel_format": capture["pixel_format"], "bit_depth": capture["bit_depth"],
                "capture_quality": capture["capture_quality"],
                "mode": mode,
                "roi_pixels": self._jsonable(roi),
                "quadrilateral_pixels": self._jsonable(quadrilateral),
                "validity": valid,
                "summary": summary,
                "algorithm_version": 1,
                "annotated_image": annotated_name,
                "result": self._jsonable(result),
            }
            path = self.measurements / f"{measurement_id}.json"
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            return payload

    def list_measurements(self, limit: int = 100) -> list[dict[str, Any]]:
        records = []
        for path in self.measurements.glob("mtf_*.json"):
            try:
                item = json.loads(path.read_text(encoding="utf-8"))
                records.append({k: item.get(k) for k in (
                    "measurement_id", "sequence", "created_at", "capture_id", "camera",
                    "width", "height", "mode", "validity", "summary"
                )})
            except (OSError, json.JSONDecodeError):
                continue
        records.sort(key=lambda item: item.get("sequence") or 0, reverse=True)
        return records[:limit]

    def get_measurement(self, measurement_id: str) -> dict[str, Any] | None:
        path = self.measurements / f"{self._safe(measurement_id)}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def capture_image_path(self, capture_id: str) -> Path | None:
        path = self.captures / f"{self._safe(capture_id)}.png"
        return path if path.exists() else None

    def annotated_image_path(self, measurement_id: str) -> Path | None:
        item = self.get_measurement(measurement_id)
        if not item:
            return None
        path = self.measurements / Path(item["annotated_image"]).name
        return path if path.exists() else None

    def _next_sequence(self) -> int:
        existing = self.list_measurements(limit=100000)
        return max((int(x.get("sequence") or 0) for x in existing), default=0) + 1

    @staticmethod
    def _safe(value: str) -> str:
        return "".join(c if c.isalnum() or c in "._-" else "_" for c in str(value))[:180]

    @staticmethod
    def _validity(result: dict[str, Any]) -> str:
        if result.get("mode") == "sbir_target":
            groups = result.get("groups") or []
            if not groups:
                return "invalid"
            return "valid" if all(g.get("valid") for g in groups) else "review"
        return "valid" if result.get("valid") else "review"

    @staticmethod
    def _summary(result: dict[str, Any]) -> str:
        mode = result.get("mode")
        if mode == "sbir_target":
            groups = result.get("groups") or []
            valid = int(result.get("valid_group_count") or 0)
            return f"{valid}/{len(groups)} groups valid"
        if mode == "slanted_edge":
            value = result.get("mtf50_cycles_per_pixel")
            return f"MTF50 {value:.4f} cy/px" if isinstance(value, (int, float)) else "MTF50 unavailable"
        modulation = result.get("modulation")
        return f"{100 * modulation:.1f}% modulation" if isinstance(modulation, (int, float)) else "USAF measurement"

    @staticmethod
    def _save_annotated_preview(image: np.ndarray, path: Path, roi, result: dict[str, Any]) -> None:
        values = np.asarray(image)
        source_h, source_w = values.shape[:2]
        scale = min(1.0, 2400.0 / max(source_w, source_h))
        # Downsample the NumPy view before RGB conversion. This avoids creating a
        # second ~184 MB RGB buffer when annotating an OV64 full-resolution still.
        if scale < 1.0:
            step = max(1, int(np.floor(1.0 / scale)))
            values = values[::step, ::step]
            scale_x = values.shape[1] / source_w
            scale_y = values.shape[0] / source_h
        else:
            scale_x = scale_y = 1.0
        pil = MtfHistoryStore._image_for_pil(values).convert("RGB")
        draw = ImageDraw.Draw(pil)
        if roi and len(roi) == 4:
            box = tuple(round(float(v) * (scale_x if i % 2 == 0 else scale_y)) for i, v in enumerate(roi))
            draw.rectangle(box, outline="cyan", width=3)
        if result.get("mode") == "sbir_target" and roi and len(roi) == 4:
            ox, oy = float(roi[0]), float(roi[1])
            for index, group in enumerate(result.get("groups") or [], 1):
                coords = group.get("roi_pixels")
                if coords and len(coords) == 4:
                    gx0, gy0, gx1, gy1 = coords
                    box = tuple(round(v * (scale_x if i % 2 == 0 else scale_y)) for i, v in enumerate((gx0, gy0, gx1, gy1)))
                else:
                    gx0, gy0, gx1, gy1 = group.get("roi", (0, 0, 0, 0))
                    box = tuple(round(v * scale) for v in (ox + gx0, oy + gy0, ox + gx1, oy + gy1))
                draw.rectangle(box, outline=(40, 220, 90) if group.get("valid") else (255, 210, 70), width=3)
                draw.text((box[0] + 4, box[1] + 4), str(index), fill="white", stroke_width=2, stroke_fill="black")
        pil.save(path, format="JPEG", quality=92)
