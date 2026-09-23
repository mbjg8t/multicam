from __future__ import annotations

import io

from flask import Blueprint, Response, jsonify, render_template, request
from PIL import Image


def create_mtf_blueprint(*, manager, broker, mtf_service, compositor):
    blueprint = Blueprint("mtf", __name__)

    @blueprint.route("/mtf")
    def mtf_page():
        return render_template("mtf.html")

    @blueprint.route("/api/mtf/cameras")
    def mtf_cameras_api():
        cameras = []
        for camera in manager.list_cameras():
            stream = broker.get_state(camera.id)
            cameras.append({
                "id": camera.id,
                "name": camera.name,
                "model": camera.model,
                "backend": camera.backend,
                "running": stream.running,
                "has_frame": broker.get_latest(camera.id) is not None,
                "last_error": stream.last_error,
            })
        return jsonify({"cameras": cameras})

    @blueprint.route("/api/mtf/freeze", methods=["POST"])
    def mtf_freeze_api():
        camera_id = (request.get_json(silent=True) or {}).get("camera_id")
        if not camera_id or manager.get_device(camera_id) is None:
            return jsonify({"error": "Select an open camera"}), 400
        try:
            info = mtf_service.freeze(camera_id)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({
            "camera_id": info.camera_id,
            "width": info.width,
            "height": info.height,
            "timestamp_ns": info.timestamp_ns,
            "frame_number": info.frame_number,
            "capture_quality": info.capture_quality,
        })

    @blueprint.route("/api/mtf/frame/<path:camera_id>")
    def mtf_frame_api(camera_id):
        frame = mtf_service.get_frozen(camera_id)
        if frame is None:
            return jsonify({"error": "Freeze this camera first"}), 404
        image = compositor.to_display_rgb(
            mtf_service.get_oriented_image(camera_id)
        )
        buffer = io.BytesIO()
        Image.fromarray(image).save(buffer, format="JPEG", quality=94)
        return Response(buffer.getvalue(), mimetype="image/jpeg")

    @blueprint.route("/api/mtf/analyze", methods=["POST"])
    def mtf_analyze_api():
        data = request.get_json(silent=True) or {}
        try:
            result = mtf_service.analyze(
                str(data["camera_id"]),
                tuple(data["roi"]),
                str(data["mode"]),
                str(data.get("roi_space", "normalized")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(result)

    return blueprint
