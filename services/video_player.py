import html
import json
import math
import re

import streamlit.components.v1 as components


DEFAULT_FRAME_RATE = 30.0


def _clean_text(value):
    if value is None:
        return ""
    return str(value).strip()


def _safe_dom_id(value):
    text = re.sub(r"[^A-Za-z0-9_-]+", "-", _clean_text(value))
    text = text.strip("-")
    return text or "volleyreview-video"


def _normalized_angle_name(value):
    return _clean_text(value).upper()


def _is_program(angle):
    name = _normalized_angle_name(angle.get("angle_name"))
    return name in {
        "PGM",
        "PROGRAM",
        "PROGRAM FEED",
        "PROGRAM OUTPUT",
    }


def _is_replay(angle):
    name = _normalized_angle_name(angle.get("angle_name"))
    return name in {
        "REPLAY OUTPUT",
        "RO",
        "REPLAY",
        "REPLAY OUT",
    }


def _workspace_height(angle_count):
    # One main player plus a wrapping camera-button strip. The estimate keeps
    # the component from developing an internal scrollbar on normal desktop
    # layouts even when a play has many camera angles.
    rows = max(1, math.ceil(max(angle_count, 1) / 6))
    return min(980, 650 + (rows * 58))


def render_keyboard_video_workspace(
    angles,
    *,
    key,
    frame_rate=DEFAULT_FRAME_RATE,
):
    """
    Render one main video player with keyboard review controls and camera
    selection buttons for every angle attached to the selected play.

    Shortcuts:
      Z         = back 5 seconds
      X         = back 1 frame
      C         = play / pause
      V         = forward 1 frame
      B         = forward 5 seconds
      D / F     = previous / next camera
      P         = program feed
      R         = replay output
      1 / 2 / 3 = 0.5x / 1.0x / 2.0x
      \\         = enter / exit fullscreen workspace

    Camera changes preserve the current time, play/pause state, and playback
    speed. Fullscreen is applied to the entire workspace—not the native video
    element—so camera buttons and keyboard listeners remain available.

    Hovering a camera button lazily loads a muted preview at approximately the
    main player's current timestamp. Clicking the button makes that angle the
    active source in the main player.
    """
    usable = []

    for index, angle in enumerate(angles or []):
        if not isinstance(angle, dict):
            continue

        url = _clean_text(
            angle.get("video_url")
            or angle.get("url")
        )
        if not url:
            continue

        name = (
            _clean_text(angle.get("angle_name"))
            or f"Video {index + 1}"
        )

        usable.append(
            {
                "id": _clean_text(angle.get("id")) or str(index + 1),
                "name": name,
                "url": url,
                "sas_error": _clean_text(angle.get("sas_error")),
                "is_program": _is_program(angle),
                "is_replay": _is_replay(angle),
            }
        )

    if not usable:
        return

    try:
        fps = float(frame_rate)
    except (TypeError, ValueError):
        fps = DEFAULT_FRAME_RATE

    if fps <= 0:
        fps = DEFAULT_FRAME_RATE

    dom_id = _safe_dom_id(key)
    angle_json = json.dumps(
        usable,
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")

    frame_step = 1.0 / fps
    height = _workspace_height(len(usable))
    safe_title = html.escape(dom_id)

    markup = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
    :root {{
        color-scheme: dark;
        --bg: #071425;
        --panel: #0b1b31;
        --card: #10253f;
        --card2: #132b49;
        --blue: #0a67c8;
        --sky: #68d8ff;
        --mint: #8cf0cb;
        --lav: #b9a7ff;
        --text: #f5f9ff;
        --muted: #9cb0c8;
        --border: rgba(143, 200, 255, 0.20);
        --active: rgba(104, 216, 255, 0.95);
    }}

    * {{ box-sizing: border-box; }}

    html, body {{
        margin: 0;
        padding: 0;
        background: transparent;
        color: var(--text);
        font-family: Inter, ui-sans-serif, system-ui, -apple-system,
                     BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}

    #vr-{safe_title} {{
        width: 100%;
        background:
            radial-gradient(circle at 10% 0%, rgba(104,216,255,.07), transparent 30%),
            linear-gradient(145deg, #071425 0%, #08182b 55%, #06101e 100%);
        border: 1px solid var(--border);
        border-radius: 16px;
        padding: 14px;
        outline: none;
        position: relative;
    }}

    #vr-{safe_title}:fullscreen {{
        width: 100vw;
        height: 100vh;
        border: 0;
        border-radius: 0;
        padding: 18px 22px;
        background: #02060c;
        display: flex;
        flex-direction: column;
        overflow: hidden;
    }}

    .topbar {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        flex-wrap: wrap;
        margin-bottom: 10px;
    }}

    .active-summary {{
        min-width: 0;
        display: flex;
        align-items: center;
        gap: 9px;
        font-weight: 800;
        letter-spacing: .01em;
    }}

    .active-dot {{
        width: 10px;
        height: 10px;
        border-radius: 999px;
        background: var(--mint);
        box-shadow: 0 0 0 4px rgba(140,240,203,.12),
                    0 0 16px rgba(140,240,203,.55);
        flex: 0 0 auto;
    }}

    .active-angle {{
        color: var(--sky);
        max-width: 360px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }}

    .play-status {{
        color: var(--muted);
        font-size: 13px;
        font-weight: 650;
        white-space: nowrap;
    }}

    .focus-note {{
        color: var(--muted);
        font-size: 12px;
        margin-bottom: 10px;
    }}

    .main-stage {{
        position: relative;
        width: 100%;
        background: #000;
        border: 2px solid rgba(104,216,255,.34);
        border-radius: 14px;
        overflow: hidden;
        box-shadow: 0 14px 40px rgba(0,0,0,.28);
    }}

    #vr-{safe_title}:fullscreen .main-stage {{
        flex: 1 1 auto;
        min-height: 0;
        display: flex;
        align-items: center;
        justify-content: center;
        border-color: rgba(104,216,255,.60);
    }}

    .main-stage video {{
        width: 100%;
        display: block;
        aspect-ratio: 16 / 9;
        background: #000;
        max-height: 68vh;
    }}

    #vr-{safe_title}:fullscreen .main-stage video {{
        width: 100%;
        height: 100%;
        max-height: none;
        object-fit: contain;
        aspect-ratio: auto;
    }}

    .stage-badge {{
        position: absolute;
        top: 12px;
        left: 12px;
        z-index: 5;
        display: inline-flex;
        align-items: center;
        gap: 7px;
        padding: 7px 10px;
        border-radius: 999px;
        background: rgba(7,20,37,.86);
        border: 1px solid rgba(104,216,255,.48);
        backdrop-filter: blur(8px);
        font-size: 12px;
        font-weight: 800;
        box-shadow: 0 6px 20px rgba(0,0,0,.25);
        pointer-events: none;
    }}

    .stage-badge span {{ color: var(--sky); }}

    .camera-title {{
        margin: 13px 0 8px;
        display: flex;
        align-items: baseline;
        justify-content: space-between;
        gap: 12px;
    }}

    .camera-title strong {{
        font-size: 12px;
        letter-spacing: .08em;
        text-transform: uppercase;
    }}

    .camera-title span {{
        color: var(--muted);
        font-size: 11px;
    }}

    .camera-strip {{
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        align-items: center;
        position: relative;
    }}

    #vr-{safe_title}:fullscreen .camera-title {{
        margin-top: 10px;
    }}

    #vr-{safe_title}:fullscreen .camera-strip {{
        flex: 0 0 auto;
    }}

    .camera-wrap {{
        position: relative;
    }}

    .camera-btn {{
        appearance: none;
        border: 1px solid rgba(143,200,255,.22);
        border-radius: 10px;
        padding: 9px 12px;
        min-width: 94px;
        max-width: 190px;
        background: linear-gradient(180deg, #132b49 0%, #10253f 100%);
        color: var(--text);
        font: inherit;
        font-size: 12px;
        font-weight: 750;
        cursor: pointer;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        transition: border-color .12s ease, transform .12s ease,
                    box-shadow .12s ease, background .12s ease;
    }}

    .camera-btn:hover {{
        transform: translateY(-1px);
        border-color: rgba(104,216,255,.72);
    }}

    .camera-btn.active {{
        color: #fff;
        border-color: var(--active);
        background: linear-gradient(180deg, #0b579c 0%, #0a3f75 100%);
        box-shadow: 0 0 0 2px rgba(104,216,255,.12),
                    0 7px 22px rgba(10,103,200,.28);
    }}

    .camera-btn .mini {{
        display: inline-block;
        margin-left: 6px;
        color: var(--mint);
        font-size: 9px;
        vertical-align: 1px;
    }}

    .preview {{
        position: absolute;
        left: 50%;
        bottom: calc(100% + 10px);
        transform: translateX(-50%) translateY(4px);
        width: 250px;
        background: #06111f;
        border: 1px solid rgba(104,216,255,.44);
        border-radius: 12px;
        padding: 8px;
        box-shadow: 0 16px 45px rgba(0,0,0,.48);
        opacity: 0;
        visibility: hidden;
        pointer-events: none;
        transition: opacity .12s ease, transform .12s ease,
                    visibility .12s ease;
        z-index: 30;
    }}

    .camera-wrap:hover .preview,
    .camera-wrap:focus-within .preview {{
        opacity: 1;
        visibility: visible;
        transform: translateX(-50%) translateY(0);
    }}

    .preview video {{
        width: 100%;
        aspect-ratio: 16 / 9;
        object-fit: contain;
        display: block;
        background: #000;
        border-radius: 7px;
    }}

    .preview-label {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
        padding-top: 6px;
        color: var(--muted);
        font-size: 10px;
    }}

    .preview-label strong {{
        color: var(--text);
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }}

    .shortcut-bar {{
        display: flex;
        flex-wrap: wrap;
        gap: 7px 12px;
        align-items: center;
        margin-top: 13px;
        padding: 10px 11px;
        border-radius: 11px;
        background: rgba(11,27,49,.78);
        border: 1px solid rgba(143,200,255,.14);
        color: var(--muted);
        font-size: 11px;
    }}

    #vr-{safe_title}:fullscreen .shortcut-bar {{
        margin-top: 9px;
        padding: 7px 10px;
    }}

    .shortcut {{
        display: inline-flex;
        align-items: center;
        gap: 5px;
        white-space: nowrap;
    }}

    kbd {{
        min-width: 22px;
        padding: 2px 6px;
        text-align: center;
        color: var(--text);
        background: #071425;
        border: 1px solid rgba(143,200,255,.28);
        border-bottom-color: rgba(143,200,255,.42);
        border-radius: 5px;
        font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
        font-size: 10px;
        box-shadow: inset 0 -1px 0 rgba(255,255,255,.05);
    }}

    .warning {{
        margin-top: 8px;
        padding: 8px 10px;
        border: 1px solid rgba(255,199,92,.35);
        border-radius: 9px;
        color: #ffd58a;
        background: rgba(114,73,10,.20);
        font-size: 11px;
    }}

    @media (max-width: 760px) {{
        .camera-btn {{ min-width: 78px; max-width: 145px; }}
        .preview {{ width: 210px; }}
        .main-stage video {{ max-height: none; }}
    }}
