
let cameras = [];
let streams = [];
let viewState = null;
const openCameraSettings = new Set();
let lastLayerRenderKey = null;
let hardwareState = null;


async function api(url, options = {}) {
    const response = await fetch(url, options);

    if (!response.ok) {
        const text = await response.text();
        throw new Error(text || response.statusText);
    }

    return response.json();
}


async function refresh() {
    [cameras, streams, viewState, hardwareState] = await Promise.all([
        api('/api/cameras'),
        api('/api/streams'),
        api('/api/state'),
        api('/api/hardware')
    ]);

    renderHardware();

    const layerRenderKey = JSON.stringify({
        cameras: cameras.map(camera => ({
            id: camera.id,
            name: camera.name,
            backend: camera.backend,
            vendor: camera.vendor,
            model: camera.model,
            serial: camera.serial
        })),
        streams: streams.map(stream => ({
            id: stream.id,
            running: stream.running,
            last_error: stream.last_error,
            has_frame: stream.has_frame,
            width: stream.width,
            height: stream.height,
            pixel_format: stream.pixel_format,
            dtype: stream.dtype
        })),
        layers: viewState.layers
    });

    if (layerRenderKey !== lastLayerRenderKey) {
        lastLayerRenderKey = layerRenderKey;
        renderLayers();
    }

    renderAvailableCameras();
}


async function refreshHardware() {
    hardwareState = await api('/api/hardware');
    renderHardware();
}


