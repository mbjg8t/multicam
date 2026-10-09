const camera = document.getElementById('camera');
const frame = document.getElementById('frame');
const stage = document.getElementById('stage');
const selection = document.getElementById('selection');
const analyze = document.getElementById('analyze');
const statusLine = document.getElementById('status');
const viewport = document.getElementById('image-viewport');
const crosshairX = document.getElementById('crosshair-x');
const crosshairY = document.getElementById('crosshair-y');
const chartOverlay = document.getElementById('chart-overlay');
const chartPolygon = document.getElementById('chart-polygon');
const chartPointsGroup = document.getElementById('chart-points');
const resultGroups = document.getElementById('result-groups');
const roiTool = document.getElementById('roi-tool');
const outlineTool = document.getElementById('outline-tool');
const panTool = document.getElementById('pan-tool');
let sourceWidth = 0;
let sourceHeight = 0;
let roi = null;
let start = null;
let resizeHandle = null;
let tool = 'roi';
let outline = [];
let fitWidth = 0;
let zoom = 1;
let panStart = null;

const clamp = (value, maximum) => Math.max(0, Math.min(maximum, value));

function framePoint(event) {
    const rect = frame.getBoundingClientRect();
    return {
        x: clamp(event.clientX - rect.left, rect.width),
        y: clamp(event.clientY - rect.top, rect.height),
        rect
    };
}

function renderSelection() {
    if (!roi || !sourceWidth) {
        selection.style.display = 'none';
        return;
    }
    const rect = frame.getBoundingClientRect();
    const left = frame.offsetLeft + roi[0] * rect.width / sourceWidth;
    const top = frame.offsetTop + roi[1] * rect.height / sourceHeight;
    const width = (roi[2] - roi[0]) * rect.width / sourceWidth;
    const height = (roi[3] - roi[1]) * rect.height / sourceHeight;
    Object.assign(selection.style, {
        display: 'block', left: `${left}px`, top: `${top}px`,
        width: `${width}px`, height: `${height}px`
    });
}

function setSelection(startPoint, endPoint, rect) {
    const left = Math.min(startPoint.x, endPoint.x);
    const top = Math.min(startPoint.y, endPoint.y);
    const width = Math.abs(endPoint.x - startPoint.x);
    const height = Math.abs(endPoint.y - startPoint.y);
    const scaleX = sourceWidth / rect.width;
    const scaleY = sourceHeight / rect.height;
    roi = [
        Math.round(left * scaleX), Math.round(top * scaleY),
        Math.round((left + width) * scaleX),
        Math.round((top + height) * scaleY)
    ];
    renderSelection();
    return {width: roi[2] - roi[0], height: roi[3] - roi[1]};
}

function renderOutline() {
    if (!sourceWidth) return;
    const rect = frame.getBoundingClientRect();
    Object.assign(chartOverlay.style, {
        display: outline.length ? 'block' : 'none',
        left: `${frame.offsetLeft}px`, top: `${frame.offsetTop}px`,
        width: `${rect.width}px`, height: `${rect.height}px`
    });
    chartOverlay.setAttribute('viewBox', `0 0 ${sourceWidth} ${sourceHeight}`);
    const points = outline.map(point => `${point.x},${point.y}`).join(' ');
    chartPolygon.setAttribute('points', points);
    chartPointsGroup.innerHTML = outline.map((point, index) =>
        `<circle cx="${point.x}" cy="${point.y}" r="7"></circle>` +
        `<text x="${point.x + 11}" y="${point.y - 11}">${index + 1}</text>`
    ).join('');
    document.getElementById('clear-outline').disabled = !outline.length;
}

function setZoom(nextZoom) {
    zoom = Math.max(0.5, Math.min(32, nextZoom));
    const width = Math.round(fitWidth * zoom);
    frame.style.width = `${width}px`;
    frame.style.height = 'auto';
    document.getElementById('zoom-label').textContent =
        zoom === 1 ? 'Fit' : `${Math.round(zoom * 100)}%`;
    requestAnimationFrame(() => { renderSelection(); renderOutline(); });
}

