/* =========================================================
   MediaFlow — app.js
   ========================================================= */

const API_BASE = "";

/* =========================================================
   UTILITY HELPERS
   ========================================================= */
function show(el) { el.classList.remove("hidden"); }
function hide(el) { el.classList.add("hidden"); }

function setError(el, msg) {
    el.textContent = msg;
    el.className = "status-msg is-error";
    show(el);
}
function setSuccess(el, msg) {
    el.textContent = msg;
    el.className = "status-msg is-success";
    show(el);
}
function setInfo(el, msg) {
    el.textContent = msg;
    el.className = "status-msg";
    show(el);
}

function formatDuration(seconds) {
    if (!seconds) return "";
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    return h > 0
        ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`
        : `${m}:${String(s).padStart(2, "0")}`;
}

function formatBytes(bytes) {
    if (!bytes) return "";
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 ** 2) return (bytes / 1024).toFixed(1) + " KB";
    if (bytes < 1024 ** 3) return (bytes / 1024 ** 2).toFixed(1) + " MB";
    return (bytes / 1024 ** 3).toFixed(2) + " GB";
}

function setLoading(btn, state) {
    const text = btn.querySelector(".btn-text, .btn-download-text");
    const spinner = btn.querySelector(".btn-spinner");
    btn.disabled = state;
    if (state) {
        if (text) text.style.opacity = "0.5";
        if (spinner) show(spinner);
    } else {
        if (text) text.style.opacity = "1";
        if (spinner) hide(spinner);
    }
}

/* =========================================================
   PLATFORM THEMING
   Maps yt-dlp extractor_key → accent colors & gradient
   ========================================================= */
const PLATFORM_THEMES = {
    Youtube: { a1: "#ff0000", a2: "#ff6b6b", grad: "linear-gradient(135deg,#ff0000 0%,#cc0000 100%)", orb1: "#ff0000", orb2: "#ff4444" },
    Instagram: { a1: "#e1306c", a2: "#f77737", grad: "linear-gradient(135deg,#833ab4 0%,#e1306c 50%,#f77737 100%)", orb1: "#833ab4", orb2: "#f77737" },
    Facebook: { a1: "#1877f2", a2: "#42a5f5", grad: "linear-gradient(135deg,#1877f2 0%,#42a5f5 100%)", orb1: "#1877f2", orb2: "#0d47a1" },
    TikTok: { a1: "#69c9d0", a2: "#ee1d52", grad: "linear-gradient(135deg,#010101 0%,#ee1d52 50%,#69c9d0 100%)", orb1: "#ee1d52", orb2: "#69c9d0" },
    Twitter: { a1: "#1da1f2", a2: "#0d8ddb", grad: "linear-gradient(135deg,#1da1f2 0%,#0d8ddb 100%)", orb1: "#1da1f2", orb2: "#075e99" },
    Twitch: { a1: "#9147ff", a2: "#bf94ff", grad: "linear-gradient(135deg,#9147ff 0%,#bf94ff 100%)", orb1: "#9147ff", orb2: "#6441a5" },
    _default: { a1: "#6c63ff", a2: "#00d4ff", grad: "linear-gradient(135deg,#6c63ff 0%,#00d4ff 100%)", orb1: "#6c63ff", orb2: "#00d4ff" },
};

function applyPlatformTheme(platformKey) {
    const theme = PLATFORM_THEMES[platformKey] || PLATFORM_THEMES["_default"];
    const root = document.documentElement;
    root.style.setProperty("--accent", theme.a1);
    root.style.setProperty("--accent-2", theme.a2);
    root.style.setProperty("--accent-grad", theme.grad);
    // Re-colour the background orbs via inline style on the elements
    const orb1 = document.querySelector(".orb-1");
    const orb2 = document.querySelector(".orb-2");
    if (orb1) orb1.style.background = `radial-gradient(circle,${theme.orb1},transparent 70%)`;
    if (orb2) orb2.style.background = `radial-gradient(circle,${theme.orb2},transparent 70%)`;
    // Show a small platform badge glow on the preview card
    const preview = document.getElementById("dl-preview");
    if (preview) preview.style.borderColor = theme.a1 + "55";
}

/* =========================================================
   DOWNLOADER — state
   ========================================================= */
let dlResolutions = [];
let dlSelectedType = "video";

/* DOM refs */
const dlUrl = document.getElementById("dl-url");
const dlFetchBtn = document.getElementById("dl-fetch-btn");
const dlUrlError = document.getElementById("dl-url-error");
const dlPreview = document.getElementById("dl-preview");
const dlThumb = document.getElementById("dl-thumb");
const dlTitleEl = document.getElementById("dl-title");
const dlUploaderEl = document.getElementById("dl-uploader");
const dlPlatformEl = document.getElementById("dl-platform");
const dlDurationEl = document.getElementById("dl-duration");
const dlOptions = document.getElementById("dl-options");
const dlResolutionSel = document.getElementById("dl-resolution");
const resolutionBlock = document.getElementById("resolution-block");
const dlDownloadBtn = document.getElementById("dl-download-btn");
const dlDownloadStatus = document.getElementById("dl-download-status");
const typeVideoBtn = document.getElementById("type-video");
const typeAudioBtn = document.getElementById("type-audio");

/* ---- Fetch video info ---- */
async function fetchVideoInfo() {
    const url = dlUrl.value.trim();
    hide(dlUrlError);

    if (!url) {
        dlUrlError.textContent = "Please paste a video URL first.";
        show(dlUrlError);
        return;
    }

    setLoading(dlFetchBtn, true);
    hide(dlPreview);
    hide(dlOptions);
    hide(dlDownloadStatus);

    try {
        const resp = await fetch(`${API_BASE}/api/info?url=${encodeURIComponent(url)}`);
        const data = await resp.json();

        if (!resp.ok) {
            throw new Error(data.error || "Failed to fetch video info.");
        }

        // Populate preview
        dlThumb.src = data.thumbnail || "";
        dlTitleEl.textContent = data.title || "Unknown Title";
        dlUploaderEl.textContent = data.uploader ? "👤 " + data.uploader : "";
        dlPlatformEl.textContent = data.platform ? "🌐 " + data.platform : "";
        dlDurationEl.textContent = data.duration ? "⏱ " + formatDuration(data.duration) : "";

        show(dlPreview);

        // Apply platform colour theme instantly
        applyPlatformTheme(data.platform || "");

        // Populate resolution dropdown — highest first, auto-select it
        dlResolutions = data.resolutions || [];
        dlResolutionSel.innerHTML = "";
        if (dlResolutions.length === 0) {
            const opt = document.createElement("option");
            opt.value = "best";
            opt.dataset.formatId = "";
            opt.textContent = "Best Available";
            dlResolutionSel.appendChild(opt);
        } else {
            dlResolutions.forEach(r => {
                const opt = document.createElement("option");
                opt.value = r.label;
                opt.dataset.formatId = r.format_id || "";
                // Show size: exact with no prefix, estimated with ~
                let sizeStr = "";
                if (r.filesize) {
                    sizeStr = (r.estimated ? "  (~" : "  (~") + formatBytes(r.filesize) + ")";
                }
                opt.textContent = r.label + sizeStr;
                dlResolutionSel.appendChild(opt);
            });
            // Auto-select the highest resolution (first in the list)
            dlResolutionSel.selectedIndex = 0;
        }

        show(dlOptions);
        hide(dlDownloadStatus);

    } catch (err) {
        dlUrlError.textContent = err.message;
        show(dlUrlError);
    } finally {
        setLoading(dlFetchBtn, false);
    }
}

if (dlFetchBtn) {
    dlFetchBtn.addEventListener("click", fetchVideoInfo);
}

if (dlUrl) {
    dlUrl.addEventListener("keydown", e => { if (e.key === "Enter") fetchVideoInfo(); });
    // Reset to default theme when URL is cleared
    dlUrl.addEventListener("input", () => { if (!dlUrl.value.trim()) applyPlatformTheme("_default"); });
}


/* ---- Type toggle ---- */
if (typeof typeVideoBtn !== 'undefined' && typeVideoBtn && typeof typeAudioBtn !== 'undefined' && typeAudioBtn) {
    [typeVideoBtn, typeAudioBtn].forEach(btn => {
        btn.addEventListener("click", () => {
            dlSelectedType = btn.dataset.value;
            typeVideoBtn.classList.toggle("active", dlSelectedType === "video");
            typeAudioBtn.classList.toggle("active", dlSelectedType === "audio");
            // Show/hide resolution when audio is picked
            if (typeof resolutionBlock !== 'undefined' && resolutionBlock) {
                resolutionBlock.style.opacity = dlSelectedType === "audio" ? "0.4" : "1";
                resolutionBlock.style.pointerEvents = dlSelectedType === "audio" ? "none" : "auto";
            }
        });
    });
}

/* ---- Download ---- */
if (dlDownloadBtn) {
    dlDownloadBtn.addEventListener("click", async () => {
        const url = dlUrl.value.trim();
        const selectedOpt = dlResolutionSel.options[dlResolutionSel.selectedIndex];
        const resolution = selectedOpt?.value || "720p";
        const format_id = selectedOpt?.dataset?.formatId || "";  // exact stream id

        if (!url) return;

        setLoading(dlDownloadBtn, true);
        setInfo(dlDownloadStatus, "⏳ Downloading… this may take a moment.");

        try {
            // Use a hidden form POST so the browser handles the file download natively.
            // This avoids blob-URL size limits and popup/security blockers in Chrome/Edge.
            // The backend determines the exact filename and sends Content-Disposition.
            const form = document.createElement("form");
            form.method = "POST";
            form.action = `${API_BASE}/api/download`;
            form.style.display = "none";

            const fields = { url, resolution, format_id, media_type: dlSelectedType };
            Object.entries(fields).forEach(([k, v]) => {
                const inp = document.createElement("input");
                inp.type = "hidden";
                inp.name = k;
                inp.value = v;
                form.appendChild(inp);
            });

            document.body.appendChild(form);
            form.submit();

            // Clean up the DOM
            setTimeout(() => form.remove(), 100);

            // Give the browser a moment to receive headers, then show success
            setTimeout(() => {
                setSuccess(dlDownloadStatus, "✅ Download started! Check your browser's Downloads folder.");
                setLoading(dlDownloadBtn, false);
            }, 1500);

        } catch (err) {
            setError(dlDownloadStatus, "❌ " + err.message);
            setLoading(dlDownloadBtn, false);
        }
    });
}




/* =========================================================
   CONVERTER — state
   ========================================================= */
let cvSelectedFile = null;
let cvSelectedFormat = null;

/* DOM refs */
const cvDropzone = document.getElementById("cv-dropzone");
const cvFileInput = document.getElementById("cv-file-input");
const cvBrowseBtn = document.getElementById("cv-browse-btn");
const cvFileInfo = document.getElementById("cv-file-info");
const cvFileName = document.getElementById("cv-file-name");
const cvFileSize = document.getElementById("cv-file-size");
const cvRemoveFile = document.getElementById("cv-remove-file");
const cvFormatPicker = document.getElementById("cv-format-picker");
const cvConvertBtn = document.getElementById("cv-convert-btn");
const cvStatus = document.getElementById("cv-status");
const formatBtns = document.querySelectorAll(".format-btn");

/* ---- File selection helpers ---- */
function setFile(file) {
    cvSelectedFile = file;
    cvFileName.textContent = file.name;
    cvFileSize.textContent = formatBytes(file.size);
    hide(cvDropzone);
    show(cvFileInfo);
    show(cvFormatPicker);
    hide(cvStatus);
}

function clearFile() {
    cvSelectedFile = null;
    cvSelectedFormat = null;
    cvFileInput.value = "";
    formatBtns.forEach(b => b.classList.remove("selected"));
    cvConvertBtn.disabled = true;
    show(cvDropzone);
    hide(cvFileInfo);
    hide(cvFormatPicker);
    hide(cvStatus);
}

/* ---- Browse + drop ---- */
cvBrowseBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    cvFileInput.click();
});
cvDropzone.addEventListener("click", () => cvFileInput.click());
cvDropzone.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") cvFileInput.click(); });

cvFileInput.addEventListener("change", () => {
    if (cvFileInput.files && cvFileInput.files[0]) setFile(cvFileInput.files[0]);
});

cvDropzone.addEventListener("dragover", e => {
    e.preventDefault();
    cvDropzone.classList.add("drag-over");
});
cvDropzone.addEventListener("dragleave", () => cvDropzone.classList.remove("drag-over"));
cvDropzone.addEventListener("drop", e => {
    e.preventDefault();
    cvDropzone.classList.remove("drag-over");
    const file = e.dataTransfer.files[0];
    if (file) setFile(file);
});

cvRemoveFile.addEventListener("click", clearFile);

/* ---- Format selection ---- */
formatBtns.forEach(btn => {
    btn.addEventListener("click", () => {
        formatBtns.forEach(b => b.classList.remove("selected"));
        btn.classList.add("selected");
        cvSelectedFormat = btn.dataset.format;
        cvConvertBtn.disabled = false;
    });
});

/* ---- Convert ---- */
if (typeof cvConvertBtn !== 'undefined' && cvConvertBtn) {
    cvConvertBtn.addEventListener("click", async () => {
        if (!cvSelectedFile || !cvSelectedFormat) return;

        setLoading(cvConvertBtn, true);
        setInfo(cvStatus, `⏳ Converting to .${cvSelectedFormat.toUpperCase()}… please wait.`);

        try {
            const fd = new FormData();
            fd.append("file", cvSelectedFile);
            fd.append("target_format", cvSelectedFormat);

            const resp = await fetch(`${API_BASE}/api/v2/convert`, {
                method: "POST",
                body: fd,
            });

            if (!resp.ok) {
                let errMsg = `Server error ${resp.status}`;
                try { const j = await resp.json(); errMsg = j.error || errMsg; } catch (_) { }
                throw new Error(errMsg);
            }

            // Trigger a file download from the binary response
            const blob = await resp.blob();
            const contentDisp = resp.headers.get("Content-Disposition") || "";
            const nameMatch = contentDisp.match(/filename\*?=(?:UTF-8'')?["']?([^"';\n]+)/i);
            const filename = nameMatch ? decodeURIComponent(nameMatch[1]) : `converted.${cvSelectedFormat}`;

            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 1000);

            setSuccess(cvStatus, `✅ Done! Saved as ${filename}`);
        } catch (err) {
            setError(cvStatus, "❌ " + err.message);
        } finally {
            setLoading(cvConvertBtn, false);
        }
    });
}

