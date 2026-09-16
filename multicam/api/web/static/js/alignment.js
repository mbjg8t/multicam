let alignmentState = null;
let pointPairs = [];
let pendingReferencePoint = null;
let correctionIndex = null;

const referenceSelect = document.getElementById('reference-camera');
const targetSelect = document.getElementById('target-camera');
const modelSelect = document.getElementById('alignment-model');
const referenceImage = document.getElementById('reference-image');
const targetImage = document.getElementById('target-image');
const previewImage = document.getElementById('preview-image');

async function api(path, options = {}) {
    const response = await fetch(path, options);
    const data = await response.json();

    if (!response.ok) {
        throw new Error(data.error || `Request failed: ${response.status}`);
    }
    return data;
}

function showMessage(text, isError = false) {
    const message = document.getElementById('message');
    message.textContent = text;
    message.classList.toggle('error', isError);
}

function cameraLabel(camera) {
    return camera.model ? `${camera.name} — ${camera.model}` : camera.name;
}

function requiredPointCount() {
    return Number(modelSelect.value);
}

function modelName(count = pointPairs.length) {
    if (count >= 4) return 'Perspective';
    if (count === 3) return 'Affine';
    if (count === 2) return 'Rotation + scale';
    return 'Translation';
}

function populateSelect(select, selectedId, excludedId) {
    select.replaceChildren();

    for (const camera of alignmentState.cameras) {
        const option = document.createElement('option');
        option.value = camera.id;
        option.textContent = cameraLabel(camera);
        option.disabled = (
            !camera.running || !camera.has_frame || camera.id === excludedId
        );
        option.selected = camera.id === selectedId;
        select.append(option);
    }
}

function selectedCamera() {
    return alignmentState.cameras.find(
        camera => camera.id === alignmentState.target_camera_id
    );
}

function updateControls() {
    populateSelect(
        referenceSelect,
        alignmentState.reference_camera_id,
        alignmentState.target_camera_id
    );
    populateSelect(
        targetSelect,
        alignmentState.target_camera_id,
        alignmentState.reference_camera_id
    );

    const target = selectedCamera();
    const isPreview = target?.alignment_status === 'preview';
    document.getElementById('accept').disabled = !isPreview;
    document.getElementById('reject').disabled = !isPreview;
    document.getElementById('undo').disabled = !target?.can_undo;
    document.getElementById('clear-points').disabled = (
        pointPairs.length === 0 && !pendingReferencePoint
    );

    const frozenIds = new Set(
        alignmentState.frozen_frames.map(frame => frame.camera_id)
    );
    const canAdjust = (
        frozenIds.has(alignmentState.reference_camera_id) &&
        frozenIds.has(alignmentState.target_camera_id)
    );

    document.querySelectorAll('.nudge').forEach(button => {
        button.disabled = !canAdjust;
    });
    document.getElementById('auto-match').disabled = !canAdjust;

    const summary = document.getElementById('transform-summary');
    if (target?.transform) {
        const transform = target.transform;
        const label = isPreview ? 'Preview' : 'Accepted';
        let detail = (
            `${label} ${transform.model}: X ${transform.x.toFixed(1)} px, ` +
            `Y ${transform.y.toFixed(1)} px`
        );

        if (transform.model !== 'translation') {
            detail += `, rotation ${transform.rotation_deg.toFixed(2)}°`;
        }
        if (transform.model === 'similarity') {
            detail += `, scale ${transform.scale_x.toFixed(4)}`;
        }
        summary.textContent = detail;
    } else {
        summary.textContent = 'No alignment transform for selected target';
    }
}

function imageUrl(cameraId) {
    return `/alignment/frame/${encodeURIComponent(cameraId)}?t=${Date.now()}`;
}

function loadImage(image, url) {
    image.classList.remove('loaded');
    image.onload = () => {
        image.classList.add('loaded');
        renderMarkers();
    };
    image.src = url;
}

function clearMarkers(stageId) {
    document.querySelectorAll(`#${stageId} .marker`).forEach(marker => {
        marker.remove();
    });
}

function clearPoints() {
    pointPairs = [];
    pendingReferencePoint = null;
    correctionIndex = null;
    clearMarkers('reference-stage');
    clearMarkers('target-stage');
    updateControls();
}

function refreshFrozenImages() {
    const frozenIds = new Set(
        alignmentState.frozen_frames.map(frame => frame.camera_id)
    );
    const referenceId = alignmentState.reference_camera_id;
    const targetId = alignmentState.target_camera_id;

    if (frozenIds.has(referenceId)) {
        loadImage(referenceImage, imageUrl(referenceId));
    }
    if (frozenIds.has(targetId)) {
        loadImage(targetImage, imageUrl(targetId));
    }
    if (frozenIds.has(referenceId) && frozenIds.has(targetId)) {
        loadImage(previewImage, `/alignment/preview?t=${Date.now()}`);
    }
}