function setTool(nextTool) {
    tool = nextTool;
    if (tool === 'outline') {
        roi = null;
        start = null;
        resizeHandle = null;
        renderSelection();
        analyze.disabled = true;
    }
    roiTool.classList.toggle('active-tool', tool === 'roi');
    outlineTool.classList.toggle('active-tool', tool === 'outline');
    panTool.classList.toggle('active-tool', tool === 'pan');
    stage.classList.toggle('pan-tool', tool === 'pan');
    if (tool === 'roi') {
        status(document.getElementById('mode').value === 'sbir_target'
            ? 'ROI tool: draw one box around the complete compact SBIR target.'
            : 'ROI tool: drag a small measurement region; use its handles to refine it.');
    } else if (tool === 'outline') {
        status(`Target outline: click four chart corners clockwise (${outline.length}/4 selected).`);
    } else {
        status('Zoom / pan: drag to move the image and use the mouse wheel to zoom.');
    }
}

function updateAnalyzeAvailability() {
    const mode = document.getElementById('mode').value;
    const rectangularReady = roi && roi[2] - roi[0] >= 24 && roi[3] - roi[1] >= 24;
    const quadrilateralReady = mode === 'usaf_bar' && outline.length === 4;
    analyze.disabled = !(rectangularReady || quadrilateralReady);
}

function clearOutline() {
    outline = [];
    renderOutline();
    updateAnalyzeAvailability();
}

async function api(url, options) {
    const response = await fetch(url, options);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Request failed');
    return data;
}

function status(message, error = false) {
    statusLine.textContent = message;
    statusLine.style.color = error ? '#ff8d8d' : '#78c9ff';
}

async function loadCameras() {
    const data = await api('/api/mtf/cameras');
    camera.replaceChildren();
    data.cameras.filter(item => item.running && item.has_frame).forEach(item => {
        const option = document.createElement('option');
        option.value = item.id;
        option.textContent = `${item.name} — ${item.backend}`;
        camera.appendChild(option);
    });
    if (!camera.value) status('No running cameras with frames.', true);
}

document.getElementById('freeze').addEventListener('click', async () => {
    try {
        clearMeasurement();
        const result = await api('/api/mtf/freeze', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({camera_id: camera.value})
        });
        roi = null; outline = []; start = null; resizeHandle = null;
        selection.style.display = 'none'; analyze.disabled = true;
        sourceWidth = result.width; sourceHeight = result.height;
        frame.src = `/api/mtf/frame/${encodeURIComponent(result.camera_id)}?t=${Date.now()}`;
        const qualityLabels = {maximum_sensor_resolution: 'maximum sensor resolution', native_sensor_resolution: 'selected acquisition mode', selected_acquisition_mode: 'selected acquisition mode', live_frame_fallback: 'live-frame fallback'};
        const quality = qualityLabels[result.capture_quality] || result.capture_quality.replaceAll('_', ' ');
        document.getElementById('capture-info').textContent =
            `${result.width}×${result.height} • ${quality}`;
        status(`Frozen ${result.width} × ${result.height} at ${quality}. Select one measurement feature.`);
    } catch (error) { status(error.message, true); }
});

frame.addEventListener('error', () => {
    status('Frozen frame could not be loaded. Freeze again or check the camera stream.', true);
});

frame.addEventListener('load', () => {
    if (!sourceWidth || !sourceHeight) { sourceWidth = frame.naturalWidth; sourceHeight = frame.naturalHeight; }
    const availableWidth = Math.max(320, viewport.clientWidth - 58);
    const availableHeight = Math.max(240, window.innerHeight - 280);
    const scale = Math.min(
        1, availableWidth / sourceWidth,
        availableHeight / sourceHeight
    );
    fitWidth = Math.round(sourceWidth * scale);
    ['roi-tool', 'outline-tool', 'pan-tool', 'zoom-out', 'zoom-in', 'zoom-fit', 'zoom-selection']
        .forEach(id => { document.getElementById(id).disabled = false; });
    setZoom(1);
    renderOutline();
});

stage.addEventListener('pointerdown', event => {
    if (!sourceWidth) return;
    event.preventDefault();
    const point = framePoint(event);
    if (tool === 'pan') {
        panStart = {
            x: event.clientX,
            y: event.clientY,
            scrollLeft: viewport.scrollLeft,
            scrollTop: viewport.scrollTop
        };
        stage.classList.add('dragging');
        stage.setPointerCapture(event.pointerId);
        return;
    }
    const handle = event.target.dataset && event.target.dataset.handle;
    if (handle && roi) {
        resizeHandle = handle;
        stage.setPointerCapture(event.pointerId);
        return;
    }
    if (tool === 'outline') {
        if (outline.length === 4) outline = [];
        outline.push({
            x: Math.round(point.x * sourceWidth / point.rect.width),
            y: Math.round(point.y * sourceHeight / point.rect.height)
        });
        renderOutline();
        updateAnalyzeAvailability();
        status(outline.length === 4
            ? 'Target outline complete. Switch to ROI tool and select one measurement feature.'
            : `Target outline: click corner ${outline.length + 1} of 4 clockwise.`);
        return;
    }
    if (outline.length) clearOutline();
    start = {x: point.x, y: point.y};
    stage.setPointerCapture(event.pointerId);
});