async function applyHardwareConfiguration() {
    const button = document.getElementById(
        'hardwareApplyButton'
    );
    const resultDiv = document.getElementById(
        'hardwareApplyResult'
    );

    button.disabled = true;
    resultDiv.textContent = 'Applying configuration...';

    try {
        const response = await fetch('/api/hardware/apply', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        const result = await response.json();

        if (!response.ok || !result.success) {
            const errors = result.errors || [];
            throw new Error(
                result.error ||
                errors.join(' | ') ||
                'Configuration apply failed'
            );
        }

        let message = 'Configuration applied.';

        if (result.backup_path) {
            message += ` Backup: ${result.backup_path}.`;
        }

        if (result.reboot_required) {
            message += ' Reboot required.';
        }

        resultDiv.className = 'camera-info stream-ok';
        resultDiv.textContent = message;

        hardwareState = await api('/api/hardware');
        renderHardware();

        // renderHardware clears/rebuilds the hardware presentation,
        // so restore the operation result afterward.
        resultDiv.className = 'camera-info stream-ok';
        resultDiv.textContent = message;
    } catch (error) {
        resultDiv.className = 'camera-info stream-error';
        resultDiv.textContent = error.message;

        await refreshHardware();
    }
}


function hardwareStatusClass(status) {
    return status === 'ready' ? 'stream-ok' : 'stream-error';
}


function renderHardware() {
    const summary = document.getElementById('hardwareSummary');
    const container = document.getElementById('hardwareList');
    const proposed = document.getElementById('hardwareProposed');
    const applyButton = document.getElementById(
        'hardwareApplyButton'
    );

    if (!hardwareState) {
        summary.textContent = 'Hardware status unavailable';
        container.innerHTML = '';
        proposed.innerHTML = '';
        return;
    }

    const autoDetect =
        hardwareState.camera_auto_detect === null
            ? 'Unknown'
            : (hardwareState.camera_auto_detect ? 'On' : 'Off');

    summary.textContent =
        `${hardwareState.platform_model || hardwareState.platform} | ` +
        `Auto detect: ${autoDetect} | ` +
        `Reboot required: ${hardwareState.reboot_required ? 'Yes' : 'No'}`;

    container.innerHTML = '';
    proposed.innerHTML = '';

    if (hardwareState.entries.length === 0) {
        container.innerHTML =
            '<div class="empty">No provisioned CSI cameras detected</div>';
        return;
    }

    hardwareState.entries.forEach(entry => {
        const div = document.createElement('div');
        div.className = 'layer';

        const runtime = entry.runtime;
        const configured = entry.configured;

        const runtimeName = runtime
            ? `${runtime.name} [${runtime.backend}]`
            : 'No runtime camera';

        const overlayText = configured
            ? configured.overlay
            : 'No explicit camera overlay';

        const portText =
            configured && configured.port_hint
                ? configured.port_hint
                : 'not explicitly assigned';

        const pathText =
            runtime && runtime.runtime_path
                ? runtime.runtime_path
                : '';

        div.innerHTML = `
            <div class="layer-title">
                <strong>${escapeHtml(runtimeName)}</strong>
                <span class="${hardwareStatusClass(entry.status)}">
                    ${escapeHtml(entry.status.toUpperCase())}
                </span>
            </div>

            <div class="camera-info">
                Boot overlay: ${escapeHtml(overlayText)}
                | Port hint: ${escapeHtml(portText)}
            </div>

            <div class="camera-info">
                ${escapeHtml(pathText)}
            </div>
        `;

        container.appendChild(div);
    });

    if (hardwareState.errors.length > 0) {
        const errorDiv = document.createElement('div');
        errorDiv.className = 'camera-info stream-error';
        errorDiv.textContent = hardwareState.errors.join(' | ');
        container.appendChild(errorDiv);
    }

    const changes = hardwareState.proposed_changes || [];

    applyButton.disabled = !(
        hardwareState.apply_enabled &&
        changes.length > 0
    );

    applyButton.title = hardwareState.apply_enabled
        ? ''
        : 'Provisioning writes are disabled for this startup.';

    if (changes.length === 0) {
        proposed.textContent = 'No configuration changes proposed.';
    } else {
        changes.forEach(change => {
            const div = document.createElement('div');
            div.className = 'camera-info';

            const params = change.parameters || {};

            const paramText = Object.entries(params)
                .map(([key, value]) =>
                    value === true ? key : `${key}=${value}`
                )
                .join(',');

            let text =
                change.description ||
                change.action ||
                'Configuration change';

            if (change.overlay) {
                text += ` | dtoverlay=${change.overlay}`;

                if (paramText) {
                    text += `,${paramText}`;
                }
            }

            if (change.reboot_required) {
                text += ' | reboot required';
            }

            div.textContent = text;
            proposed.appendChild(div);
        });
    }
}


function cameraById(id) {
    return cameras.find(c => c.id === id);
}


function streamById(id) {
    return streams.find(s => s.id === id);
}


function cameraLabel(camera) {
    if (!camera) {
        return 'Unknown camera';
    }

    return `${camera.name} [${camera.backend}]`;
}


function streamText(stream) {
    if (!stream) {
        return 'No stream status';
    }

    if (stream.last_error) {
        return `ERROR: ${stream.last_error}`;
    }

    if (!stream.running) {
        return 'Stream stopped';
    }

    if (!stream.has_frame) {
        return `Running - waiting for frame (${stream.frame_count} frames)`;
    }

    const details = [
        `${stream.width}x${stream.height}`,
        stream.pixel_format,
        stream.dtype,
        `${stream.frame_count} frames`
    ].filter(Boolean);

    return `Streaming - ${details.join(' | ')}`;
}


function renderLayers() {
    const container = document.getElementById('layerList');
    container.innerHTML = '';

    if (viewState.layers.length === 0) {
        container.innerHTML =
            '<div class="empty">No camera layers</div>';
        return;
    }

    const layers = [...viewState.layers].sort(
        (a, b) => a.z_order - b.z_order
    );

    layers.forEach((layer, index) => {
        const camera = cameraById(layer.camera_id);
        const stream = streamById(layer.camera_id);
        const streamClass =
            stream && stream.running && !stream.last_error
                ? 'stream-ok'
                : 'stream-error';

        const div = document.createElement('div');
        div.className = 'layer';

        div.innerHTML = `
            <div class="layer-title">
                <span class="layer-number">Layer ${index + 1}</span>
                <strong>${cameraLabel(camera)}</strong>
            </div>

            <div class="camera-info">
                ${camera ? `${camera.vendor || ''} ${camera.model || ''}`.trim() : ''}
                ${camera && camera.serial ? ` | Serial ${camera.serial}` : ''}
            </div>

            <div class="camera-info ${streamClass}">
                ${escapeHtml(streamText(stream))}
            </div>

            <div class="row">
                <label>
                    <input
                        type="checkbox"
                        ${layer.enabled ? 'checked' : ''}
                        onchange="setEnabled(
                            '${escapeJs(layer.camera_id)}',
                            this.checked
                        )"
                    >
                    Enabled
                </label>

                <span>Opacity</span>

                <input
                    class="opacity"
                    type="range"
                    min="0"
                    max="1"
                    step="0.01"
                    value="${layer.opacity}"
                    oninput="
                        this.nextElementSibling.textContent =
                        Math.round(this.value * 100) + '%'
                    "
                    onchange="setOpacity(
                        '${escapeJs(layer.camera_id)}',
                        this.value
                    )"
                >

                <span class="value">
                    ${Math.round(layer.opacity * 100)}%
                </span>

                <span class="spacer"></span>

                <button onclick="toggleCameraSettings(
                    '${escapeJs(layer.camera_id)}'
                )">
                    Settings
                </button>

                <button onclick="removeLayer(
                    '${escapeJs(layer.camera_id)}'
                )">
                    Remove
                </button>
            </div>

            <div
                class="camera-settings ${
                    openCameraSettings.has(layer.camera_id)
                        ? 'open'
                        : ''
                }"
                id="settings-${encodeURIComponent(layer.camera_id)}"
            >
                <div class="settings-message">
                    ${
                        openCameraSettings.has(layer.camera_id)
                            ? 'Loading camera settings...'
                            : ''
                    }
                </div>
            </div>
        `;

        container.appendChild(div);

        if (openCameraSettings.has(layer.camera_id)) {
            loadCameraSettings(layer.camera_id).catch(error => {
                console.error(error);
                showStatus('Unable to load camera settings');
            });
        }
    });
}


async function toggleCameraSettings(cameraId) {
    if (openCameraSettings.has(cameraId)) {
        openCameraSettings.delete(cameraId);
        renderLayers();
        return;
    }

    openCameraSettings.add(cameraId);
    renderLayers();
}


const cameraControlTimers = new Map();


function cameraControlSection(capability) {
    const id = capability.id;

    if (
        id === 'cooling_enable' ||
        id === 'cooling_target' ||
        id.includes('temperature')
    ) {
        return 'Sensor';
    }

    if (
        id === 'reverse_x' ||
        id === 'reverse_y'
    ) {
        return 'Orientation';
    }

    return 'Image';
}


function cameraControlDefault(capability) {
    if (
        capability.metadata &&
        capability.metadata.session_default !== undefined &&
        capability.metadata.session_default !== null
    ) {
        return capability.metadata.session_default;
    }

    if (
        capability.value !== undefined &&
        capability.value !== null
    ) {
        return capability.value;
    }

    return null;
}


function cameraSliderSpec(capability, value) {
    if (
        capability.metadata &&
        capability.metadata.ui === 'manual'
    ) {
        return null;
    }

    const minimum = Number(capability.minimum);
    const maximum = Number(capability.maximum);
    const current = Number(value);

    if (
        !Number.isFinite(minimum) ||
        !Number.isFinite(maximum) ||
        maximum <= minimum ||
        !Number.isFinite(current)
    ) {
        return null;
    }

    const useLog =
        minimum > 0 &&
        maximum / minimum >= 100;

    return {
        minimum,
        maximum,
        useLog
    };
}


function valueToSlider(value, spec) {
    value = Number(value);

    if (!spec.useLog) {
        return value;
    }

    const minLog = Math.log(spec.minimum);
    const maxLog = Math.log(spec.maximum);
    const valueLog = Math.log(
        Math.max(spec.minimum, value)
    );

    return (
        (valueLog - minLog) /
        (maxLog - minLog) *
        1000
    );
}


function sliderToValue(sliderValue, spec) {
    sliderValue = Number(sliderValue);

    if (!spec.useLog) {
        return sliderValue;
    }

    const minLog = Math.log(spec.minimum);
    const maxLog = Math.log(spec.maximum);

    return Math.exp(
        minLog +
        (sliderValue / 1000) *
        (maxLog - minLog)
    );
}


function scheduleCameraControl(
    cameraId,
    controlId,
    value,
    delay = 120
) {
    const key = cameraId + '|' + controlId;

    const existing = cameraControlTimers.get(key);

    if (existing) {
        clearTimeout(existing);
    }

    const timer = setTimeout(async () => {
        cameraControlTimers.delete(key);

        try {
            await setCameraControlValue(
                cameraId,
                controlId,
                value
            );
        } catch (error) {
            console.error(error);
            showStatus('Unable to update camera setting');
        }
    }, delay);

    cameraControlTimers.set(key, timer);
}


async function setCameraControlValue(
    cameraId,
    controlId,
    value
) {
    await api(
        '/api/cameras/' +
        encodeURIComponent(cameraId) +
        '/controls',
        {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                control_id: controlId,
                value: value
            })
        }
    );
}


