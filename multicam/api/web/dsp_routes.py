from __future__ import annotations

import io
import time

from flask import Blueprint, Response, jsonify, render_template, request
from PIL import Image


def create_dsp_blueprint(*, manager, broker, dsp_service, dsp_store, compositor):
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
                "grayscale",
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
            "black_percentile": float,
            "white_percentile": float,
            "gamma": float,
            "denoise_radius": int,
            "sharpen": float,
            "grayscale": bool,
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
            while True:
                frame = (
                    dsp_service.get_frame(camera_id)
                    if variant == "processed"
                    else broker.get_latest(camera_id)
                )
                if frame is None:
                    time.sleep(0.08)
                    continue

                image = compositor.to_display_rgb(frame.image)
                buffer = io.BytesIO()
                Image.fromarray(image).save(buffer, format="JPEG", quality=88)
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + buffer.getvalue()
                    + b"\r\n"
                )
                time.sleep(0.06)

        return Response(
            generate(),
            mimetype="multipart/x-mixed-replace; boundary=frame",
        )

    return blueprint