stage.addEventListener('pointermove', event => {
    const point = framePoint(event);
    if (panStart) {
        event.preventDefault();
        viewport.scrollLeft = panStart.scrollLeft - (event.clientX - panStart.x);
        viewport.scrollTop = panStart.scrollTop - (event.clientY - panStart.y);
        return;
    }
    Object.assign(crosshairX.style, {
        display: 'block', left: `${frame.offsetLeft}px`,
        top: `${frame.offsetTop + point.y}px`, width: `${point.rect.width}px`
    });
    Object.assign(crosshairY.style, {
        display: 'block', left: `${frame.offsetLeft + point.x}px`,
        top: `${frame.offsetTop}px`, height: `${point.rect.height}px`
    });
    if (resizeHandle && roi) {
        event.preventDefault();
        const x = Math.round(point.x * sourceWidth / point.rect.width);
        const y = Math.round(point.y * sourceHeight / point.rect.height);
        if (resizeHandle.includes('n')) roi[1] = Math.min(y, roi[3] - 1);
        if (resizeHandle.includes('s')) roi[3] = Math.max(y, roi[1] + 1);
        if (resizeHandle.includes('w')) roi[0] = Math.min(x, roi[2] - 1);
        if (resizeHandle.includes('e')) roi[2] = Math.max(x, roi[0] + 1);
        renderSelection();
        return;
    }
    if (!start) return;
    event.preventDefault();
    setSelection(start, point, point.rect);
});

stage.addEventListener('pointerup', event => {
    if (panStart) {
        panStart = null;
        stage.classList.remove('dragging');
        return;
    }
    if (resizeHandle) {
        resizeHandle = null;
        const width = roi[2] - roi[0], height = roi[3] - roi[1];
        analyze.disabled = width < 24 || height < 24;
        status(`ROI adjusted: ${width} × ${height} pixels.`);
        return;
    }
    if (!start) return;
    event.preventDefault();
    const point = framePoint(event);
    const size = setSelection(start, point, point.rect);
    start = null;
    const valid = size.width >= 24 && size.height >= 24;
    analyze.disabled = !valid;
    status(
        valid
            ? `ROI selected: ${size.width} × ${size.height} pixels.`
            : `ROI is ${size.width} × ${size.height}; select at least 24 × 24 pixels.`,
        !valid
    );
});

stage.addEventListener('pointercancel', () => {
    start = null; resizeHandle = null; panStart = null;
    stage.classList.remove('dragging');
});
stage.addEventListener('pointerleave', () => {
    if (!start && !resizeHandle) {
        crosshairX.style.display = 'none'; crosshairY.style.display = 'none';
    }
});

roiTool.addEventListener('click', () => setTool('roi'));
outlineTool.addEventListener('click', () => {
    if (tool === 'outline' && outline.length) {
        clearOutline();
        status('Target outline cleared. Click four corners clockwise to start again.');
        return;
    }
    setTool('outline');
});
panTool.addEventListener('click', () => setTool('pan'));
document.getElementById('clear-outline').addEventListener('click', () => {
    clearOutline(); status('Target outline cleared.');
});
function applyModeUi() {
    const mode = document.getElementById('mode').value;
    const isUsaf = mode === 'usaf_bar';
    outlineTool.disabled = !sourceWidth || !isUsaf;
    outlineTool.style.display = isUsaf ? '' : 'none';
    document.getElementById('clear-outline').style.display = isUsaf ? '' : 'none';
    if (!isUsaf && outline.length) clearOutline();
    if (!isUsaf && tool === 'outline') setTool('roi');
    if (mode === 'sbir_target') {
        setTool('roi');
        analyze.textContent = 'Analyze SBIR Target';
        document.getElementById('mode-help').textContent = 'Draw one box around all bar groups.';
        status('Draw one box around all bar groups.');
    } else if (mode === 'slanted_edge') {
        setTool('roi');
        analyze.textContent = 'Analyze Edge';
        document.getElementById('mode-help').textContent = 'Select one clean dark-to-bright edge with uniform regions on both sides.';
        status('Select one clean dark-to-bright edge.');
    } else {
        analyze.textContent = 'Analyze Element';
        document.getElementById('mode-help').textContent = 'Select one three-bar element, or use the optional 4-corner target tool for perspective correction.';
        status('Select one USAF three-bar element.');
    }
    updateAnalyzeAvailability();
}

