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


def _workspace_height(angles):
    """Estimate iframe height for the current desktop-oriented grid."""
    primary_count = sum(
        1
        for angle in angles
        if (
            bool(angle.get("is_program"))
            or bool(angle.get("is_replay"))
            or _is_program(angle)
            or _is_replay(angle)
        )
    )
    primary_count = min(primary_count, 2)
    secondary_count = max(len(angles) - primary_count, 0)

    primary_rows = 1 if primary_count else 0
    secondary_rows = math.ceil(secondary_count / 3) if secondary_count else 0

    # Toolbar + shortcut legend + primary grid + secondary grid.
    return int(
        185
        + (primary_rows * 455)
        + (secondary_rows * 315)
        + (70 if secondary_rows else 0)
    )


def render_keyboard_video_workspace(
    angles,
    *,
    key,
    frame_rate=DEFAULT_FRAME_RATE,
):
    """
    Render all video angles for one play in a keyboard-aware review workspace.

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
      Shift+Esc = fullscreen active angle

    The component intentionally owns the keyboard focus. Clicking outside the
    video workspace (for example, into an Editor form field) removes focus and
    prevents normal typing from triggering video shortcuts.
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
    height = _workspace_height(usable)

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
        --border: rgba(143, 200, 255, .20);
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

    body {{ outline: none; }}

    .workspace {{
        width: 100%;
        outline: none;
    }}

    .control-bar {{
        position: sticky;
        top: 0;
        z-index: 20;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 16px;
        padding: 12px 14px;
        margin-bottom: 10px;
        border: 1px solid var(--border);
        border-radius: 12px;
        background: linear-gradient(135deg, #0b1b31, #0e2440);
        box-shadow: 0 10px 28px rgba(0,0,0,.18);
    }}

    .active-stack {{
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 8px;
        min-width: 0;
    }}

    .active-pill {{
        display: inline-flex;
        align-items: center;
        gap: 7px;
        padding: 6px 10px;
        border-radius: 999px;
        border: 1px solid rgba(104, 216, 255, .48);
        background: rgba(10, 103, 200, .20);
        color: var(--text);
        font-size: 12px;
        font-weight: 800;
        letter-spacing: .04em;
        text-transform: uppercase;
        white-space: nowrap;
    }}

    .dot {{
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: var(--mint);
        box-shadow: 0 0 12px rgba(140,240,203,.9);
    }}

    .state {{
        color: var(--muted);
        font-size: 12px;
        font-weight: 650;
        white-space: nowrap;
    }}

    .focus-note {{
        color: var(--muted);
        font-size: 12px;
        text-align: right;
    }}

    .shortcut-strip {{
        display: flex;
        flex-wrap: wrap;
        gap: 6px 12px;
        align-items: center;
        padding: 0 2px 12px;
        color: var(--muted);
        font-size: 11px;
        line-height: 1.3;
    }}

    .shortcut {{ white-space: nowrap; }}

    kbd {{
        display: inline-block;
        min-width: 22px;
        padding: 2px 6px;
        margin-right: 3px;
        border: 1px solid rgba(156,176,200,.34);
        border-bottom-width: 2px;
        border-radius: 5px;
        background: rgba(255,255,255,.055);
        color: var(--text);
        font: 700 10px/1.2 ui-monospace, SFMono-Regular, Menlo, monospace;
        text-align: center;
    }}

    .grid {{
        display: grid;
        gap: 14px;
        width: 100%;
    }}

    .primary-grid {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
        margin-bottom: 16px;
    }}

    .primary-grid.one {{
        grid-template-columns: minmax(0, 1fr);
    }}

    .secondary-label {{
        margin: 4px 2px 8px;
        color: var(--muted);
        font-size: 11px;
        font-weight: 800;
        letter-spacing: .10em;
        text-transform: uppercase;
    }}

    .secondary-grid {{
        grid-template-columns: repeat(3, minmax(0, 1fr));
    }}

    .video-card {{
        position: relative;
        min-width: 0;
        overflow: hidden;
        border: 1px solid var(--border);
        border-radius: 13px;
        background: linear-gradient(180deg, var(--card2), var(--card));
        box-shadow: 0 8px 24px rgba(0,0,0,.18);
        transition: border-color .12s ease,
                    box-shadow .12s ease,
                    transform .12s ease;
    }}

    .video-card:hover {{
        border-color: rgba(104, 216, 255, .42);
    }}

    .video-card.active {{
        border: 2px solid var(--sky);
        box-shadow:
            0 0 0 2px rgba(104,216,255,.12),
            0 0 28px rgba(104,216,255,.18),
            0 12px 30px rgba(0,0,0,.24);
    }}

    .card-header {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
        padding: 9px 11px;
        min-height: 40px;
    }}

    .angle-name {{
        min-width: 0;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        font-size: 13px;
        font-weight: 800;
        letter-spacing: .01em;
    }}

    .active-badge {{
        display: none;
        flex: 0 0 auto;
        padding: 4px 7px;
        border-radius: 999px;
        background: var(--sky);
        color: #04111f;
        font-size: 9px;
        font-weight: 900;
        letter-spacing: .07em;
        text-transform: uppercase;
    }}

    .video-card.active .active-badge {{ display: inline-flex; }}

    video {{
        display: block;
        width: 100%;
        aspect-ratio: 16 / 9;
        background: #000;
        object-fit: contain;
    }}

    .card-footer {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
        padding: 7px 10px 9px;
        min-height: 34px;
    }}

    .card-status {{
        color: var(--muted);
        font-size: 10px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }}

    .open-link {{
        flex: 0 0 auto;
        color: var(--sky);
        font-size: 10px;
        font-weight: 750;
        text-decoration: none;
    }}

    .error {{
        padding: 7px 10px 9px;
        color: #ffd5d5;
        background: rgba(150, 30, 30, .16);
        border-top: 1px solid rgba(255, 125, 125, .15);
        font-size: 10px;
        line-height: 1.35;
    }}

    @media (max-width: 950px) {{
        .secondary-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}

    @media (max-width: 720px) {{
        .control-bar {{ align-items: flex-start; flex-direction: column; }}
        .focus-note {{ text-align: left; }}
        .primary-grid,
        .primary-grid.one,
        .secondary-grid {{ grid-template-columns: minmax(0, 1fr); }}
    }}
</style>
</head>
<body tabindex="0">
<div id="{html.escape(dom_id)}" class="workspace" tabindex="0">
    <div class="control-bar">
        <div class="active-stack">
            <div class="active-pill">
                <span class="dot"></span>
                <span>Shortcut Control:</span>
                <span id="active-name">—</span>
            </div>
            <span id="play-state" class="state">Paused</span>
            <span id="speed-state" class="state">1.0×</span>
            <span id="time-state" class="state">0:00.000</span>
        </div>
        <div id="focus-note" class="focus-note">
            Click any video to activate shortcuts on that angle.
        </div>
    </div>

    <div class="shortcut-strip" aria-label="Video keyboard shortcuts">
        <span class="shortcut"><kbd>Z</kbd>-5 sec</span>
        <span class="shortcut"><kbd>X</kbd>-1 frame</span>
        <span class="shortcut"><kbd>C</kbd>play/pause</span>
        <span class="shortcut"><kbd>V</kbd>+1 frame</span>
        <span class="shortcut"><kbd>B</kbd>+5 sec</span>
        <span class="shortcut"><kbd>D</kbd>previous angle</span>
        <span class="shortcut"><kbd>F</kbd>next angle</span>
        <span class="shortcut"><kbd>P</kbd>program</span>
        <span class="shortcut"><kbd>R</kbd>replay output</span>
        <span class="shortcut"><kbd>1</kbd>0.5×</span>
        <span class="shortcut"><kbd>2</kbd>1×</span>
        <span class="shortcut"><kbd>3</kbd>2×</span>
        <span class="shortcut"><kbd>Shift+Esc</kbd>fullscreen</span>
    </div>

    <div id="primary-grid" class="grid primary-grid"></div>
    <div id="secondary-block" style="display:none;">
        <div class="secondary-label">Additional Angles</div>
        <div id="secondary-grid" class="grid secondary-grid"></div>
    </div>
</div>

<script>
(() => {{
    "use strict";

    const angles = {angle_json};
    const frameStep = {frame_step:.10f};
    const root = document.getElementById({json.dumps(dom_id)});
    const primaryGrid = document.getElementById("primary-grid");
    const secondaryGrid = document.getElementById("secondary-grid");
    const secondaryBlock = document.getElementById("secondary-block");
    const activeNameEl = document.getElementById("active-name");
    const playStateEl = document.getElementById("play-state");
    const speedStateEl = document.getElementById("speed-state");
    const timeStateEl = document.getElementById("time-state");
    const focusNoteEl = document.getElementById("focus-note");

    const players = [];
    let activeIndex = -1;
    let componentFocused = false;

    function formatTime(seconds) {{
        if (!Number.isFinite(seconds) || seconds < 0) seconds = 0;
        const mins = Math.floor(seconds / 60);
        const secs = seconds - (mins * 60);
        return `${{mins}}:${{secs.toFixed(3).padStart(6, "0")}}`;
    }}

    function statusText(video) {{
        if (!video) return "";
        return `${{video.paused ? "Paused" : "Playing"}} • ${{video.playbackRate.toFixed(1)}}× • ${{formatTime(video.currentTime)}}`;
    }}

    function updateTopStatus() {{
        const item = players[activeIndex];
        if (!item) return;
        const video = item.video;
        activeNameEl.textContent = item.angle.name;
        playStateEl.textContent = video.paused ? "Paused" : "Playing";
        speedStateEl.textContent = `${{video.playbackRate.toFixed(1)}}×`;
        timeStateEl.textContent = formatTime(video.currentTime);
        item.cardStatus.textContent = statusText(video);
    }}

    function pauseOthers(exceptIndex) {{
        players.forEach((item, index) => {{
            if (index !== exceptIndex && !item.video.paused) {{
                item.video.pause();
            }}
        }});
    }}

    function applySnapshot(target, snapshot) {{
        const video = target.video;
        const setTime = () => {{
            try {{
                const duration = Number.isFinite(video.duration) ? video.duration : null;
                const wanted = Math.max(0, snapshot.time || 0);
                video.currentTime = duration === null
                    ? wanted
                    : Math.min(wanted, Math.max(duration - 0.001, 0));
            }} catch (_) {{}}

            try {{ video.playbackRate = snapshot.rate || 1.0; }} catch (_) {{}}

            if (!snapshot.paused) {{
                const promise = video.play();
                if (promise && typeof promise.catch === "function") {{
                    promise.catch(() => {{}});
                }}
            }} else {{
                video.pause();
            }}
        }};

        if (video.readyState >= 1) {{
            setTime();
        }} else {{
            video.addEventListener("loadedmetadata", setTime, {{ once: true }});
            video.load();
        }}
    }}

    function setActive(index, syncFromCurrent=false) {{
        if (index < 0 || index >= players.length) return;

        let snapshot = null;
        if (syncFromCurrent && activeIndex >= 0 && players[activeIndex]) {{
            const current = players[activeIndex].video;
            snapshot = {{
                time: current.currentTime || 0,
                paused: current.paused,
                rate: current.playbackRate || 1.0,
            }};
            current.pause();
        }}

        activeIndex = index;

        players.forEach((item, i) => {{
            item.card.classList.toggle("active", i === activeIndex);
        }});

        if (snapshot) {{
            pauseOthers(index);
            applySnapshot(players[index], snapshot);
        }}

        updateTopStatus();
    }}

    function selectRelative(delta) {{
        if (!players.length) return;
        const next = ((activeIndex + delta) % players.length + players.length) % players.length;
        setActive(next, true);
    }}

    function selectSpecial(kind) {{
        const index = players.findIndex(item => Boolean(item.angle[kind]));
        if (index >= 0) setActive(index, true);
    }}

    function activeVideo() {{
        return activeIndex >= 0 && players[activeIndex]
            ? players[activeIndex].video
            : null;
    }}

    function seekBy(seconds) {{
        const video = activeVideo();
        if (!video) return;
        const maxTime = Number.isFinite(video.duration)
            ? Math.max(video.duration - 0.001, 0)
            : Infinity;
        video.currentTime = Math.min(
            Math.max((video.currentTime || 0) + seconds, 0),
            maxTime,
        );
        updateTopStatus();
    }}

    function stepFrame(direction) {{
        const item = players[activeIndex];
        if (!item) return;
        item.video.pause();
        const step = Number.isFinite(item.frameStep) && item.frameStep > 0
            ? item.frameStep
            : frameStep;
        seekBy(direction * step);
    }}

    function togglePlay() {{
        const video = activeVideo();
        if (!video) return;
        pauseOthers(activeIndex);
        if (video.paused) {{
            const promise = video.play();
            if (promise && typeof promise.catch === "function") {{
                promise.catch(() => {{}});
            }}
        }} else {{
            video.pause();
        }}
        updateTopStatus();
    }}

    function setRate(rate) {{
        const video = activeVideo();
        if (!video) return;
        video.playbackRate = rate;
        updateTopStatus();
    }}

    async function toggleFullscreen() {{
        const item = players[activeIndex];
        if (!item) return;
        try {{
            if (document.fullscreenElement) {{
                await document.exitFullscreen();
            }} else if (item.card.requestFullscreen) {{
                await item.card.requestFullscreen();
            }}
        }} catch (_) {{}}
    }}

    function createCard(angle, sourceIndex) {{
        const playerIndex = players.length;
        const card = document.createElement("div");
        card.className = "video-card";
        card.dataset.index = String(playerIndex);

        const header = document.createElement("div");
        header.className = "card-header";

        const title = document.createElement("div");
        title.className = "angle-name";
        title.textContent = angle.name;
        title.title = angle.name;

        const badge = document.createElement("span");
        badge.className = "active-badge";
        badge.textContent = "● Active";

        header.appendChild(title);
        header.appendChild(badge);

        const video = document.createElement("video");
        video.controls = true;
        video.preload = "metadata";
        video.playsInline = true;
        video.src = angle.url;

        const footer = document.createElement("div");
        footer.className = "card-footer";

        const cardStatus = document.createElement("div");
        cardStatus.className = "card-status";
        cardStatus.textContent = "Paused • 1.0× • 0:00.000";

        const open = document.createElement("a");
        open.className = "open-link";
        open.href = angle.url;
        open.target = "_blank";
        open.rel = "noopener noreferrer";
        open.textContent = "Open Video ↗";
        open.addEventListener("click", event => event.stopPropagation());

        footer.appendChild(cardStatus);
        footer.appendChild(open);

        card.appendChild(header);
        card.appendChild(video);
        card.appendChild(footer);

        if (angle.sas_error) {{
            const error = document.createElement("div");
            error.className = "error";
            error.textContent = `Signed URL refresh warning: ${{angle.sas_error}}`;
            card.appendChild(error);
        }}

        const item = {{
            angle,
            card,
            video,
            cardStatus,
            frameStep: frameStep,
            lastMediaTime: null,
            frameCallbackId: null,
        }};
        players.push(item);

        // Modern browsers expose presented-frame timestamps through
        // requestVideoFrameCallback. Measure the source cadence while the
        // clip plays so X/V use the real frame duration when available.
        if (typeof video.requestVideoFrameCallback === "function") {{
            const observeFrame = (_now, metadata) => {{
                const mediaTime = metadata && Number.isFinite(metadata.mediaTime)
                    ? metadata.mediaTime
                    : null;

                if (mediaTime !== null && item.lastMediaTime !== null) {{
                    const delta = mediaTime - item.lastMediaTime;
                    if (delta >= 0.005 && delta <= 0.100) {{
                        item.frameStep = delta;
                    }}
                }}

                if (mediaTime !== null) item.lastMediaTime = mediaTime;
                item.frameCallbackId = video.requestVideoFrameCallback(observeFrame);
            }};

            item.frameCallbackId = video.requestVideoFrameCallback(observeFrame);
        }}

        const makeActive = () => {{
            setActive(playerIndex, false);
        }};

        card.addEventListener("pointerdown", makeActive);
        video.addEventListener("focus", makeActive);
        video.addEventListener("play", () => {{
            if (activeIndex !== playerIndex) setActive(playerIndex, false);
            pauseOthers(playerIndex);
            updateTopStatus();
        }});
        video.addEventListener("pause", updateTopStatus);
        video.addEventListener("ratechange", updateTopStatus);
        video.addEventListener("timeupdate", () => {{
            cardStatus.textContent = statusText(video);
            if (activeIndex === playerIndex) updateTopStatus();
        }});
        video.addEventListener("loadedmetadata", () => {{
            cardStatus.textContent = statusText(video);
            if (activeIndex === playerIndex) updateTopStatus();
        }});

        return card;
    }}

    const primaryAngles = [];
    const secondaryAngles = [];
    angles.forEach((angle, index) => {{
        if ((angle.is_program || angle.is_replay) && primaryAngles.length < 2) {{
            primaryAngles.push([angle, index]);
        }} else {{
            secondaryAngles.push([angle, index]);
        }}
    }});

    if (primaryAngles.length === 1) primaryGrid.classList.add("one");
    primaryAngles.forEach(([angle, index]) => primaryGrid.appendChild(createCard(angle, index)));

    if (secondaryAngles.length) {{
        secondaryBlock.style.display = "block";
        secondaryAngles.forEach(([angle, index]) => secondaryGrid.appendChild(createCard(angle, index)));
    }}

    // If there were no PGM/Replay primary angles, put every card in the
    // secondary grid but keep the normal player ordering.
    if (!primaryAngles.length) {{
        primaryGrid.style.display = "none";
        secondaryBlock.style.display = "block";
        secondaryGrid.innerHTML = "";
        players.length = 0;
        angles.forEach((angle, index) => secondaryGrid.appendChild(createCard(angle, index)));
    }}

    let initialIndex = players.findIndex(item => item.angle.is_program);
    if (initialIndex < 0) initialIndex = players.findIndex(item => item.angle.is_replay);
    if (initialIndex < 0) initialIndex = 0;
    setActive(initialIndex, false);

    window.addEventListener("focus", () => {{
        componentFocused = true;
        focusNoteEl.textContent = "Shortcuts ready • click any angle to change control target.";
    }});

    window.addEventListener("blur", () => {{
        componentFocused = false;
        focusNoteEl.textContent = "Click a video to reactivate shortcuts.";
    }});

    root.addEventListener("pointerdown", () => {{
        componentFocused = true;
        focusNoteEl.textContent = "Shortcuts ready • click any angle to change control target.";
    }});

    document.addEventListener("keydown", event => {{
        const key = event.key.toLowerCase();
        const target = event.target;
        const tag = target && target.tagName ? target.tagName.toLowerCase() : "";
        const typing = tag === "input" || tag === "textarea" || tag === "select" || (target && target.isContentEditable);
        if (typing) return;

        const shiftEscape = event.shiftKey && event.key === "Escape";
        const mapped = new Set(["z", "x", "c", "v", "b", "d", "f", "p", "r", "1", "2", "3"]);
        if (!shiftEscape && !mapped.has(key)) return;

        event.preventDefault();
        event.stopPropagation();

        if (event.repeat && ["c", "d", "f", "p", "r", "1", "2", "3"].includes(key)) {{
            return;
        }}

        switch (key) {{
            case "z": seekBy(-5); break;
            case "x": stepFrame(-1); break;
            case "c": togglePlay(); break;
            case "v": stepFrame(1); break;
            case "b": seekBy(5); break;
            case "d": selectRelative(-1); break;
            case "f": selectRelative(1); break;
            case "p": selectSpecial("is_program"); break;
            case "r": selectSpecial("is_replay"); break;
            case "1": setRate(0.5); break;
            case "2": setRate(1.0); break;
            case "3": setRate(2.0); break;
            default:
                if (shiftEscape) toggleFullscreen();
        }}
    }}, true);

    updateTopStatus();
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