function formatCameraValue(value) {
    const number = Number(value);

    if (!Number.isFinite(number)) {
        return String(value);
    }

    if (Number.isInteger(number)) {
        return String(number);
    }

    if (Math.abs(number) >= 100) {
        return number.toFixed(2).replace(/\\.?0+$/, '');
    }

    return number.toFixed(3).replace(/\\.?0+$/, '');
}


function cameraNumericControl(
    cameraId,
    capability,
    value
) {
    const defaultValue = cameraControlDefault(capability);

    const inputId =
        'control-' +
        encodeURIComponent(cameraId) +
        '-' +
        capability.id;

    const sliderId =
        'slider-' +
        encodeURIComponent(cameraId) +
        '-' +
        capability.id;

    const spec = cameraSliderSpec(
        capability,
        value
    );

    let sliderHtml = '<span></span>';

    if (spec) {
        const sliderMin = spec.useLog
            ? 0
            : spec.minimum;

        const sliderMax = spec.useLog
            ? 1000
            : spec.maximum;

        const sliderStep = spec.useLog
            ? 1
            : (
                capability.step !== null &&
                capability.step !== undefined
                    ? capability.step
                    : 'any'
            );

        const sliderValue = valueToSlider(
            value,
            spec
        );

        sliderHtml = `
            <input
                class="control-slider"
                id="${sliderId}"
                type="range"
                min="${sliderMin}"
                max="${sliderMax}"
                step="${sliderStep}"
                value="${sliderValue}"
                oninput="cameraSliderChanged(
                    '${escapeJs(cameraId)}',
                    '${escapeJs(capability.id)}',
                    this.value,
                    ${spec.minimum},
                    ${spec.maximum},
                    ${spec.useLog ? 'true' : 'false'}
                )"
            >
        `;
    }

    const defaultHtml =
        defaultValue !== null
            ? `
                <div class="control-default">
                    Default:
                    ${escapeHtml(formatCameraValue(defaultValue))}
                    ${escapeHtml(capability.units || '')}
                </div>
            `
            : '';

    return `
        <div class="control-row">
            <div class="control-name">
                ${escapeHtml(capability.name)}
            </div>

            ${sliderHtml}

            <div class="control-value">
                <input
                    id="${inputId}"
                    type="number"
                    value="${escapeHtml(value ?? '')}"
                    ${
                        capability.step !== null &&
                        capability.step !== undefined
                            ? `step="${escapeHtml(capability.step)}"`
                            : 'step="any"'
                    }
                    ${
                        capability.minimum !== null &&
                        capability.minimum !== undefined
                            ? `min="${escapeHtml(capability.minimum)}"`
                            : ''
                    }
                    ${
                        capability.maximum !== null &&
                        capability.maximum !== undefined
                            ? `max="${escapeHtml(capability.maximum)}"`
                            : ''
                    }
                    onkeydown="cameraNumberKeyDown(
                        event,
                        '${escapeJs(cameraId)}',
                        '${escapeJs(capability.id)}'
                    )"
                    onchange="cameraNumberChanged(
                        '${escapeJs(cameraId)}',
                        '${escapeJs(capability.id)}'
                    )"
                >

                <span class="control-unit">
                    ${escapeHtml(capability.units || '')}
                </span>
            </div>

            ${
                defaultValue !== null
                    ? `
                        <button
                            class="control-reset"
                            title="Reset to default"
                            onclick="resetCameraControl(
                                '${escapeJs(cameraId)}',
                                '${escapeJs(capability.id)}',
                                ${JSON.stringify(defaultValue)}
                            )"
                        >↺</button>
                    `
                    : '<span></span>'
            }
        </div>

        ${defaultHtml}
    `;
}


