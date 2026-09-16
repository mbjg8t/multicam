from __future__ import annotations

import io
import time

from flask import Blueprint, Response, jsonify, render_template, request
import numpy as np
from PIL import Image


def create_dsp_blueprint(
    *,
    manager,
    broker,
    dsp_service,
    dsp_store,
    live_view_service,
):
    blueprint = Blueprint("dsp", __name__)

    def serialize_camera(camera):
        config = dsp_store.get(camera.id)
        status = dsp_service.get_status(camera.id)
        stream = broker.get_state(camera.id)
        frame = broker.get_latest(camera.id)
        return {
            "id": camera.id,
            "name": camera.name,
            "model": camera.model,
            "backend": camera.backend,
            "connected": camera.connected,
            "running": stream.running,
            "has_frame": frame is not None,
            "width": frame.width if frame is not None else None,
            "height": frame.height if frame is not None else None,
            "pixel_format": frame.pixel_format if frame is not None else None,
            "config": config.as_dict(),
            "status": status.as_dict(),
        }

    @blueprint.route("/dsp")
    def dsp_page():
        return render_template("dsp.html")

    @blueprint.route("/api/dsp")
    def dsp_api():
        return jsonify({
            "cameras": [
                serialize_camera(camera)
                for camera in manager.list_cameras()
            ],
            "processors": [
                "levels",
                "gamma",
                "denoise",
                "sharpen",
                "edges",
                "invert",
                "palette",
            ],
        })

    @blueprint.route("/api/dsp/<path:camera_id>", methods=["PATCH"])
    def dsp_camera_api(camera_id):
        camera = next(
            (item for item in manager.list_cameras() if item.id == camera_id),
            None,
        )
        if camera is None:
            return jsonify({"error": "Unknown camera"}), 404

        data = request.get_json(silent=True) or {}
        converters = {
            "enabled": bool,
            "levels_mode": str,
            "black_percentile": float,
            "white_percentile": float,
            "gamma_mode": str,
            "gamma": float,
            "denoise_mode": str,
            "denoise_radius": int,
            "sharpen_mode": str,
            "sharpen": float,
            "edge_mode": str,
            "edge_strength": float,
            "invert": bool,
            "palette": str,
            "max_fps": float,
        }
        changes = {}

        try:
            for key, value in data.items():
                converter = converters.get(key)
                if converter is None:
                    raise ValueError(f"Unknown DSP setting: {key}")
                changes[key] = converter(value)
            dsp_service.configure(camera_id, **changes)
        except (TypeError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400

        return jsonify(serialize_camera(camera))

    @blueprint.route("/dsp/stream/<variant>/<path:camera_id>")
    def dsp_stream(variant, camera_id):
        if variant not in ("raw", "processed"):
            return jsonify({"error": "Unknown DSP stream variant"}), 404
        if manager.get_device(camera_id) is None:
            return jsonify({"error": "Camera is not open"}), 404

        def generate():
            last_key = None
            while True:
                frame = (
                    dsp_service.get_frame(camera_id)
                    if variant == "processed"
                    else broker.get_latest(camera_id)
                )
                if frame is None:
                    time.sleep(0.08)
                    continue

                dsp_metadata = frame.metadata.get("dsp", {})
                key = (
                    id(frame),
                    frame.frame_number,
                    frame.monotonic_timestamp_ns,
                    dsp_metadata.get("revision"),
                )
                if key == last_key:
                    time.sleep(0.02)
                    continue

                image = live_view_service.get_camera_preview(camera_id, frame)
                height, width = image.shape[:2]
                preview_limit = 1280
                if max(width, height) > preview_limit:
                    scale = preview_limit / max(width, height)
                    image = np.asarray(
                        Image.fromarray(image).resize(
                            (
                                max(1, round(width * scale)),
                                max(1, round(height * scale)),
                            ),
                            Image.Resampling.BILINEAR,
                        )
                    )
                buffer = io.BytesIO()
                Image.fromarray(image).save(buffer, format="JPEG", quality=85)
                last_key = key
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + buffer.getvalue()
                    + b"\r\n"
                )
                time.sleep(0.03)

        return Response(
            generate(),
            mimetype="multipart/x-mixed-replace; boundary=frame",
        )

    return blueprint