document.getElementById('mode').addEventListener('change', () => {
    clearMeasurement();
    applyModeUi();
});
document.getElementById('zoom-in').addEventListener('click', () => setZoom(zoom * 1.35));
document.getElementById('zoom-out').addEventListener('click', () => setZoom(zoom / 1.35));
document.getElementById('zoom-fit').addEventListener('click', () => setZoom(1));
document.getElementById('zoom-selection').addEventListener('click', () => {
    if (!roi || !sourceWidth) return;
    const roiWidth = roi[2] - roi[0], roiHeight = roi[3] - roi[1];
    const targetScale = Math.min((viewport.clientWidth - 50) / roiWidth, (viewport.clientHeight - 50) / roiHeight);
    const fitScale = fitWidth / sourceWidth;
    setZoom(Math.min(32, targetScale / Math.max(fitScale, 1e-9)));
    requestAnimationFrame(() => {
        const rect = frame.getBoundingClientRect();
        const sx = rect.width / sourceWidth, sy = rect.height / sourceHeight;
        viewport.scrollLeft = frame.offsetLeft + ((roi[0] + roi[2]) / 2) * sx - viewport.clientWidth / 2;
        viewport.scrollTop = frame.offsetTop + ((roi[1] + roi[3]) / 2) * sy - viewport.clientHeight / 2;
    });
});

viewport.addEventListener('wheel', event => {
    if (!sourceWidth) return;
    event.preventDefault();
    const bounds = viewport.getBoundingClientRect();
    const anchorX = event.clientX - bounds.left + viewport.scrollLeft;
    const anchorY = event.clientY - bounds.top + viewport.scrollTop;
    const oldZoom = zoom;
    setZoom(zoom * (event.deltaY < 0 ? 1.18 : 1 / 1.18));
    const ratio = zoom / oldZoom;
    requestAnimationFrame(() => {
        viewport.scrollLeft = anchorX * ratio - (event.clientX - bounds.left);
        viewport.scrollTop = anchorY * ratio - (event.clientY - bounds.top);
    });
}, {passive: false});

function renderResultGroups(groups) {
    if (!groups || !groups.length || !sourceWidth) { resultGroups.innerHTML = ''; return; }
    renderOutline();
    chartOverlay.style.display = 'block';
    resultGroups.innerHTML = groups.map((group, index) => {
        const [x0, y0, x1, y1] = group.roi_pixels;
        const cls = group.valid ? 'valid' : 'review';
        return `<rect class="result-group ${cls}" x="${x0}" y="${y0}" width="${x1-x0}" height="${y1-y0}"></rect>` +
            `<text class="result-label ${cls}" x="${x0 + 5}" y="${Math.max(18, y0 + 22)}">${index + 1}</text>`;
    }).join('');
}

function metric(label, value) {
    return `<div class="metric">${label}<strong>${value}</strong></div>`;
}

function frequency(value) {
    return value === null || value === undefined
        ? 'No crossing'
        : `${value.toFixed(4)} cy/px`;
}

function clearMeasurement() {
    document.getElementById('metrics').innerHTML = '';
    resultGroups.innerHTML = '';
    const canvas = document.getElementById('curve');
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
}

function tickText(value, span) {
    if (Math.abs(span) < 0.1) return value.toFixed(3);
    if (Math.abs(span) < 2) return value.toFixed(2);
    return value.toFixed(0);
}

