from __future__ import annotations

import io

from flask import Blueprint, Response, jsonify, render_template, request
from PIL import Image

from multicam.core.state import CameraLayer, ViewState


def create_alignment_blueprint(
    *,
    manager,
    broker,
    alignment_state,
    alignment_service,
    compositor,
    orientation_store,
):
    blueprint = Blueprint("alignment", __name__)

    def oriented_size(frame, camera_id):
        height, width = frame.image.shape[:2]
        orientation = orientation_store.get(camera_id)

        if orientation.rotation_deg in (90, 270):
            width, height = height, width

        return int(width), int(height)

    def serialize_transform(transform):
        if transform is None:
            return None

        return {
            "model": transform.model,
            "matrix": [list(row) for row in transform.matrix],
            "x": transform.x,
            "y": transform.y,
            "rotation_deg": transform.rotation_deg,
            "scale_x": transform.scale_x,
            "scale_y": transform.scale_y,
            "source_size": transform.source_size,
            "reference_size": transform.reference_size,
            "source_points": transform.source_points,
            "reference_points": transform.reference_points,
            "created_at": transform.created_at,
        }

    def serialize_alignment(auto_match=None):
        current = alignment_state.get()
        frozen = {
            item.camera_id: item
            for item in alignment_service.frozen_info()
        }
        frozen_items = list(frozen.values())
        cameras = []
        reference_frame = (
            broker.get_latest(current.reference_camera_id)
            if current.reference_camera_id
            else None
        )
        reference_size = None

        if reference_frame is not None:
            reference_size = oriented_size(
                reference_frame,
                current.reference_camera_id,
            )

        for camera in manager.list_cameras():
            stream = broker.get_state(camera.id)
            frame = broker.get_latest(camera.id)
            accepted = current.transforms.get(camera.id)
            draft = current.drafts.get(camera.id)

            if camera.id == current.reference_camera_id:
                status = "reference"
            elif draft is not None:
                status = "preview"
            elif accepted is not None:
                frame_size = (
                    oriented_size(frame, camera.id)
                    if frame is not None
                    else None
                )
                status = (
                    "mode_mismatch"
                    if frame_size != accepted.source_size
                    or reference_size != accepted.reference_size
                    else "aligned"
                )
            else:
                status = "unaligned"

            cameras.append({
                "id": camera.id,
                "name": camera.name,
                "backend": camera.backend,
                "model": camera.model,
                "connected": camera.connected,
                "running": stream.running,
                "has_frame": frame is not None,
                "last_error": stream.last_error,
                "role": (
                    "reference"
                    if camera.id == current.reference_camera_id
                    else "target"
                    if camera.id == current.target_camera_id
                    else None
                ),
                "alignment_status": status,
                "frozen": camera.id in frozen,
                "can_undo": camera.id in current.previous,
                "transform": serialize_transform(draft or accepted),
            })

        result = {
            "reference_camera_id": current.reference_camera_id,
            "target_camera_id": current.target_camera_id,
            "cameras": cameras,
            "frozen_frames": [
                {
                    "camera_id": item.camera_id,
                    "timestamp_ns": item.timestamp_ns,
                    "monotonic_timestamp_ns": item.monotonic_timestamp_ns,
                    "width": item.width,
                    "height": item.height,
                    "pixel_format": item.pixel_format,
                    "frame_number": item.frame_number,
                }
                for item in frozen_items
            ],
            "timestamp_skew_ns": alignment_service.timestamp_skew_ns(
                frozen_items
            ),
        }

        if auto_match is not None:
            result["auto_match"] = {
                "reference_point": {
                    "x": auto_match.reference_point[0],
                    "y": auto_match.reference_point[1],
                },
                "target_point": {
                    "x": auto_match.target_point[0],
                    "y": auto_match.target_point[1],
                },
                "score": auto_match.score,
                "uniqueness": auto_match.uniqueness,
                "confidence": auto_match.confidence,
                "patch_size": auto_match.patch_size,
            }

        return result

    @blueprint.route("/alignment")
    def alignment_page():
        return render_template("alignment.html")

    @blueprint.route("/api/alignment")
    def alignment_api():
        return jsonify(serialize_alignment())

    @blueprint.route("/api/alignment/selection", methods=["PATCH"])
    def alignment_selection_api():
        data = request.get_json(silent=True) or {}
        reference_id = data.get("reference_camera_id")
        target_id = data.get("target_camera_id")
        known_ids = {camera.id for camera in manager.list_cameras()}

        if reference_id not in known_ids or target_id not in known_ids:
            return jsonify({"error": "Select two known cameras"}), 400

        for camera_id in (reference_id, target_id):
            stream = broker.get_state(camera_id)

            if not stream.running or broker.get_latest(camera_id) is None:
                return jsonify({
                    "error": (
                        "Camera is not streaming with frames: "
                        f"{camera_id}"
                    )
                }), 400

        try:
            alignment_state.select(reference_id, target_id)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        return jsonify(serialize_alignment())

    @blueprint.route("/api/alignment/freeze", methods=["POST"])
    def alignment_freeze_api():
        current = alignment_state.get()

        if not current.reference_camera_id or not current.target_camera_id:
            return jsonify({
                "error": "Select reference and target cameras first"
            }), 400

        camera_ids = [
            camera.id
            for camera in manager.list_cameras()
            if broker.get_state(camera.id).running
            and broker.get_latest(camera.id) is not None
        ]

        if (
            current.reference_camera_id not in camera_ids
            or current.target_camera_id not in camera_ids
        ):
            return jsonify({
                "error": (
                    "Reference and target must both be streaming with frames"
                )
            }), 400

        try:
            alignment_service.freeze(camera_ids)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        # A new frozen frame set starts a new measurement. Preserve the last
        # accepted transform, but never leave a draft from the prior frames
        # available for accidental acceptance.
        alignment_state.reject(current.target_camera_id)

        return jsonify(serialize_alignment())

    @blueprint.route("/api/alignment/point-pair", methods=["POST"])
    def alignment_point_pair_api():
        data = request.get_json(silent=True) or {}

        try:
            reference_point = (
                float(data["reference_point"]["x"]),
                float(data["reference_point"]["y"]),
            )
            target_point = (
                float(data["target_point"]["x"]),
                float(data["target_point"]["y"]),
            )
            alignment_service.set_point_pair(
                reference_point=reference_point,
                target_point=target_point,
            )
        except (KeyError, TypeError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400

        return jsonify(serialize_alignment())

    @blueprint.route("/api/alignment/point-pairs", methods=["POST"])
    def alignment_point_pairs_api():
        data = request.get_json(silent=True) or {}

        try:
            reference_points = [
                (float(point["x"]), float(point["y"]))
                for point in data["reference_points"]
            ]
            target_points = [
                (float(point["x"]), float(point["y"]))
                for point in data["target_points"]
            ]
            alignment_service.set_point_pairs(
                reference_points=reference_points,
                target_points=target_points,
            )
        except (KeyError, TypeError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400

        return jsonify(serialize_alignment())

    @blueprint.route("/api/alignment/auto-point", methods=["POST"])
    def alignment_auto_point_api():
        data = request.get_json(silent=True) or {}

        try:
            reference_point = (
                float(data["reference_point"]["x"]),
                float(data["reference_point"]["y"]),
            )
            auto_match = alignment_service.auto_align(
                reference_point=reference_point,
            )
        except (KeyError, TypeError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400

        return jsonify(serialize_alignment(auto_match=auto_match))

    @blueprint.route("/api/alignment/nudge", methods=["POST"])
    def alignment_nudge_api():
        data = request.get_json(silent=True) or {}

        try:
            alignment_service.nudge(
                x_delta=float(data["x_delta"]),
                y_delta=float(data["y_delta"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400

        return jsonify(serialize_alignment())

    def alignment_action(action):
        camera_id = alignment_state.get().target_camera_id

        if camera_id is None:
            return jsonify({"error": "No target camera selected"}), 400

        if not action(camera_id):
            return jsonify({
                "error": "No alignment change is available"
            }), 400

        return jsonify(serialize_alignment())

    @blueprint.route("/api/alignment/accept", methods=["POST"])
    def alignment_accept_api():
        return alignment_action(alignment_state.accept)

    @blueprint.route("/api/alignment/reject", methods=["POST"])
    def alignment_reject_api():
        return alignment_action(alignment_state.reject)

    @blueprint.route("/api/alignment/undo", methods=["POST"])
    def alignment_undo_api():
        return alignment_action(alignment_state.undo)

    @blueprint.route("/api/alignment/reset", methods=["POST"])
    def alignment_reset_api():
        alignment_state.reset()
        return jsonify(serialize_alignment())

    def jpeg_response(image):
        buffer = io.BytesIO()
        Image.fromarray(image).save(buffer, format="JPEG", quality=90)
        return Response(buffer.getvalue(), mimetype="image/jpeg")

    @blueprint.route("/alignment/frame/<path:camera_id>")
    def alignment_frame(camera_id):
        frame = alignment_service.get_frozen(camera_id)

        if frame is None:
            return jsonify({"error": "No frozen frame for camera"}), 404

        try:
            image = compositor.orient_display_image(
                frame.image,
                orientation_store.get(camera_id),
            )
        except (TypeError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400

        return jpeg_response(image)

    @blueprint.route("/alignment/preview")
    def alignment_preview():
        current = alignment_state.get()
        reference_id = current.reference_camera_id
        target_id = current.target_camera_id

        if reference_id is None or target_id is None:
            return jsonify({"error": "No alignment selection"}), 400

        reference = alignment_service.get_frozen(reference_id)
        target = alignment_service.get_frozen(target_id)

        if reference is None or target is None:
            return jsonify({"error": "Freeze frames first"}), 404

        preview_state = ViewState(layers=[
            CameraLayer(camera_id=reference_id, opacity=1.0, z_order=0),
            CameraLayer(camera_id=target_id, opacity=0.5, z_order=1),
        ])
        image = compositor.compose(
            {reference_id: reference, target_id: target},
            preview_state,
            registrations=alignment_state.effective_transforms(),
            orientations=orientation_store.snapshot(),
            reference_camera_id=reference_id,
        )

        if image is None:
            return jsonify({"error": "Unable to render preview"}), 400

        return jpeg_response(image)

    return blueprint