function cameraBooleanControl(
    cameraId,
    capability,
    value
) {
    const defaultValue = cameraControlDefault(capability);

    const inputId =
        'control-' +
        encodeURIComponent(cameraId) +
        '-' +
        capability.id;

    return `
        <div class="control-row">
            <div class="control-name">
                ${escapeHtml(capability.name)}
            </div>

            <div class="control-toggle">
                <input
                    id="${inputId}"
                    type="checkbox"
                    ${value ? 'checked' : ''}
                    onchange="cameraBooleanChanged(
                        '${escapeJs(cameraId)}',
                        '${escapeJs(capability.id)}',
                        this.checked
                    )"
                >
            </div>

            <span></span>

            ${
                defaultValue !== null
                    ? `
                        <button
                            class="control-reset"
                            title="Reset to default"
                            onclick="resetCameraControl(
                                '${escapeJs(cameraId)}',
                                '${escapeJs(capability.id)}',
                                ${JSON.stringify(defaultValue)}
                            )"
                        >↺</button>
                    `
                    : '<span></span>'
            }
        </div>

        ${
            defaultValue !== null
                ? `
                    <div class="control-default">
                        Default:
                        ${defaultValue ? 'On' : 'Off'}
                    </div>
                `
                : ''
        }
    `;
}