async function refresh() {
    alignmentState = await api('/api/alignment');
    updateControls();
    refreshFrozenImages();
}

async function setSelection() {
    if (
        !referenceSelect.value ||
        !targetSelect.value ||
        referenceSelect.value === targetSelect.value
    ) {
        return;
    }

    try {
        alignmentState = await api('/api/alignment/selection', {
            method: 'PATCH',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                reference_camera_id: referenceSelect.value,
                target_camera_id: targetSelect.value
            })
        });
        clearPoints();
        refreshFrozenImages();
        showMessage('Selection updated. Freeze all running cameras for a new match.');
    } catch (error) {
        showMessage(error.message, true);
        await refresh();
    }
}

function displayedImageRect(stage, image) {
    const stageRect = stage.getBoundingClientRect();
    const imageAspect = image.naturalWidth / image.naturalHeight;
    const stageAspect = stageRect.width / stageRect.height;
    let width;
    let height;

    if (imageAspect > stageAspect) {
        width = stageRect.width;
        height = width / imageAspect;
    } else {
        height = stageRect.height;
        width = height * imageAspect;
    }

    return {
        left: (stageRect.width - width) / 2,
        top: (stageRect.height - height) / 2,
        width,
        height,
        stageRect
    };
}

function pointFromClick(event, stage, image) {
    if (!image.classList.contains('loaded')) return null;

    const rendered = displayedImageRect(stage, image);
    const localX = event.clientX - rendered.stageRect.left - rendered.left;
    const localY = event.clientY - rendered.stageRect.top - rendered.top;

    if (
        localX < 0 || localY < 0 ||
        localX >= rendered.width || localY >= rendered.height
    ) {
        return null;
    }

    return {
        x: localX * image.naturalWidth / rendered.width,
        y: localY * image.naturalHeight / rendered.height
    };
}

function addMarker(stage, image, point, number, pending = false) {
    if (!image.classList.contains('loaded')) return;

    const rendered = displayedImageRect(stage, image);
    const marker = document.createElement('span');
    marker.className = pending ? 'marker pending' : 'marker';
    marker.textContent = number;
    marker.style.left = (
        rendered.left + point.x * rendered.width / image.naturalWidth
    ) + 'px';
    marker.style.top = (
        rendered.top + point.y * rendered.height / image.naturalHeight
    ) + 'px';
    marker.style.display = 'flex';
    stage.append(marker);
}

function renderMarkers() {
    clearMarkers('reference-stage');
    clearMarkers('target-stage');
    const referenceStage = document.getElementById('reference-stage');
    const targetStage = document.getElementById('target-stage');

    pointPairs.forEach((pair, index) => {
        addMarker(referenceStage, referenceImage, pair.reference, index + 1);
        addMarker(targetStage, targetImage, pair.target, index + 1);
    });

    if (pendingReferencePoint) {
        addMarker(
            referenceStage,
            referenceImage,
            pendingReferencePoint,
            pointPairs.length + 1,
            true
        );
    }
}

async function submitPointPairs(autoMatch = null) {
    try {
        alignmentState = await api('/api/alignment/point-pairs', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                reference_points: pointPairs.map(pair => pair.reference),
                target_points: pointPairs.map(pair => pair.target)
            })
        });
        updateControls();
        renderMarkers();
        loadImage(previewImage, `/alignment/preview?t=${Date.now()}`);

        const required = requiredPointCount();
        const count = pointPairs.length;
        const confidence = autoMatch
            ? ` Auto match ${autoMatch.confidence} ` +
                `(${(autoMatch.score * 100).toFixed(0)}%).`
            : '';

        if (count < required) {
            showMessage(
                `Point pair ${count} recorded.${confidence} ` +
                `Choose reference point ${count + 1} far from the prior points.`
            );
        } else {
            showMessage(
                `${modelName(count)} draft created from ${count} point pairs.` +
                `${confidence} Inspect the overlay, then accept, nudge, ` +
                'correct, or reject it.'
            );
        }
    } catch (error) {
        showMessage(error.message, true);
    }
}

async function autoMatchPendingPoint() {
    try {
        showMessage('Searching the target for the matching structure...');
        const result = await api('/api/alignment/auto-point', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({reference_point: pendingReferencePoint})
        });
        const autoMatch = result.auto_match;
        pointPairs.push({
            reference: pendingReferencePoint,
            target: autoMatch.target_point
        });
        pendingReferencePoint = null;
        correctionIndex = pointPairs.length - 1;
        await submitPointPairs(autoMatch);
    } catch (error) {
        correctionIndex = null;
        renderMarkers();
        showMessage(
            `${error.message}. Click the matching target feature manually.`,
            true
        );
    }
}