</style>
</head>
<body>
<div id="vr-{safe_title}" tabindex="0" aria-label="VolleyReview video controls">
    <div class="topbar">
        <div class="active-summary">
            <span class="active-dot"></span>
            <span>ACTIVE CAMERA:</span>
            <span class="active-angle" id="active-angle">—</span>
        </div>
        <div class="play-status" id="play-status">Paused • 1.0× • 0:00.000</div>
    </div>

    <div class="focus-note" id="focus-note">
        Shortcuts ready. Camera buttons switch the main player while preserving time and speed.
    </div>

    <div class="main-stage" id="main-stage">
        <div class="stage-badge">● ACTIVE &nbsp;<span id="stage-angle">—</span></div>
        <video id="main-video" controls preload="metadata" playsinline></video>
    </div>

    <div class="camera-title">
        <strong>Camera Angles</strong>
        <span>Hover for a preview • click to load in the main player</span>
    </div>
    <div class="camera-strip" id="camera-strip"></div>
    <div id="url-warning"></div>

    <div class="shortcut-bar">
        <span class="shortcut"><kbd>Z</kbd>-5 sec</span>
        <span class="shortcut"><kbd>X</kbd>-1 frame</span>
        <span class="shortcut"><kbd>C</kbd>play / pause</span>
        <span class="shortcut"><kbd>V</kbd>+1 frame</span>
        <span class="shortcut"><kbd>B</kbd>+5 sec</span>
        <span class="shortcut"><kbd>D</kbd>previous cam</span>
        <span class="shortcut"><kbd>F</kbd>next cam</span>
        <span class="shortcut"><kbd>P</kbd>program</span>
        <span class="shortcut"><kbd>R</kbd>replay</span>
        <span class="shortcut"><kbd>1</kbd>0.5×</span>
        <span class="shortcut"><kbd>2</kbd>1×</span>
        <span class="shortcut"><kbd>3</kbd>2×</span>
        <span class="shortcut"><kbd>\\</kbd>fullscreen</span>
    </div>