function cameraReadonlyControl(
    capability,
    value
) {
    return `
        <div class="control-row readonly">
            <div class="control-name">
                ${escapeHtml(capability.name)}
            </div>

            <div class="control-readonly-value">
                ${escapeHtml(value ?? '')}
                ${escapeHtml(capability.units || '')}
            </div>
        </div>
    `;
}


function cameraProfileSelectId(cameraId) {
    return (
        'camera-profile-' +
        encodeURIComponent(cameraId)
    );
}


function cameraProfileBar(cameraId, profiles) {
    const selectId = cameraProfileSelectId(cameraId);

    let options = `
        <option value="">Select profile...</option>
    `;

    for (const profile of profiles) {
        options += `
            <option value="${escapeHtml(profile.name)}">
                ${escapeHtml(profile.name)}
            </option>
        `;
    }

    return `
        <div class="camera-profile-bar">
            <label for="${selectId}">
                Profile:
            </label>

            <select id="${selectId}">
                ${options}
            </select>

            <button onclick="loadCameraProfile(
                '${escapeJs(cameraId)}'
            )">
                Load
            </button>

            <button onclick="saveCameraProfile(
                '${escapeJs(cameraId)}'
            )">
                Save As...
            </button>

            <button onclick="deleteCameraProfile(
                '${escapeJs(cameraId)}'
            )">
                Delete
            </button>
        </div>
    `;
}


function cameraOrientationSection(cameraId, orientation) {
    const prefix = 'orientation-' + encodeURIComponent(cameraId);

    return `
        <div class="settings-section camera-orientation">
            <div class="settings-section-title">
                Display Orientation
            </div>

            <div class="camera-info">
                Applied before alignment and live compositing. Changing it
                clears active alignment transforms.
            </div>

            <div class="orientation-controls">
                <label>
                    Rotate
                    <select id="${prefix}-rotation">
                        <option value="0" ${orientation.rotation_deg === 0 ? 'selected' : ''}>0°</option>
                        <option value="90" ${orientation.rotation_deg === 90 ? 'selected' : ''}>90° clockwise</option>
                        <option value="180" ${orientation.rotation_deg === 180 ? 'selected' : ''}>180°</option>
                        <option value="270" ${orientation.rotation_deg === 270 ? 'selected' : ''}>270° clockwise</option>
                    </select>
                </label>

                <label>
                    <input
                        id="${prefix}-flip-horizontal"
                        type="checkbox"
                        ${orientation.flip_horizontal ? 'checked' : ''}
                    >
                    Flip horizontal
                </label>

                <label>
                    <input
                        id="${prefix}-flip-vertical"
                        type="checkbox"
                        ${orientation.flip_vertical ? 'checked' : ''}
                    >
                    Flip vertical
                </label>

                <button onclick="setCameraOrientation(
                    '${escapeJs(cameraId)}'
                )">
                    Apply orientation
                </button>
            </div>
        </div>
    `;
}


