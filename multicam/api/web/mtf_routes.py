from __future__ import annotations

import io

from flask import Blueprint, Response, jsonify, render_template, request, send_file
from PIL import Image


def create_mtf_blueprint(*, manager, broker, mtf_service, compositor, history_store):
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
                tuple(data.get("roi") or (0, 0, 1, 1)),
                str(data["mode"]),
                str(data.get("roi_space", "normalized")),
                quadrilateral=data.get("quadrilateral"),
            )
        except (KeyError, TypeError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400
        frame = mtf_service.get_frozen(str(data["camera_id"]))
        image = mtf_service.get_oriented_image(str(data["camera_id"]))
        camera_info = next((camera for camera in manager.list_cameras() if camera.id == str(data["camera_id"])), None)
        camera_meta = {
            "id": str(data["camera_id"]),
            "name": getattr(camera_info, "name", str(data["camera_id"])),
            "model": getattr(camera_info, "model", ""),
            "backend": getattr(camera_info, "backend", ""),
        }
        if frame is not None and image is not None:
            measurement = history_store.save_measurement(
                frame=frame, image=image, camera=camera_meta, mode=str(data["mode"]),
                roi=result.get("roi_pixels"), quadrilateral=data.get("quadrilateral"), result=result,
            )
            result["measurement"] = {
                "measurement_id": measurement["measurement_id"],
                "sequence": measurement["sequence"],
                "capture_id": measurement["capture_id"],
                "created_at": measurement["created_at"],
                "validity": measurement["validity"],
                "summary": measurement["summary"],
            }
        return jsonify(result)

    @blueprint.route("/api/mtf/history")
    def mtf_history_api():
        return jsonify({"measurements": history_store.list_measurements()})

    @blueprint.route("/api/mtf/history/<measurement_id>")
    def mtf_history_detail_api(measurement_id):
        item = history_store.get_measurement(measurement_id)
        if item is None:
            return jsonify({"error": "Measurement not found"}), 404
        return jsonify(item)

    @blueprint.route("/api/mtf/history/<measurement_id>/annotated")
    def mtf_history_annotated_api(measurement_id):
        path = history_store.annotated_image_path(measurement_id)
        if path is None:
            return jsonify({"error": "Annotated image not found"}), 404
        return send_file(path, mimetype="image/jpeg")

    @blueprint.route("/api/mtf/captures/<capture_id>/image")
    def mtf_capture_image_api(capture_id):
        path = history_store.capture_image_path(capture_id)
        if path is None:
            return jsonify({"error": "Capture not found"}), 404
        return send_file(path, mimetype="image/png")

    return blueprint
