let alignmentState = null;
let pointPairs = [];
let pendingReferencePoint = null;
let correctionIndex = null;
let fitIsCurrent = false;

const referenceSelect = document.getElementById('reference-camera');
const targetSelect = document.getElementById('target-camera');
const modelSelect = document.getElementById('alignment-model');
const referenceImage = document.getElementById('reference-image');
const targetImage = document.getElementById('target-image');
const previewImage = document.getElementById('preview-image');
const viewportStates = {
    'reference-stage': {zoom: 1, panX: 0, panY: 0, suppressClick: false},
    'target-stage': {zoom: 1, panX: 0, panY: 0, suppressClick: false}
};

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

function modelSpec() {
    return {
        auto: {minimum: 3, maximum: 12, label: 'Guided auto'},
        translation: {minimum: 1, maximum: 1, label: 'Shift'},
        similarity: {minimum: 2, maximum: 12, label: 'Rotation + scale'},
        affine: {minimum: 3, maximum: 12, label: 'Quick affine'},
        homography: {minimum: 6, maximum: 12, label: 'Planar precision'}
    }[modelSelect.value];
}

function modelName(count = pointPairs.length) {
    if (modelSelect.value === 'homography' && count >= 6) return 'Homography';
    if (modelSelect.value === 'auto' && count >= 6) return 'Guided auto';
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

function syncPairMetrics() {
    const transform = selectedCamera()?.transform;
    const metricsAreCurrent = (
        fitIsCurrent &&
        transform?.residuals_px?.length === pointPairs.length &&
        transform?.inlier_mask?.length === pointPairs.length
    );

    pointPairs.forEach((pair, index) => {
        pair.residual = metricsAreCurrent
            ? transform.residuals_px[index]
            : null;
        pair.inlier = metricsAreCurrent
            ? transform.inlier_mask[index]
            : true;
    });
}

function renderPairList() {
    const panel = document.getElementById('fit-panel');
    const list = document.getElementById('point-pair-list');
    const quality = document.getElementById('fit-quality');
    const transform = selectedCamera()?.transform;
    panel.hidden = pointPairs.length === 0;
    list.replaceChildren();

    if (pointPairs.length === 0) return;

    if (
        fitIsCurrent &&
        transform?.rms_error_px !== null &&
        transform?.rms_error_px !== undefined
    ) {
        const accepted = transform.inlier_mask.filter(Boolean).length;
        const outliers = transform.inlier_mask.length - accepted;
        const status = transform.fit_status
            ? `, ${transform.fit_status}`
            : '';
        quality.textContent = (
            `${transform.model}: RMS ${transform.rms_error_px.toFixed(2)} px, ` +
            `max ${transform.max_error_px.toFixed(2)} px, ` +
            `${accepted} used, ${outliers} model outlier(s)${status}` +
            (transform.fit_message ? ` — ${transform.fit_message}` : '')
        );
    } else {
        quality.textContent = `${pointPairs.length} point pair(s) collected`;
    }

    pointPairs.forEach((pair, index) => {
        const item = document.createElement('div');
        item.className = 'point-pair';
        item.classList.toggle('outlier', pair.inlier === false);
        item.classList.toggle('selected', correctionIndex === index);

        const label = document.createElement('span');
        const error = pair.residual === null
            ? ''
            : ` — ${pair.residual.toFixed(1)} px`;
        label.textContent = (
            `#${index + 1}${error}` +
            (pair.inlier === false ? ' model outlier' : '')
        );
        item.append(label);

        const correct = document.createElement('button');
        correct.type = 'button';
        correct.textContent = 'Correct target';
        correct.addEventListener('click', () => {
            correctionIndex = index;
            renderMarkers();
            renderPairList();
            showMessage(
                `Point ${index + 1} selected. Click its correct target location.`
            );
        });
        item.append(correct);

        const remove = document.createElement('button');
        remove.type = 'button';
        remove.textContent = 'Remove';
        remove.addEventListener('click', async () => {
            pointPairs.splice(index, 1);
            correctionIndex = null;

            if (pointPairs.length === 0) {
                await clearMatchPoints();
            } else {
                await submitPointPairs();
            }
        });
        item.append(remove);
        list.append(item);
    });
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
    const pointCountSupported = pointPairs.length === 0 || (
        pointPairs.length >= modelSpec().minimum &&
        pointPairs.length <= modelSpec().maximum
    );
    const accept = document.getElementById('accept');
    accept.disabled = (
        !isPreview || !pointCountSupported || !fitIsCurrent ||
        pendingReferencePoint !== null
    );
    accept.title = accept.disabled
        ? !fitIsCurrent
            ? 'The selected model does not have a valid current fit.'
            : pendingReferencePoint !== null
                ? 'Finish or remove the pending point first.'
                : !pointCountSupported
                    ? `This model requires ${modelSpec().minimum}–` +
                        `${modelSpec().maximum} point pairs.`
                    : 'Create a preview alignment first.'
        : 'Accept this preview alignment.';
    document.getElementById('reject').disabled = !isPreview;
    const undo = document.getElementById('undo');
    undo.disabled = !target?.can_undo;
    undo.title = undo.disabled
        ? 'Undo becomes available after an alignment is accepted.'
        : 'Restore the alignment that existed before the last acceptance.';
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
    const autoMatch = document.getElementById('auto-match');
    autoMatch.disabled = !canAdjust || pointPairs.length < 2;

    if (autoMatch.disabled) autoMatch.checked = false;

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

    syncPairMetrics();
    renderPairList();
}

function imageUrl(cameraId) {
    return `/alignment/frame/${encodeURIComponent(cameraId)}?t=${Date.now()}`;
}

function loadImage(image, url) {
    image.classList.remove('loaded');
    image.onload = () => {
        image.classList.add('loaded');
        applyViewportTransform(image.parentElement, image);
        renderMarkers();
    };
    image.src = url;
}

function viewportState(stage) {
    return viewportStates[stage.id] || {
        zoom: 1,
        panX: 0,
        panY: 0,
        suppressClick: false
    };
}

function applyViewportTransform(stage, image) {
    const viewport = viewportState(stage);
    image.style.transform = (
        `translate(${viewport.panX}px, ${viewport.panY}px) ` +
        `scale(${viewport.zoom})`
    );
    stage.classList.toggle('zoomed', viewport.zoom > 1);
}

function setSelectionZoom(zoom) {
    for (const [stageId, viewport] of Object.entries(viewportStates)) {
        viewport.zoom = zoom;
        viewport.panX = 0;
        viewport.panY = 0;
        const stage = document.getElementById(stageId);
        const image = stage.querySelector('img');
        applyViewportTransform(stage, image);
    }

    renderMarkers();
}

function updateZoomReadout() {
    const values = Object.values(viewportStates).map(item => item.zoom);
    const preset = [1, 2, 4, 8].find(value => (
        values.every(zoom => Math.abs(zoom - value) < 0.001)
    ));
    document.getElementById('selection-zoom').value = (
        preset === undefined ? 'custom' : String(preset)
    );
}

function zoomViewportAt(stage, image, zoom, clientX, clientY) {
    const viewport = viewportState(stage);
    const oldZoom = viewport.zoom;
    const nextZoom = Math.max(1, Math.min(12, zoom));
    const rect = stage.getBoundingClientRect();
    const localX = clientX - rect.left;
    const localY = clientY - rect.top;
    const centerX = rect.width / 2;
    const centerY = rect.height / 2;
    const baseX = centerX + (
        localX - centerX - viewport.panX
    ) / oldZoom;
    const baseY = centerY + (
        localY - centerY - viewport.panY
    ) / oldZoom;

    viewport.zoom = nextZoom;
    viewport.panX = (
        localX - centerX - (baseX - centerX) * nextZoom
    );
    viewport.panY = (
        localY - centerY - (baseY - centerY) * nextZoom
    );

    if (nextZoom === 1) {
        viewport.panX = 0;
        viewport.panY = 0;
    }

    applyViewportTransform(stage, image);
    updateZoomReadout();
    renderMarkers();
}

function clearMarkers(stageId) {
    document.querySelectorAll(
        `#${stageId} .marker, #${stageId} .residual-vector`
    ).forEach(marker => {
        marker.remove();
    });
}

function clearPoints() {
    pointPairs = [];
    pendingReferencePoint = null;
    correctionIndex = null;
    fitIsCurrent = false;
    clearMarkers('reference-stage');
    clearMarkers('target-stage');
    document.getElementById('fit-panel').hidden = true;
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

    const baseLeft = (stageRect.width - width) / 2;
    const baseTop = (stageRect.height - height) / 2;
    const centerX = stageRect.width / 2;
    const centerY = stageRect.height / 2;
    const viewport = viewportState(stage);

    return {
        left: (
            centerX + (baseLeft - centerX) * viewport.zoom + viewport.panX
        ),
        top: (
            centerY + (baseTop - centerY) * viewport.zoom + viewport.panY
        ),
        width: width * viewport.zoom,
        height: height * viewport.zoom,
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

function addMarker(
    stage,
    image,
    point,
    number,
    {pending = false, inlier = true, selected = false} = {}
) {
    if (!image.classList.contains('loaded')) return;

    const rendered = displayedImageRect(stage, image);
    const marker = document.createElement('span');
    marker.className = pending ? 'marker pending' : 'marker';
    marker.classList.toggle('outlier', !inlier);
    marker.classList.toggle('selected', selected);
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

function projectPoint(matrix, point) {
    if (!matrix) return null;

    const denominator = (
        matrix[2][0] * point.x + matrix[2][1] * point.y + matrix[2][2]
    );

    if (Math.abs(denominator) < 1e-12) return null;

    return {
        x: (
            matrix[0][0] * point.x + matrix[0][1] * point.y + matrix[0][2]
        ) / denominator,
        y: (
            matrix[1][0] * point.x + matrix[1][1] * point.y + matrix[1][2]
        ) / denominator
    };
}

function addResidualVector(stage, image, start, end, inlier) {
    if (!image.classList.contains('loaded')) return;

    const rendered = displayedImageRect(stage, image);
    const scaleX = rendered.width / image.naturalWidth;
    const scaleY = rendered.height / image.naturalHeight;
    const startX = rendered.left + start.x * scaleX;
    const startY = rendered.top + start.y * scaleY;
    const endX = rendered.left + end.x * scaleX;
    const endY = rendered.top + end.y * scaleY;
    const deltaX = endX - startX;
    const deltaY = endY - startY;
    const length = Math.hypot(deltaX, deltaY);

    if (length < 1) return;

    const vector = document.createElement('span');
    vector.className = 'residual-vector';
    vector.classList.toggle('outlier', !inlier);
    vector.style.left = `${startX}px`;
    vector.style.top = `${startY}px`;
    vector.style.width = `${length}px`;
    vector.style.transform = `rotate(${Math.atan2(deltaY, deltaX)}rad)`;
    stage.append(vector);
}

function renderMarkers() {
    clearMarkers('reference-stage');
    clearMarkers('target-stage');
    const referenceStage = document.getElementById('reference-stage');
    const targetStage = document.getElementById('target-stage');
    const transform = fitIsCurrent ? selectedCamera()?.transform : null;

    pointPairs.forEach((pair, index) => {
        const options = {
            inlier: pair.inlier !== false,
            selected: correctionIndex === index
        };
        addMarker(
            referenceStage,
            referenceImage,
            pair.reference,
            index + 1,
            options
        );
        const projected = projectPoint(transform?.matrix, pair.target);

        if (projected) {
            addResidualVector(
                referenceStage,
                referenceImage,
                projected,
                pair.reference,
                pair.inlier !== false
            );
        }
        addMarker(
            targetStage,
            targetImage,
            pair.target,
            index + 1,
            options
        );
    });

    if (pendingReferencePoint) {
        addMarker(
            referenceStage,
            referenceImage,
            pendingReferencePoint,
            pointPairs.length + 1,
            {pending: true}
        );
    }
}

async function submitPointPairs(autoMatch = null) {
    try {
        alignmentState = await api('/api/alignment/point-pairs', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                model: modelSelect.value,
                reference_points: pointPairs.map(pair => pair.reference),
                target_points: pointPairs.map(pair => pair.target)
            })
        });
        fitIsCurrent = true;
        syncPairMetrics();
        updateControls();
        renderMarkers();
        loadImage(previewImage, `/alignment/preview?t=${Date.now()}`);

        const spec = modelSpec();
        const count = pointPairs.length;
        const confidence = autoMatch
            ? ` Auto match ${autoMatch.confidence} ` +
                `(${(autoMatch.score * 100).toFixed(0)}%).`
            : '';

        if (count < spec.minimum) {
            const anchorGuidance = count === 2
                ? ' Two manual anchors established; Auto-find is now available.'
                : '';
            showMessage(
                `Point pair ${count} recorded.${confidence} ` +
                `Choose at least ${spec.minimum - count} more, well separated.` +
                anchorGuidance
            );
        } else {
            const fittedModel = selectedCamera()?.transform?.model || modelName(count);
            showMessage(
                `${fittedModel} draft updated from ${count} point pairs.` +
                `${confidence} Add more points for robustness, or inspect ` +
                'the residuals and accept.'
            );
        }
    } catch (error) {
        fitIsCurrent = false;
        updateControls();
        renderMarkers();
        loadImage(previewImage, `/alignment/preview?t=${Date.now()}`);
        showMessage(
            `${error.message} The last valid preview remains displayed but ` +
            'cannot be accepted for the selected model.',
            true
        );
    }
}

async function refitSelectedModel() {
    const spec = modelSpec();
    const count = pointPairs.length;

    if (count === 0) {
        fitIsCurrent = false;
        updateControls();
        showMessage(
            `${spec.label} selected. Existing point pairs will be retained ` +
            'when models are changed.'
        );
        return;
    }

    if (count > spec.maximum) {
        fitIsCurrent = false;
        updateControls();
        renderMarkers();
        loadImage(previewImage, `/alignment/preview?t=${Date.now()}`);
        showMessage(
            `${spec.label} supports at most ${spec.maximum} point pair(s); ` +
            `all ${count} points were retained. Remove extra points or ` +
            'select another model. The last valid preview remains displayed.',
            true
        );
        return;
    }

    await submitPointPairs();
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
        if (viewportState(referenceStage).suppressClick) {
            viewportState(referenceStage).suppressClick = false;
            return;
        }

        const spec = modelSpec();

        if (pointPairs.length >= spec.maximum) {
            showMessage(
                `This model allows at most ${spec.maximum} pairs. ` +
                'Remove a pair or accept the alignment.',
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
        if (viewportState(targetStage).suppressClick) {
            viewportState(targetStage).suppressClick = false;
            return;
        }

        const point = pointFromClick(event, targetStage, targetImage);
        if (point) await recordManualTarget(point);
    });

    installPanHandler(referenceStage, referenceImage);
    installPanHandler(targetStage, targetImage);
}

function installPanHandler(stage, image) {
    let drag = null;

    stage.addEventListener('pointerdown', event => {
        const viewport = viewportState(stage);

        if (event.button !== 0 || viewport.zoom <= 1) return;

        drag = {
            pointerId: event.pointerId,
            startX: event.clientX,
            startY: event.clientY,
            panX: viewport.panX,
            panY: viewport.panY,
            moved: false
        };
        stage.setPointerCapture(event.pointerId);
    });

    stage.addEventListener('pointermove', event => {
        if (!drag || event.pointerId !== drag.pointerId) return;

        const deltaX = event.clientX - drag.startX;
        const deltaY = event.clientY - drag.startY;

        if (!drag.moved && Math.hypot(deltaX, deltaY) < 4) return;

        drag.moved = true;
        const viewport = viewportState(stage);
        viewport.panX = drag.panX + deltaX;
        viewport.panY = drag.panY + deltaY;
        stage.classList.add('panning');
        applyViewportTransform(stage, image);
        renderMarkers();
    });

    const finishPan = event => {
        if (!drag || event.pointerId !== drag.pointerId) return;

        if (drag.moved) viewportState(stage).suppressClick = true;
        stage.classList.remove('panning');
        drag = null;
    };

    stage.addEventListener('pointerup', finishPan);
    stage.addEventListener('pointercancel', finishPan);
    stage.addEventListener('wheel', event => {
        if (!image.classList.contains('loaded')) return;

        event.preventDefault();
        const factor = Math.exp(-event.deltaY * 0.0015);
        zoomViewportAt(
            stage,
            image,
            viewportState(stage).zoom * factor,
            event.clientX,
            event.clientY
        );
    }, {passive: false});
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
        fitIsCurrent = true;
        updateControls();
        loadImage(previewImage, `/alignment/preview?t=${Date.now()}`);
        showMessage('Nudge created a draft alignment. Accept or reject it.');
    } catch (error) {
        showMessage(error.message, true);
    }
}