function previewResolutionSection(cameraId, capability) {
    if (!capability) {
        return '';
    }

    const selectId =
        'preview-resolution-' + encodeURIComponent(cameraId);
    const value = (
        capability.current_value ?? capability.value ?? ''
    );
    const choices = capability.choices || [];
    const options = choices.map(choice => `
        <option
            value="${escapeHtml(choice)}"
            ${choice === value ? 'selected' : ''}
        >
            ${escapeHtml(choice)}
        </option>
    `).join('');

    return `
        <div class="settings-section preview-resolution">
            <div class="settings-section-title">
                Live Preview Resolution
            </div>

            <div class="camera-info">
                Restarts only this camera stream. It clears active alignment
                because frame geometry changes.
            </div>

            <div class="orientation-controls">
                <select id="${selectId}">
                    ${options}
                </select>

                <button onclick="setPreviewResolution(
                    '${escapeJs(cameraId)}'
                )">
                    Apply resolution
                </button>
            </div>
        </div>
    `;
}


function selectedCameraProfile(cameraId) {
    const select = document.getElementById(
        cameraProfileSelectId(cameraId)
    );

    if (!select) {
        return '';
    }

    return select.value;
}


async function saveCameraProfile(cameraId) {
    const name = window.prompt(
        'Camera profile name:'
    );

    if (!name || !name.trim()) {
        return;
    }

    try {
        const result = await api(
            '/api/camera-profiles',
            {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    name: name.trim(),
                    camera_id: cameraId
                })
            }
        );

        await loadCameraSettings(cameraId);

        const select = document.getElementById(
            cameraProfileSelectId(cameraId)
        );

        if (select && result.profile) {
            select.value = result.profile.name;
        }

    } catch (error) {
        window.alert(
            'Unable to save camera profile: ' +
            error.message
        );
    }
}


async function loadCameraProfile(cameraId) {
    const profileName = selectedCameraProfile(cameraId);

    if (!profileName) {
        window.alert('Select a profile first.');
        return;
    }

    try {
        const result = await api(
            '/api/camera-profiles/' +
            encodeURIComponent(profileName) +
            '/load',
            {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    camera_id: cameraId
                })
            }
        );

        await loadCameraSettings(cameraId);

        const select = document.getElementById(
            cameraProfileSelectId(cameraId)
        );

        if (select) {
            select.value = profileName;
        }

        if (
            result.errors &&
            result.errors.length > 0
        ) {
            window.alert(
                'Profile loaded with ' +
                result.errors.length +
                ' control error(s).'
            );
        }

    } catch (error) {
        window.alert(
            'Unable to load camera profile: ' +
            error.message
        );
    }
}


async function deleteCameraProfile(cameraId) {
    const profileName = selectedCameraProfile(cameraId);

    if (!profileName) {
        window.alert('Select a profile first.');
        return;
    }

    if (!window.confirm(
        'Delete camera profile "' +
        profileName +
        '"?'
    )) {
        return;
    }

    try {
        await api(
            '/api/camera-profiles/' +
            encodeURIComponent(profileName),
            {
                method: 'DELETE'
            }
        );

        await loadCameraSettings(cameraId);

    } catch (error) {
        window.alert(
            'Unable to delete camera profile: ' +
            error.message
        );
    }
}


async function loadCameraSettings(cameraId) {
    const panel = document.getElementById(
        'settings-' + encodeURIComponent(cameraId)
    );

    if (!panel || !openCameraSettings.has(cameraId)) {
        return;
    }

    try {
        const [data, orientationData] = await Promise.all([
            api(
                '/api/cameras/' +
                encodeURIComponent(cameraId) +
                '/capabilities'
            ),
            api(
                '/api/cameras/' +
                encodeURIComponent(cameraId) +
                '/orientation'
            )
        ]);

        if (!openCameraSettings.has(cameraId)) {
            return;
        }

        const currentPanel = document.getElementById(
            'settings-' + encodeURIComponent(cameraId)
        );

        if (!currentPanel) {
            return;
        }

        const supported = data.capabilities.filter(
            capability =>
                capability.type !== 'choice' &&
                capability.id !== 'pixel_format'
        );
        const previewResolution = data.capabilities.find(
            capability => capability.id === 'preview_resolution'
        );

        const sections = {
            Image: [],
            Sensor: [],
            Orientation: []
        };

        for (const capability of supported) {
            const section = cameraControlSection(capability);

            if (!sections[section]) {
                sections[section] = [];
            }

            sections[section].push(capability);
        }

        let profiles = [];

        try {
            const profileData = await api(
                '/api/camera-profiles'
            );

            profiles = profileData.profiles || [];

        } catch (error) {
            console.error(
                'Unable to load camera profiles:',
                error
            );
        }

        let html = cameraProfileBar(
            cameraId,
            profiles
        );

        html += cameraOrientationSection(
            cameraId,
            orientationData.orientation
        );

        html += previewResolutionSection(
            cameraId,
            previewResolution
        );

        if (supported.length === 0) {
            html +=
                '<div class="settings-message">' +
                'No hardware camera controls reported.' +
                '</div>';
        }

        for (const [sectionName, capabilities] of
            Object.entries(sections)) {

            if (capabilities.length === 0) {
                continue;
            }

            html += `
                <div class="settings-section">
                    <div class="settings-section-title">
                        ${escapeHtml(sectionName)}
                    </div>
            `;

            for (const capability of capabilities) {
                const value =
                    capability.current_value !== null &&
                    capability.current_value !== undefined
                        ? capability.current_value
                        : capability.value;

                if (!capability.writable) {
                    html += cameraReadonlyControl(
                        capability,
                        value
                    );
                    continue;
                }

                if (capability.type === 'boolean') {
                    html += cameraBooleanControl(
                        cameraId,
                        capability,
                        value
                    );
                    continue;
                }

                html += cameraNumericControl(
                    cameraId,
                    capability,
                    value
                );
            }

            html += '</div>';
        }

        currentPanel.innerHTML = html;

    } catch (error) {
        panel.innerHTML =
            '<div class="settings-message">' +
            'Unable to read camera settings: ' +
            escapeHtml(error.message) +
            '</div>';
    }
}