async function recordManualTarget(point) {
    if (pendingReferencePoint) {
        pointPairs.push({
            reference: pendingReferencePoint,
            target: point
        });
        pendingReferencePoint = null;
        correctionIndex = pointPairs.length - 1;
    } else if (correctionIndex !== null && pointPairs[correctionIndex]) {
        pointPairs[correctionIndex].target = point;
    } else {
        showMessage('Click a reference feature first.', true);
        return;
    }

    await submitPointPairs();
}

function installPointHandlers() {
    const referenceStage = document.getElementById('reference-stage');
    const targetStage = document.getElementById('target-stage');

    referenceStage.addEventListener('click', async event => {
        if (pointPairs.length >= requiredPointCount()) {
            showMessage(
                'This model has all required pairs. Accept or clear points to retry.',
                true
            );
            return;
        }

        const point = pointFromClick(event, referenceStage, referenceImage);
        if (!point) return;

        pendingReferencePoint = point;
        correctionIndex = null;
        renderMarkers();
        updateControls();

        if (document.getElementById('auto-match').checked) {
            await autoMatchPendingPoint();
        } else {
            showMessage(
                `Reference point ${pointPairs.length + 1} selected. ` +
                'Click the same physical feature in the target image.'
            );
        }
    });

    targetStage.addEventListener('click', async event => {
        const point = pointFromClick(event, targetStage, targetImage);
        if (point) await recordManualTarget(point);
    });
}

async function clearMatchPoints() {
    const target = selectedCamera();

    if (target?.alignment_status === 'preview') {
        try {
            alignmentState = await api('/api/alignment/reject', {method: 'POST'});
        } catch (error) {
            showMessage(error.message, true);
            return;
        }
    }

    clearPoints();
    loadImage(previewImage, `/alignment/preview?t=${Date.now()}`);
    showMessage('Match points cleared; accepted alignment is unchanged.');
}

async function runAction(path, successMessage, clearAfter = false) {
    try {
        alignmentState = await api(path, {method: 'POST'});

        if (clearAfter) clearPoints();
        else updateControls();

        loadImage(previewImage, `/alignment/preview?t=${Date.now()}`);
        showMessage(successMessage);
    } catch (error) {
        showMessage(error.message, true);
    }
}

async function nudgeTarget(xDirection, yDirection) {
    const step = Number(document.getElementById('nudge-step').value);

    try {
        alignmentState = await api('/api/alignment/nudge', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                x_delta: xDirection * step,
                y_delta: yDirection * step
            })
        });
        updateControls();
        loadImage(previewImage, `/alignment/preview?t=${Date.now()}`);
        showMessage('Nudge created a draft alignment. Accept or reject it.');
    } catch (error) {
        showMessage(error.message, true);
    }
}

referenceSelect.addEventListener('change', setSelection);
targetSelect.addEventListener('change', setSelection);
modelSelect.addEventListener('change', clearMatchPoints);
document.getElementById('clear-points').addEventListener('click', clearMatchPoints);

document.getElementById('freeze').addEventListener('click', async () => {
    try {
        alignmentState = await api('/api/alignment/freeze', {method: 'POST'});
        clearPoints();
        refreshFrozenImages();
        const skewMs = alignmentState.timestamp_skew_ns / 1_000_000;
        showMessage(
            `Frozen ${alignmentState.frozen_frames.length} cameras; ` +
            `maximum timestamp skew ${skewMs.toFixed(1)} ms. ` +
            `Collect ${requiredPointCount()} point pair(s) for ` +
            `${modelName(requiredPointCount())}.`
        );
    } catch (error) {
        showMessage(error.message, true);
    }
});

document.getElementById('accept').addEventListener('click', () => {
    runAction('/api/alignment/accept', 'Alignment accepted.');
});
document.getElementById('reject').addEventListener('click', () => {
    runAction(
        '/api/alignment/reject',
        'Draft rejected; accepted alignment is unchanged.',
        true
    );
});
document.getElementById('undo').addEventListener('click', () => {
    runAction('/api/alignment/undo', 'Last accepted alignment undone.', true);
});
document.getElementById('reset').addEventListener('click', () => {
    if (window.confirm('Clear every accepted and pending alignment?')) {
        runAction('/api/alignment/reset', 'All runtime alignments cleared.', true);
    }
});

document.querySelectorAll('.nudge').forEach(button => {
    button.addEventListener('click', () => {
        nudgeTarget(Number(button.dataset.x), Number(button.dataset.y));
    });
});

window.addEventListener('resize', renderMarkers);
installPointHandlers();
refresh().catch(error => showMessage(error.message, true));