function drawCurve(x, y, title, xLabel, yLabel) {
    const canvas = document.getElementById('curve');
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, canvas.width, canvas.height);
    if (!x || !y || x.length < 2) return;
    const left = 76, right = 24, top = 40, bottom = 66;
    const width = canvas.width - left - right, height = canvas.height - top - bottom;
    const xmin = Math.min(...x), xmax = Math.max(...x);
    let ymin = Math.min(...y), ymax = Math.max(...y);
    if (title === 'Normalized MTF') { ymin = 0; ymax = Math.max(1, ymax); }
    const xspan = Math.max(1e-9, xmax - xmin), yspan = Math.max(1e-9, ymax - ymin);
    ctx.strokeStyle = '#222'; ctx.strokeRect(left, top, width, height);
    ctx.fillStyle = '#222'; ctx.font = '13px Arial';
    ctx.textAlign = 'center'; ctx.textBaseline = 'top';
    for (let index = 0; index <= 4; index++) {
        const fraction = index / 4;
        const px = left + fraction * width;
        ctx.beginPath(); ctx.moveTo(px, top + height); ctx.lineTo(px, top + height + 5); ctx.stroke();
        ctx.fillText(tickText(xmin + fraction * xspan, xspan), px, top + height + 8);
    }
    ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
    for (let index = 0; index <= 4; index++) {
        const fraction = index / 4;
        const py = top + height * (1 - fraction);
        ctx.beginPath(); ctx.moveTo(left - 5, py); ctx.lineTo(left, py); ctx.stroke();
        ctx.fillText(tickText(ymin + fraction * yspan, yspan), left - 9, py);
    }
    ctx.strokeStyle = '#087ec1'; ctx.lineWidth = 2; ctx.beginPath();
    y.forEach((value, index) => {
        const px = left + width * (x[index] - xmin) / xspan;
        const py = top + height * (1 - (value - ymin) / yspan);
        index ? ctx.lineTo(px, py) : ctx.moveTo(px, py);
    });
    ctx.stroke();
    ctx.fillStyle = '#111'; ctx.font = '15px Arial';
    ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic'; ctx.fillText(title, left, 24);
    ctx.textAlign = 'center'; ctx.fillText(xLabel, left + width / 2, canvas.height - 8);
    ctx.save();
    ctx.translate(17, top + height / 2); ctx.rotate(-Math.PI / 2);
    ctx.fillText(yLabel, 0, 0); ctx.restore();
}

function renderMeasurementSummary(result) {
    const saved = result.measurement;
    if (!saved) return;
    const cameraName = camera.options[camera.selectedIndex]?.textContent?.split(' — ')[0] || camera.value;
    document.getElementById('measurement-summary').innerHTML =
        `<strong>#${saved.sequence} ${cameraName}</strong> — ${modeLabel(result.mode)}<br>` +
        `${sourceWidth}×${sourceHeight} • ${saved.summary} • ${saved.validity.toUpperCase()}`;
}

function modeLabel(value) {
    return value === 'sbir_target' ? 'SBIR' : value === 'slanted_edge' ? 'Slanted edge' : 'USAF tri-bar';
}

function renderAnalysisResult(result) {
if (result.mode === 'slanted_edge') {
        document.getElementById('metrics').innerHTML =
            metric('MTF50', frequency(result.mtf50_cycles_per_pixel)) +
            metric('MTF20', frequency(result.mtf20_cycles_per_pixel)) +
            metric('MTF10', frequency(result.mtf10_cycles_per_pixel)) +
            metric('Edge slant', result.slant_degrees.toFixed(2) + '°') +
            metric('Edge isolation', (100 * result.contrast_fraction).toFixed(0) + '%') +
            metric('Valid', result.valid ? 'Yes' : 'Review');
        drawCurve(
            result.frequency_cycles_per_pixel, result.mtf,
            'Normalized MTF', 'Spatial frequency (cycles/pixel)',
            'Normalized response (unitless)'
        );
        status(result.warning || 'Slanted-edge measurement complete.', Boolean(result.warning));
    } else if (result.mode === 'sbir_target') {
        if (!result._history) renderResultGroups(result.groups);
        const rows = result.groups.map((group, index) =>
            `<tr><td>${index + 1}</td><td>${group.orientation}</td>` +
            `<td>${(100 * group.modulation).toFixed(1)}%</td>` +
            `<td>${group.dominant_frequency_cycles_per_pixel.toFixed(4)} cy/px</td>` +
            `<td>${group.pixels_per_cycle ? group.pixels_per_cycle.toFixed(1) : '—'} px/cycle</td>` +
            `<td>${(100 * (group.detection_confidence ?? 0)).toFixed(0)}%</td>` +
            `<td>${group.valid ? 'Valid' : 'Review'}</td></tr>`
        ).join('');
        document.getElementById('metrics').innerHTML =
            metric('Groups detected', result.groups.length) +
            metric('Valid groups', result.valid_group_count) +
            `<table class="group-results"><thead><tr><th>#</th><th>Bars</th>` +
            `<th>Modulation</th><th>Frequency</th><th>Spacing</th><th>Confidence</th><th>Result</th></tr></thead>` +
            `<tbody>${rows}</tbody></table>`;
        const first = result.groups[0];
        if (first) {
            drawCurve(
                first.profile.map((_, index) => index), first.profile,
                'Group 1 mean bar profile', 'Position across group (pixels)',
                'Relative intensity (DN)'
            );
        }
        status(
            result.warning || `Analyzed ${result.groups.length} SBIR bar groups.`,
            Boolean(result.warning)
        );
    } else {
        document.getElementById('metrics').innerHTML =
            metric('Bar modulation', (100 * result.modulation).toFixed(1) + '%') +
            metric('Dominant frequency', result.dominant_frequency_cycles_per_pixel.toFixed(4) + ' cy/px') +
            metric('Orientation', result.orientation) + metric('Valid', result.valid ? 'Yes' : 'Review');
        drawCurve(
            result.profile.map((_, i) => i), result.profile,
            'Mean bar profile', 'Position across ROI (pixels)',
            'Relative intensity (DN)'
        );
        status(
            result.warning || (result.perspective_rectified
                ? 'Perspective-corrected USAF measurement complete.'
                : 'USAF / tri-bar measurement complete.'),
            Boolean(result.warning)
        );
    }
    renderMeasurementSummary(result);
}