async function setCameraOrientation(cameraId) {
    const prefix = 'orientation-' + encodeURIComponent(cameraId);
    const rotation = document.getElementById(prefix + '-rotation');
    const horizontal = document.getElementById(
        prefix + '-flip-horizontal'
    );
    const vertical = document.getElementById(prefix + '-flip-vertical');

    if (!rotation || !horizontal || !vertical) {
        return;
    }

    try {
        await api(
            '/api/cameras/' +
            encodeURIComponent(cameraId) +
            '/orientation',
            {
                method: 'PATCH',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    rotation_deg: Number(rotation.value),
                    flip_horizontal: horizontal.checked,
                    flip_vertical: vertical.checked
                })
            }
        );

        showStatus('Orientation saved; active alignment reset');
        await loadCameraSettings(cameraId);

    } catch (error) {
        console.error(error);
        showStatus('Unable to update camera orientation');
    }
}


async function setPreviewResolution(cameraId) {
    const select = document.getElementById(
        'preview-resolution-' + encodeURIComponent(cameraId)
    );

    if (!select || !select.value) {
        return;
    }

    if (!window.confirm(
        `Restart this camera using ${select.value} live preview resolution? ` +
        'Current alignment will be cleared.'
    )) {
        return;
    }

    try {
        await api(
            '/api/cameras/' +
            encodeURIComponent(cameraId) +
            '/preview-resolution',
            {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    resolution: select.value
                })
            }
        );

        showStatus(
            'Preview resolution applied; stream restarting and alignment reset'
        );
        await refresh();

    } catch (error) {
        console.error(error);
        showStatus('Unable to change live preview resolution');
    }
}


function cameraSliderChanged(
    cameraId,
    controlId,
    sliderValue,
    minimum,
    maximum,
    useLog
) {
    const spec = {
        minimum: Number(minimum),
        maximum: Number(maximum),
        useLog: Boolean(useLog)
    };

    const value = sliderToValue(
        sliderValue,
        spec
    );

    const input = document.getElementById(
        'control-' +
        encodeURIComponent(cameraId) +
        '-' +
        controlId
    );

    if (input) {
        const magnitude = Math.abs(value);

        if (magnitude >= 100) {
            input.value = Math.round(value);
        } else if (magnitude >= 10) {
            input.value = value.toFixed(2);
        } else {
            input.value = value.toFixed(3);
        }
    }

    scheduleCameraControl(
        cameraId,
        controlId,
        Number(input ? input.value : value)
    );
}


function cameraNumberChanged(
    cameraId,
    controlId
) {
    const input = document.getElementById(
        'control-' +
        encodeURIComponent(cameraId) +
        '-' +
        controlId
    );

    if (!input) {
        return;
    }

    const value = Number(input.value);

    if (!Number.isFinite(value)) {
        return;
    }

    scheduleCameraControl(
        cameraId,
        controlId,
        value,
        0
    );
}


