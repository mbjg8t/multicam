from __future__ import annotations

import io
import time

from flask import Blueprint, Response, jsonify, render_template, request
from PIL import Image


def create_focus_blueprint(*, manager, broker, focus_service):
    blueprint = Blueprint("focus", __name__)

    def focus_capabilities(device):
        return [
            capability
            for capability in device.get_capabilities()
            if capability.metadata.get("purpose") == "focus"
        ]

    def serialize_capability(capability):
        return {
            "id": capability.id,
            "name": capability.name,
            "type": capability.type,
            "readable": capability.readable,
            "writable": capability.writable,
            "value": capability.value,
            "minimum": capability.minimum,
            "maximum": capability.maximum,
            "step": capability.step,
            "choices": capability.choices,
            "units": capability.units,
        }

    @blueprint.route("/focus")
    def focus_page():
        return render_template("focus.html")

    @blueprint.route("/api/focus/cameras")
    def focus_cameras_api():
        cameras = []

        for camera in manager.list_cameras():
            stream = broker.get_state(camera.id)
            device = manager.get_device(camera.id)
            capabilities = []

            if device is not None:
                try:
                    capabilities = [
                        serialize_capability(capability)
                        for capability in focus_capabilities(device)
                    ]
                except Exception:
                    capabilities = []

            cameras.append({
                "id": camera.id,
                "name": camera.name,
                "model": camera.model,
                "backend": camera.backend,
                "connected": camera.connected,
                "running": stream.running,
                "has_frame": broker.get_latest(camera.id) is not None,
                "last_error": stream.last_error,
                "focus_capabilities": capabilities,
            })

        return jsonify({"cameras": cameras})

    @blueprint.route("/api/focus/<path:camera_id>/metrics")
    def focus_metrics_api(camera_id):
        if manager.get_device(camera_id) is None:
            return jsonify({"error": "Camera is not open"}), 404

        try:
            sample = focus_service.analyze(
                camera_id,
                center_x=float(request.args.get("x", 0.5)),
                center_y=float(request.args.get("y", 0.5)),
                size=float(request.args.get("size", 0.25)),
            )
        except (TypeError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400

        return jsonify({
            "camera_id": sample.camera_id,
            "frame_number": sample.frame_number,
            "timestamp_ns": sample.timestamp_ns,
            "width": sample.width,
            "height": sample.height,
            "roi": list(sample.roi),
            "tenengrad": sample.tenengrad,
            "laplacian": sample.laplacian,
            "contrast": sample.contrast,
            "lens_position": sample.lens_position,
            "autofocus_state": sample.autofocus_state,
        })

    @blueprint.route(
        "/api/focus/<path:camera_id>/control",
        methods=["POST"],
    )
    def focus_control_api(camera_id):
        device = manager.get_device(camera_id)

        if device is None:
            return jsonify({"error": "Camera is not open"}), 404

        data = request.get_json(silent=True) or {}
        control_id = data.get("control_id")
        capability = next(
            (
                item
                for item in focus_capabilities(device)
                if item.id == control_id and item.writable
            ),
            None,
        )

        if capability is None:
            return jsonify({"error": "Unsupported focus control"}), 400

        value = data.get("value")

        if capability.choices and value not in capability.choices:
            return jsonify({"error": "Unsupported focus-control value"}), 400

        if capability.type in ("float", "integer"):
            try:
                numeric_value = float(value)
            except (TypeError, ValueError):
                return jsonify({"error": "Focus value must be numeric"}), 400

            if (
                capability.minimum is not None
                and numeric_value < float(capability.minimum)
            ) or (
                capability.maximum is not None
                and numeric_value > float(capability.maximum)
            ):
                return jsonify({
                    "error": "Focus value is outside the supported range"
                }), 400

            value = (
                int(numeric_value)
                if capability.type == "integer"
                else numeric_value
            )

        try:
            device.set_control(control_id, value)
        except (TypeError, ValueError, RuntimeError) as exc:
            return jsonify({"error": str(exc)}), 400

        return jsonify({
            "camera_id": camera_id,
            "control_id": control_id,
            "value": value,
        })

    @blueprint.route("/focus/stream/<path:camera_id>")
    def focus_stream(camera_id):
        if manager.get_device(camera_id) is None:
            return jsonify({"error": "Camera is not open"}), 404

        def generate():
            while True:
                try:
                    image = focus_service.display_image(camera_id)
                except ValueError:
                    time.sleep(0.10)
                    continue

                buffer = io.BytesIO()
                Image.fromarray(image).save(buffer, format="JPEG", quality=88)
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + buffer.getvalue()
                    + b"\r\n"
                )
                time.sleep(0.08)

        return Response(
            generate(),
            mimetype="multipart/x-mixed-replace; boundary=frame",
        )

    return blueprint