async function loadHistory() {
    const data = await api('/api/mtf/history');
    const host = document.getElementById('history');
    if (!data.measurements.length) { host.textContent = 'No saved tests yet.'; return; }
    host.innerHTML = data.measurements.map(item => {
        const cam = item.camera?.name || item.camera?.id || 'Camera';
        const when = item.created_at ? new Date(item.created_at).toLocaleString() : '';
        return `<button class="history-item" data-id="${item.measurement_id}">` +
            `<span class="seq">#${item.sequence}</span><span><strong>${cam} — ${modeLabel(item.mode)}</strong>` +
            `<span class="detail">${item.width}×${item.height} • ${item.summary} • ${when}</span></span>` +
            `<span class="validity ${item.validity}">${item.validity}</span></button>`;
    }).join('');
}

async function openHistory(measurementId) {
    const item = await api(`/api/mtf/history/${encodeURIComponent(measurementId)}`);
    const result = item.result || {};
    result.measurement = {sequence:item.sequence, summary:item.summary, validity:item.validity};
    result._history = true;
    sourceWidth = item.width; sourceHeight = item.height;
    frame.src = `/api/mtf/history/${encodeURIComponent(measurementId)}/annotated?t=${Date.now()}`;
    document.getElementById('capture-info').textContent = `${item.width} × ${item.height} — saved measurement #${item.sequence}`;
    renderAnalysisResult(result);
    document.getElementById('measurement-summary').innerHTML =
        `<strong>#${item.sequence} ${item.camera?.name || item.camera?.id || 'Camera'}</strong> — ${modeLabel(item.mode)}<br>` +
        `${item.width}×${item.height} • ${item.summary} • ${item.validity.toUpperCase()}` +
        `<br><a href="/api/mtf/captures/${encodeURIComponent(item.capture_id)}/image" target="_blank">Original capture</a>`;
    status(`Loaded saved MTF measurement #${item.sequence}.`);
}

analyze.addEventListener('click', async () => {
    try {
        clearMeasurement();
        const result = await api('/api/mtf/analyze', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                camera_id: camera.value,
                mode: document.getElementById('mode').value,
                roi, roi_space: 'pixels',
                quadrilateral: (document.getElementById('mode').value === 'usaf_bar' && outline.length === 4
                    ? outline.map(point => [point.x, point.y]) : null)
            })
        });
        renderAnalysisResult(result);
        await loadHistory();
    } catch (error) { status(error.message, true); }
});

document.getElementById('history-refresh').addEventListener('click', () => loadHistory().catch(error => status(error.message, true)));
document.getElementById('history').addEventListener('click', event => {
    const button = event.target.closest('.history-item');
    if (button) openHistory(button.dataset.id).catch(error => status(error.message, true));
});

loadCameras().catch(error => status(error.message, true));
loadHistory().catch(error => status(error.message, true));

applyModeUi();