referenceSelect.addEventListener('change', setSelection);
targetSelect.addEventListener('change', setSelection);
modelSelect.addEventListener('change', refitSelectedModel);
document.getElementById('clear-points').addEventListener('click', clearMatchPoints);
document.getElementById('selection-zoom').addEventListener('change', event => {
    setSelectionZoom(Number(event.target.value));
});
document.getElementById('reset-zoom').addEventListener('click', () => {
    document.getElementById('selection-zoom').value = '1';
    setSelectionZoom(1);
});

document.getElementById('freeze').addEventListener('click', async () => {
    try {
        alignmentState = await api('/api/alignment/freeze', {method: 'POST'});
        clearPoints();
        refreshFrozenImages();
        const skewMs = alignmentState.timestamp_skew_ns / 1_000_000;
        const spec = modelSpec();
        showMessage(
            `Frozen ${alignmentState.frozen_frames.length} cameras; ` +
            `maximum timestamp skew ${skewMs.toFixed(1)} ms. ` +
            `Collect at least ${spec.minimum} well-spaced point pair(s) for ` +
            `${spec.label}; up to ${spec.maximum} improves robustness.`
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
document.getElementById('download-diagnostics').addEventListener('click', async () => {
    try {
        const response = await fetch('/api/alignment/diagnostics', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                model: modelSelect.value,
                reference_points: pointPairs.map(pair => pair.reference),
                target_points: pointPairs.map(pair => pair.target)
            })
        });

        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.error || `Request failed: ${response.status}`);
        }

        const blob = await response.blob();
        const disposition = response.headers.get('Content-Disposition') || '';
        const match = disposition.match(/filename="([^"]+)"/);
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = match?.[1] || 'alignment-diagnostics.zip';
        link.click();
        URL.revokeObjectURL(link.href);
        showMessage('Alignment diagnostics downloaded.');
    } catch (error) {
        showMessage(error.message, true);
    }
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
