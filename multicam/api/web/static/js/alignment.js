let alignmentState = null;
let referencePoint = null;
let targetPoint = null;

const referenceSelect = document.getElementById('reference-camera');
const targetSelect = document.getElementById('target-camera');
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
    return camera.model
        ? `${camera.name} — ${camera.model}`
        : camera.name;
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

    const summary = document.getElementById('transform-summary');
    if (target?.transform) {
        const label = isPreview ? 'Preview' : 'Accepted';
        summary.textContent = (
            `${label}: move X ${target.transform.x.toFixed(1)} px, ` +
            `Y ${target.transform.y.toFixed(1)} px`
        );
    } else {
        summary.textContent = 'No alignment transform for selected target';
    }
}

function imageUrl(cameraId) {
    return `/alignment/frame/${encodeURIComponent(cameraId)}?t=${Date.now()}`;
}

function loadImage(image, url) {
    image.classList.remove('loaded');
    image.onload = () => image.classList.add('loaded');
    image.src = url;
}

function clearMarker(stageId) {
    document.querySelector(`#${stageId} .marker`).style.display = 'none';
}

function clearPoints() {
    referencePoint = null;
    targetPoint = null;
    clearMarker('reference-stage');
    clearMarker('target-stage');
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
        updateControls();
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
    if (!image.classList.contains('loaded')) {
        return null;
    }

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
        y: localY * image.naturalHeight / rendered.height,
        markerX: rendered.left + localX,
        markerY: rendered.top + localY
    };
}

function showMarker(stage, point) {
    const marker = stage.querySelector('.marker');
    marker.style.left = `${point.markerX}px`;
    marker.style.top = `${point.markerY}px`;
    marker.style.display = 'block';
}

async function submitPointPair() {
    if (!referencePoint || !targetPoint) {
        return;
    }

    try {
        alignmentState = await api('/api/alignment/point-pair', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                reference_point: referencePoint,
                target_point: targetPoint
            })
        });
        updateControls();
        loadImage(previewImage, `/alignment/preview?t=${Date.now()}`);
        showMessage('Draft alignment created. Inspect the overlay, then accept or reject it.');
    } catch (error) {
        showMessage(error.message, true);
    }
}

function installPointHandler(stageId, image, isReference) {
    const stage = document.getElementById(stageId);
    stage.addEventListener('click', async event => {
        const point = pointFromClick(event, stage, image);
        if (!point) {
            return;
        }

        showMarker(stage, point);
        const payloadPoint = {x: point.x, y: point.y};

        if (isReference) {
            referencePoint = payloadPoint;
            targetPoint = null;
            clearMarker('target-stage');
            showMessage('Now click the same physical feature in the target image.');
        } else {
            if (!referencePoint) {
                showMessage('Click the reference feature first.', true);
                return;
            }
            targetPoint = payloadPoint;
            await submitPointPair();
        }
    });
}

async function runAction(path, successMessage) {
    try {
        alignmentState = await api(path, {method: 'POST'});
        updateControls();
        loadImage(previewImage, `/alignment/preview?t=${Date.now()}`);
        showMessage(successMessage);
    } catch (error) {
        showMessage(error.message, true);
    }
}

referenceSelect.addEventListener('change', setSelection);
targetSelect.addEventListener('change', setSelection);

document.getElementById('freeze').addEventListener('click', async () => {
    try {
        alignmentState = await api('/api/alignment/freeze', {method: 'POST'});
        clearPoints();
        updateControls();
        refreshFrozenImages();
        const skewMs = alignmentState.timestamp_skew_ns / 1_000_000;
        showMessage(
            `Frozen ${alignmentState.frozen_frames.length} cameras; ` +
            `maximum timestamp skew ${skewMs.toFixed(1)} ms. ` +
            'Click a feature in the reference image.'
        );
    } catch (error) {
        showMessage(error.message, true);
    }
});

document.getElementById('accept').addEventListener('click', () => {
    runAction('/api/alignment/accept', 'Alignment accepted.');
});
document.getElementById('reject').addEventListener('click', () => {
    runAction('/api/alignment/reject', 'Draft rejected; accepted alignment is unchanged.');
});
document.getElementById('undo').addEventListener('click', () => {
    runAction('/api/alignment/undo', 'Last accepted alignment undone.');
});
document.getElementById('reset').addEventListener('click', () => {
    if (window.confirm('Clear every accepted and pending alignment?')) {
        runAction('/api/alignment/reset', 'All runtime alignments cleared.');
    }
});

installPointHandler('reference-stage', referenceImage, true);
installPointHandler('target-stage', targetImage, false);

refresh().catch(error => showMessage(error.message, true));
