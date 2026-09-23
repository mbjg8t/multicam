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
const roiTool = document.getElementById('roi-tool');
const outlineTool = document.getElementById('outline-tool');
const panTool = document.getElementById('pan-tool');
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
    if (!roi || !frame.naturalWidth) {
        selection.style.display = 'none';
        return;
    }
    const rect = frame.getBoundingClientRect();
    const left = frame.offsetLeft + roi[0] * rect.width / frame.naturalWidth;
    const top = frame.offsetTop + roi[1] * rect.height / frame.naturalHeight;
    const width = (roi[2] - roi[0]) * rect.width / frame.naturalWidth;
    const height = (roi[3] - roi[1]) * rect.height / frame.naturalHeight;
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
    const scaleX = frame.naturalWidth / rect.width;
    const scaleY = frame.naturalHeight / rect.height;
    roi = [
        Math.round(left * scaleX), Math.round(top * scaleY),
        Math.round((left + width) * scaleX),
        Math.round((top + height) * scaleY)
    ];
    renderSelection();
    return {width: roi[2] - roi[0], height: roi[3] - roi[1]};
}

function renderOutline() {
    if (!frame.naturalWidth) return;
    const rect = frame.getBoundingClientRect();
    Object.assign(chartOverlay.style, {
        display: outline.length ? 'block' : 'none',
        left: `${frame.offsetLeft}px`, top: `${frame.offsetTop}px`,
        width: `${rect.width}px`, height: `${rect.height}px`
    });
    chartOverlay.setAttribute('viewBox', `0 0 ${frame.naturalWidth} ${frame.naturalHeight}`);
    const points = outline.map(point => `${point.x},${point.y}`).join(' ');
    chartPolygon.setAttribute('points', points);
    chartPointsGroup.innerHTML = outline.map((point, index) =>
        `<circle cx="${point.x}" cy="${point.y}" r="7"></circle>` +
        `<text x="${point.x + 11}" y="${point.y - 11}">${index + 1}</text>`
    ).join('');
    document.getElementById('clear-outline').disabled = !outline.length;
}

function setZoom(nextZoom) {
    zoom = Math.max(0.5, Math.min(6, nextZoom));
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
        status('ROI tool: drag a small measurement region; use its handles to refine it.');
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
        const result = await api('/api/mtf/freeze', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({camera_id: camera.value})
        });
        roi = null; outline = []; start = null; resizeHandle = null;
        selection.style.display = 'none'; analyze.disabled = true;
        frame.src = `/api/mtf/frame/${encodeURIComponent(camera.value)}?t=${Date.now()}`;
        const quality = result.capture_quality === 'maximum_sensor_resolution'
            ? 'maximum sensor resolution'
            : 'live-frame fallback';
        document.getElementById('capture-info').textContent =
            `${result.width} × ${result.height} — ${quality}`;
        status(`Frozen ${result.width} × ${result.height} at ${quality}. Select one measurement feature.`);
    } catch (error) { status(error.message, true); }
});

frame.addEventListener('load', () => {
    const availableWidth = Math.max(320, viewport.clientWidth - 58);
    const availableHeight = Math.max(240, window.innerHeight - 280);
    const scale = Math.min(
        1, availableWidth / frame.naturalWidth,
        availableHeight / frame.naturalHeight
    );
    fitWidth = Math.round(frame.naturalWidth * scale);
    ['roi-tool', 'outline-tool', 'pan-tool', 'zoom-out', 'zoom-in', 'zoom-fit']
        .forEach(id => { document.getElementById(id).disabled = false; });
    setZoom(1);
    renderOutline();
});