function cameraNumberKeyDown(
    event,
    cameraId,
    controlId
) {
    if (event.key !== 'Enter') {
        return;
    }

    event.preventDefault();

    cameraNumberChanged(
        cameraId,
        controlId
    );

    event.target.blur();
}


function cameraBooleanChanged(
    cameraId,
    controlId,
    value
) {
    scheduleCameraControl(
        cameraId,
        controlId,
        Boolean(value),
        0
    );
}


async function setCameraControl(cameraId, controlId) {
    const input = document.getElementById(
        'control-' +
        encodeURIComponent(cameraId) +
        '-' +
        controlId
    );

    if (!input) {
        return;
    }

    try {
        await api(
            '/api/cameras/' +
            encodeURIComponent(cameraId) +
            '/controls',
            {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    control_id: controlId,
                    value:
                        input.type === 'checkbox'
                            ? input.checked
                            : Number(input.value)
                })
            }
        );

        showStatus('Camera setting updated');
        await loadCameraSettings(cameraId);

    } catch (error) {
        console.error(error);
        showStatus('Unable to update camera setting');
    }
}


async function resetCameraControl(
    cameraId,
    controlId,
    defaultValue
) {
    const input = document.getElementById(
        'control-' +
        encodeURIComponent(cameraId) +
        '-' +
        controlId
    );

    if (input) {
        if (input.type === 'checkbox') {
            input.checked = Boolean(defaultValue);
        } else {
            input.value = defaultValue;
        }
    }

    try {
        await setCameraControlValue(
            cameraId,
            controlId,
            defaultValue
        );

        showStatus('Camera setting reset');

        await loadCameraSettings(cameraId);

    } catch (error) {
        console.error(error);
        showStatus('Unable to reset camera setting');
    }
}


function renderAvailableCameras() {

    const select = document.getElementById('availableCamera');
    const button = document.getElementById('addLayerButton');

    // Preserve the user's selection when the periodic refresh rebuilds
    // the list of available cameras.
    const selectedCameraId = select.value;

    const used = new Set(
        viewState.layers.map(layer => layer.camera_id)
    );

    const available = cameras.filter(
        camera => !used.has(camera.id)
    );

    select.innerHTML = '';

    if (available.length === 0) {
        const option = document.createElement('option');
        option.textContent = 'No unused cameras available';
        option.value = '';
        select.appendChild(option);
        select.disabled = true;
        button.disabled = true;
        return;
    }

    select.disabled = false;
    button.disabled = false;

    for (const camera of available) {
        const option = document.createElement('option');
        option.value = camera.id;
        option.textContent = cameraLabel(camera);
        select.appendChild(option);
    }

    if (available.some(camera => camera.id === selectedCameraId)) {
        select.value = selectedCameraId;
    }
}


function escapeJs(value) {
    return value
        .replace(/\\/g, '\\\\')
        .replace(/'/g, "\\'");
}


function escapeHtml(value) {
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}


async function addLayer() {
    const select = document.getElementById('availableCamera');
    const cameraId = select.value;

    if (!cameraId) {
        return;
    }

    await api('/api/layers', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            camera_id: cameraId,
            opacity: 0.5
        })
    });

    await refresh();
    showStatus('Camera layer added');
}


async function removeLayer(cameraId) {
    await api(
        '/api/layers/' + encodeURIComponent(cameraId),
        {method: 'DELETE'}
    );

    await refresh();
    showStatus('Camera layer removed');
}


async function setOpacity(cameraId, value) {
    viewState = await api(
        '/api/layers/' + encodeURIComponent(cameraId),
        {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                opacity: Number(value)
            })
        }
    );

    showStatus('Opacity updated');
}


async function setEnabled(cameraId, enabled) {
    viewState = await api(
        '/api/layers/' + encodeURIComponent(cameraId),
        {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                enabled: enabled
            })
        }
    );

    showStatus(enabled ? 'Camera layer enabled' : 'Camera layer disabled');
}


function showStatus(message) {
    const status = document.getElementById('status');
    status.textContent = message;

    setTimeout(() => {
        status.textContent = '';
    }, 1500);
}


refresh().catch(error => {
    console.error(error);
    alert(error);
});

// Keep diagnostics fresh without changing layer controls/state.
setInterval(() => {
    refresh().catch(console.error);
}, 2000);