</div>

<script>
(() => {{
    const root = document.getElementById("vr-{safe_title}");
    const mainVideo = document.getElementById("main-video");
    const cameraStrip = document.getElementById("camera-strip");
    const activeAngleEl = document.getElementById("active-angle");
    const stageAngleEl = document.getElementById("stage-angle");
    const statusEl = document.getElementById("play-status");
    const focusNoteEl = document.getElementById("focus-note");
    const warningEl = document.getElementById("url-warning");
    const angles = {angle_json};
    const fallbackFrameStep = {frame_step:.12f};

    let activeIndex = -1;
    let measuredFrameStep = fallbackFrameStep;
    let lastFrameMediaTime = null;
    let pendingState = null;
    const previews = new Map();

    function formatTime(value) {{
        const seconds = Number.isFinite(value) ? Math.max(value, 0) : 0;
        const minutes = Math.floor(seconds / 60);
        const remainder = seconds - (minutes * 60);
        return `${{minutes}}:${{remainder.toFixed(3).padStart(6, "0")}}`;
    }}

    function statusText() {{
        const state = mainVideo.paused ? "Paused" : "Playing";
        const rate = Number.isFinite(mainVideo.playbackRate) ? mainVideo.playbackRate : 1;
        return `${{state}} • ${{rate.toFixed(1)}}× • ${{formatTime(mainVideo.currentTime)}}`;
    }}

    function updateStatus() {{
        statusEl.textContent = statusText();
    }}

    function snapshotState() {{
        return {{
            time: Number.isFinite(mainVideo.currentTime) ? mainVideo.currentTime : 0,
            paused: mainVideo.paused,
            rate: Number.isFinite(mainVideo.playbackRate) ? mainVideo.playbackRate : 1,
        }};
    }}

    function setPreviewTime(preview) {{
        if (!preview || !Number.isFinite(mainVideo.currentTime)) return;
        const desired = Math.max(mainVideo.currentTime, 0);
        const apply = () => {{
            if (!Number.isFinite(preview.duration) || preview.duration <= 0) return;
            preview.currentTime = Math.min(desired, Math.max(preview.duration - 0.04, 0));
        }};
        if (preview.readyState >= 1) apply();
        else preview.addEventListener("loadedmetadata", apply, {{ once: true }});
    }}

    function refreshButtons() {{
        cameraStrip.querySelectorAll(".camera-btn").forEach((button, index) => {{
            button.classList.toggle("active", index === activeIndex);
            button.setAttribute("aria-pressed", index === activeIndex ? "true" : "false");
        }});
    }}

    function loadAngle(index, preserveState=true) {{
        if (!angles.length) return;
        const next = ((index % angles.length) + angles.length) % angles.length;
        if (next === activeIndex && mainVideo.src) {{
            root.focus({{ preventScroll: true }});
            return;
        }}

        const state = preserveState ? snapshotState() : {{ time: 0, paused: true, rate: 1 }};
        activeIndex = next;
        pendingState = state;

        const angle = angles[activeIndex];
        activeAngleEl.textContent = angle.name;
        stageAngleEl.textContent = angle.name;
        refreshButtons();

        warningEl.innerHTML = "";
        if (angle.sas_error) {{
            const warning = document.createElement("div");
            warning.className = "warning";
            warning.textContent = `Signed URL refresh warning: ${{angle.sas_error}}`;
            warningEl.appendChild(warning);
        }}

        measuredFrameStep = fallbackFrameStep;
        lastFrameMediaTime = null;

        mainVideo.pause();
        mainVideo.src = angle.url;
        mainVideo.load();
        root.focus({{ preventScroll: true }});
        updateStatus();
    }}

    mainVideo.addEventListener("loadedmetadata", () => {{
        if (!pendingState) return;
        const state = pendingState;
        pendingState = null;

        mainVideo.playbackRate = state.rate;
        if (Number.isFinite(mainVideo.duration) && mainVideo.duration > 0) {{
            mainVideo.currentTime = Math.min(
                Math.max(state.time, 0),
                Math.max(mainVideo.duration - 0.04, 0),
            );
        }}

        if (!state.paused) {{
            const promise = mainVideo.play();
            if (promise && typeof promise.catch === "function") promise.catch(() => {{}});
        }}
        updateStatus();
    }});

    if (typeof mainVideo.requestVideoFrameCallback === "function") {{
        const observeFrame = (_now, metadata) => {{
            const mediaTime = metadata && Number.isFinite(metadata.mediaTime)
                ? metadata.mediaTime
                : null;

            if (mediaTime !== null && lastFrameMediaTime !== null) {{
                const delta = mediaTime - lastFrameMediaTime;
                if (delta >= 0.005 && delta <= 0.100) measuredFrameStep = delta;
            }}
            if (mediaTime !== null) lastFrameMediaTime = mediaTime;
            mainVideo.requestVideoFrameCallback(observeFrame);
        }};
        mainVideo.requestVideoFrameCallback(observeFrame);
    }}

    function seekBy(seconds) {{
        if (!mainVideo.src) return;
        const maxTime = Number.isFinite(mainVideo.duration)
            ? Math.max(mainVideo.duration - 0.001, 0)
            : Infinity;
        mainVideo.currentTime = Math.min(
            Math.max((mainVideo.currentTime || 0) + seconds, 0),
            maxTime,
        );
        updateStatus();
    }}

    function stepFrame(direction) {{
        mainVideo.pause();
        const step = Number.isFinite(measuredFrameStep) && measuredFrameStep > 0
            ? measuredFrameStep
            : fallbackFrameStep;
        seekBy(direction * step);
    }}

    function togglePlay() {{
        if (!mainVideo.src) return;
        if (mainVideo.paused) {{
            const promise = mainVideo.play();
            if (promise && typeof promise.catch === "function") promise.catch(() => {{}});
        }} else {{
            mainVideo.pause();
        }}
        updateStatus();
    }}

    function setRate(rate) {{
        mainVideo.playbackRate = rate;
        updateStatus();
    }}

    function selectSpecial(kind) {{
        const index = angles.findIndex(angle => Boolean(angle[kind]));
        if (index >= 0) loadAngle(index, true);
    }}

    async function toggleFullscreen() {{
        try {{
            if (document.fullscreenElement) {{
                await document.exitFullscreen();
            }} else if (root.requestFullscreen) {{
                await root.requestFullscreen();
                root.focus({{ preventScroll: true }});
            }}
        }} catch (_) {{}}
    }}

    function buildCameraButton(angle, index) {{
        const wrap = document.createElement("div");
        wrap.className = "camera-wrap";

        const button = document.createElement("button");
        button.type = "button";
        button.className = "camera-btn";
        button.title = angle.name;
        button.setAttribute("aria-label", `Load camera ${{angle.name}}`);
        button.textContent = angle.name;

        if (angle.is_program || angle.is_replay) {{
            const mini = document.createElement("span");
            mini.className = "mini";
            mini.textContent = angle.is_program ? "PGM" : "R";
            button.appendChild(mini);
        }}

        const previewBox = document.createElement("div");
        previewBox.className = "preview";

        const previewVideo = document.createElement("video");
        previewVideo.muted = true;
        previewVideo.playsInline = true;
        previewVideo.preload = "metadata";

        const previewLabel = document.createElement("div");
        previewLabel.className = "preview-label";
        const previewName = document.createElement("strong");
        previewName.textContent = angle.name;
        const previewHint = document.createElement("span");
        previewHint.textContent = "preview";
        previewLabel.appendChild(previewName);
        previewLabel.appendChild(previewHint);

        previewBox.appendChild(previewVideo);
        previewBox.appendChild(previewLabel);
        wrap.appendChild(button);
        wrap.appendChild(previewBox);
        previews.set(index, previewVideo);

        const primePreview = () => {{
            if (!previewVideo.src) {{
                previewVideo.src = angle.url;
                previewVideo.load();
            }}
            setPreviewTime(previewVideo);
        }};

        wrap.addEventListener("mouseenter", primePreview);
        button.addEventListener("focus", primePreview);
        button.addEventListener("click", () => loadAngle(index, true));

        return wrap;
    }}

    angles.forEach((angle, index) => {{
        cameraStrip.appendChild(buildCameraButton(angle, index));
    }});

    let initialIndex = angles.findIndex(angle => angle.is_program);
    if (initialIndex < 0) initialIndex = angles.findIndex(angle => angle.is_replay);
    if (initialIndex < 0) initialIndex = 0;
    loadAngle(initialIndex, false);

    ["play", "pause", "ratechange", "timeupdate", "seeked"].forEach(eventName => {{
        mainVideo.addEventListener(eventName, updateStatus);
    }});

    root.addEventListener("pointerdown", () => {{
        root.focus({{ preventScroll: true }});
        focusNoteEl.textContent = "Shortcuts active • hover a camera for preview or click it to switch.";
    }});

    document.addEventListener("fullscreenchange", () => {{
        if (document.fullscreenElement === root) {{
            root.focus({{ preventScroll: true }});
            focusNoteEl.textContent = "Fullscreen shortcuts active • \\ exits fullscreen.";
        }} else {{
            focusNoteEl.textContent = "Shortcuts ready • \\ enters fullscreen.";
        }}
    }});

    document.addEventListener("keydown", event => {{
        const target = event.target;
        const tag = target && target.tagName ? target.tagName.toLowerCase() : "";
        const typing = tag === "input" || tag === "textarea" || tag === "select" ||
                       (target && target.isContentEditable);
        if (typing) return;

        const lower = (event.key || "").toLowerCase();
        const isFullscreenKey = event.key === "\\\\" || event.code === "Backslash";
        const mapped = new Set(["z", "x", "c", "v", "b", "d", "f", "p", "r", "1", "2", "3"]);
        if (!isFullscreenKey && !mapped.has(lower)) return;

        event.preventDefault();
        event.stopPropagation();

        if (event.repeat && ["c", "d", "f", "p", "r", "1", "2", "3"].includes(lower)) return;

        switch (lower) {{
            case "z": seekBy(-5); break;
            case "x": stepFrame(-1); break;
            case "c": togglePlay(); break;
            case "v": stepFrame(1); break;
            case "b": seekBy(5); break;
            case "d": loadAngle(activeIndex - 1, true); break;
            case "f": loadAngle(activeIndex + 1, true); break;
            case "p": selectSpecial("is_program"); break;
            case "r": selectSpecial("is_replay"); break;
            case "1": setRate(0.5); break;
            case "2": setRate(1.0); break;
            case "3": setRate(2.0); break;
            default:
                if (isFullscreenKey) toggleFullscreen();
        }}
    }}, true);

    updateStatus();
}})();
</script>
</body>
</html>
"""

    components.html(
        markup,
        height=height,
        scrolling=False,
    )