stage.addEventListener('pointerdown', event => {
    if (!frame.naturalWidth) return;
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
            x: Math.round(point.x * frame.naturalWidth / point.rect.width),
            y: Math.round(point.y * frame.naturalHeight / point.rect.height)
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
        const x = Math.round(point.x * frame.naturalWidth / point.rect.width);
        const y = Math.round(point.y * frame.naturalHeight / point.rect.height);
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
document.getElementById('mode').addEventListener('change', () => {
    updateAnalyzeAvailability();
    if (outline.length === 4 && document.getElementById('mode').value === 'slanted_edge') {
        status('Four-corner ROIs are for USAF analysis. Draw a rectangular ROI around one clean edge.');
    }
});
document.getElementById('zoom-in').addEventListener('click', () => setZoom(zoom * 1.35));
document.getElementById('zoom-out').addEventListener('click', () => setZoom(zoom / 1.35));
document.getElementById('zoom-fit').addEventListener('click', () => setZoom(1));

viewport.addEventListener('wheel', event => {
    if (!frame.naturalWidth) return;
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

function metric(label, value) {
    return `<div class="metric">${label}<strong>${value}</strong></div>`;
}

function frequency(value) {
    return value === null || value === undefined
        ? 'No crossing'
        : `${value.toFixed(4)} cy/px`;
}

function drawCurve(x, y, label) {
    const canvas = document.getElementById('curve');
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, canvas.width, canvas.height);
    if (!x || !y || x.length < 2) return;
    const pad = 45, width = canvas.width - 2 * pad, height = canvas.height - 2 * pad;
    const ymin = Math.min(...y), ymax = Math.max(...y);
    ctx.strokeStyle = '#222'; ctx.strokeRect(pad, pad, width, height);
    ctx.strokeStyle = '#087ec1'; ctx.lineWidth = 2; ctx.beginPath();
    y.forEach((value, index) => {
        const px = pad + width * index / (y.length - 1);
        const py = pad + height * (1 - (value - ymin) / Math.max(1e-9, ymax - ymin));
        index ? ctx.lineTo(px, py) : ctx.moveTo(px, py);
    });
    ctx.stroke(); ctx.fillStyle = '#111'; ctx.font = '16px Arial'; ctx.fillText(label, pad, 25);
}

analyze.addEventListener('click', async () => {
    try {
        const result = await api('/api/mtf/analyze', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                camera_id: camera.value,
                mode: document.getElementById('mode').value,
                roi,
                roi_space: 'pixels',
                quadrilateral: outline.length === 4 ? outline.map(point => [point.x, point.y]) : null
            })
        });
        if (result.mode === 'slanted_edge') {
            document.getElementById('metrics').innerHTML =
                metric('MTF50', frequency(result.mtf50_cycles_per_pixel)) +
                metric('MTF20', frequency(result.mtf20_cycles_per_pixel)) +
                metric('MTF10', frequency(result.mtf10_cycles_per_pixel)) +
                metric('Edge slant', result.slant_degrees.toFixed(2) + '°') +
                metric('Edge isolation', (100 * result.contrast_fraction).toFixed(0) + '%') +
                metric('Valid', result.valid ? 'Yes' : 'Review');
            drawCurve(result.frequency_cycles_per_pixel, result.mtf, 'Normalized MTF');
            status(result.warning || 'Slanted-edge measurement complete.', Boolean(result.warning));
        } else {
            document.getElementById('metrics').innerHTML =
                metric('Bar modulation', (100 * result.modulation).toFixed(1) + '%') +
                metric('Dominant frequency', result.dominant_frequency_cycles_per_pixel.toFixed(4) + ' cy/px') +
                metric('Orientation', result.orientation) + metric('Valid', result.valid ? 'Yes' : 'Review');
            drawCurve(result.profile.map((_, i) => i), result.profile, 'Mean bar profile');
            status(
                result.warning || (result.perspective_rectified
                    ? 'Perspective-corrected USAF measurement complete.'
                    : 'USAF / tri-bar measurement complete.'),
                Boolean(result.warning)
            );
        }
    } catch (error) { status(error.message, true); }
});

loadCameras().catch(error => status(error.message, true));
