const MAX_FILES = 20;
const MAX_SINGLE = 50 * 1024 * 1024;
const MAX_TOTAL = 200 * 1024 * 1024;

const state = {
  files: [],
  jobId: null,
  mergeId: null,
};

const fileInput = document.getElementById("fileInput");
const dropzone = document.getElementById("dropzone");
const dropText = document.getElementById("dropText");
const errorBox = document.getElementById("errorBox");
const fileList = document.getElementById("fileList");
const summaryText = document.getElementById("summaryText");
const startBtn = document.getElementById("startBtn");
const resetBtn = document.getElementById("resetBtn");
const outputName = document.getElementById("outputName");
const progressBar = document.getElementById("progressBar");
const progressText = document.getElementById("progressText");
const statusList = document.getElementById("statusList");
const downloadBtn = document.getElementById("downloadBtn");

function makeId() {
  if (window.crypto && typeof window.crypto.randomUUID === "function") {
    return window.crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function ext(name) {
  const parts = name.toLowerCase().split(".");
  return parts.length > 1 ? `.${parts.pop()}` : "";
}

function iconColor(extension) {
  if ([".doc", ".docx", ".odt", ".rtf"].includes(extension)) return "#2563EB";
  if ([".xlsx", ".xls", ".ods", ".csv"].includes(extension)) return "#16A34A";
  if ([".ppt", ".pptx", ".odp"].includes(extension)) return "#EA580C";
  if ([".pdf"].includes(extension)) return "#DC2626";
  if ([".jpg", ".jpeg", ".png", ".webp", ".tiff", ".bmp", ".gif", ".svg", ".heic"].includes(extension)) return "#7C3AED";
  if ([".html", ".htm"].includes(extension)) return "#0D9488";
  return "#6B7280";
}

function formatSize(size) {
  return `${(size / 1024 / 1024).toFixed(2)} MB`;
}

function showError(message) {
  errorBox.textContent = message;
  dropzone.classList.add("error");
  setTimeout(() => dropzone.classList.remove("error"), 2000);
}

function totalSize() {
  return state.files.reduce((acc, f) => acc + f.size, 0);
}

function canAdd(file) {
  if (state.files.length >= MAX_FILES) return "최대 20개 파일까지 업로드할 수 있습니다.";
  if (file.size > MAX_SINGLE) return `${file.name}: 단일 파일 50MB를 초과했습니다.`;
  if (totalSize() + file.size > MAX_TOTAL) return "총 업로드 용량 200MB를 초과했습니다.";
  return "";
}

function renderFiles() {
  fileList.innerHTML = "";
  state.files.forEach((f, index) => {
    const li = document.createElement("li");
    li.className = "file-item";
    li.draggable = window.innerWidth > 767;
    li.dataset.id = f.id;
    li.innerHTML = `
      <span class="icon" style="background:${iconColor(ext(f.name))}"></span>
      <div class="meta">
        <div>${f.name}</div>
        <small>${ext(f.name)} / ${formatSize(f.size)} / → PDF</small>
      </div>
      <div class="mobile-sort">
        <button data-move="up">↑</button>
        <button data-move="down">↓</button>
      </div>
      <button data-remove="1">×</button>
    `;
    li.querySelector("[data-remove]").addEventListener("click", () => {
      state.files = state.files.filter((item) => item.id !== f.id);
      renderFiles();
    });
    li.querySelectorAll("[data-move]").forEach((btn) => {
      btn.addEventListener("click", () => moveItem(index, btn.dataset.move));
    });
    li.querySelectorAll("button").forEach((btn) => {
      btn.addEventListener("dragstart", (e) => e.preventDefault());
    });
    bindDnD(li);
    fileList.appendChild(li);
  });

  summaryText.textContent = `총 ${state.files.length}개 파일 / 합산 ${formatSize(totalSize())}`;
  startBtn.disabled = state.files.length === 0;
}

function moveItem(index, direction) {
  const newIndex = direction === "up" ? index - 1 : index + 1;
  if (newIndex < 0 || newIndex >= state.files.length) return;
  [state.files[index], state.files[newIndex]] = [state.files[newIndex], state.files[index]];
  renderFiles();
}

function bindDnD(item) {
  item.addEventListener("dragstart", (ev) => {
    item.classList.add("dragging");
    ev.dataTransfer.effectAllowed = "move";
    ev.dataTransfer.setData("text/plain", item.dataset.id || "");
  });
  item.addEventListener("dragend", () => {
    item.classList.remove("dragging");
    applyFileOrderFromDom();
  });
}

function applyFileOrderFromDom() {
  const ids = [...fileList.querySelectorAll(".file-item")].map((li) => li.dataset.id);
  if (ids.length === 0 || ids.length !== state.files.length) return;
  state.files.sort((a, b) => ids.indexOf(a.id) - ids.indexOf(b.id));
}

fileList.addEventListener("dragover", (e) => {
  e.preventDefault();
  e.dataTransfer.dropEffect = "move";
  const dragging = fileList.querySelector(".dragging");
  if (!dragging) return;
  const items = [...fileList.querySelectorAll(".file-item:not(.dragging)")];
  const next = items.find((node) => {
    const box = node.getBoundingClientRect();
    return e.clientY < box.top + box.height / 2;
  });
  if (next) fileList.insertBefore(dragging, next);
  else fileList.appendChild(dragging);
});

fileList.addEventListener("drop", (e) => {
  e.preventDefault();
  applyFileOrderFromDom();
});

function addFiles(fileListLike) {
  const files = Array.from(fileListLike || []);
  for (const file of files) {
    const error = canAdd(file);
    if (error) {
      showError(error);
      continue;
    }
    state.files.push({ id: makeId(), file, name: file.name, size: file.size });
  }
  renderFiles();
}

dropzone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropzone.classList.add("active");
  dropText.textContent = "놓으세요!";
});
dropzone.addEventListener("dragleave", () => {
  dropzone.classList.remove("active");
  dropText.textContent = "파일을 여기에 드래그하거나 클릭하여 선택";
});
dropzone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropzone.classList.remove("active");
  dropText.textContent = "파일을 여기에 드래그하거나 클릭하여 선택";
  addFiles(e.dataTransfer.files);
});
fileInput.addEventListener("change", (e) => {
  addFiles(e.target.files);
  // Allow selecting the same file again in the next picker open.
  e.target.value = "";
});

async function startProcess() {
  const formData = new FormData();
  const fallbackName = `merged_${new Date().toISOString().slice(0, 19).replace(/[-:T]/g, "")}.pdf`;
  const out = outputName.value.trim() || fallbackName;
  formData.append("output_name", out.endsWith(".pdf") ? out : `${out}.pdf`);
  state.files.forEach((entry) => formData.append("files", entry.file, entry.name));

  const upload = await fetch("/api/upload", { method: "POST", body: formData });
  if (!upload.ok) {
    showError((await upload.json()).detail || "업로드 실패");
    return;
  }

  const data = await upload.json();
  state.jobId = data.job_id;
  statusList.innerHTML = "";
  progressText.textContent = "변환 중...";
  monitorProgress();
}

async function monitorProgress() {
  if (!state.jobId) return;

  const source = new EventSource(`/api/progress-stream/${state.jobId}`);
  source.onmessage = async (event) => {
    const payload = JSON.parse(event.data);
    updateProgress(payload);

    const allDone = payload.files.every((f) => ["done", "error", "skipped"].includes(f.status));
    if (allDone) {
      source.close();
      progressText.textContent = "모든 파일 병합 중...";
      const mergeResp = await fetch("/api/merge", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: state.jobId, output_name: outputName.value.trim() || undefined }),
      });
      if (!mergeResp.ok) {
        showError((await mergeResp.json()).detail || "병합 실패");
        progressText.textContent = "병합 실패";
        return;
      }
      const mergeData = await mergeResp.json();
      state.mergeId = mergeData.merge_id;
      progressText.textContent = "완료! 다운로드 가능합니다.";
      downloadBtn.classList.remove("hidden");
      triggerDownload();
    }
  };
}

function statusLabel(status) {
  if (status === "waiting") return "대기 중";
  if (status === "converting") return "변환 중";
  if (status === "done") return "완료";
  if (status === "skipped") return "건너뜀";
  return "오류";
}

function statusColor(status) {
  if (status === "converting") return "#2563EB";
  if (status === "done") return "#16A34A";
  if (status === "error") return "#DC2626";
  if (status === "skipped") return "#D97706";
  return "#6B7280";
}

function updateProgress(payload) {
  progressBar.style.width = `${payload.overall_progress}%`;
  statusList.innerHTML = "";
  payload.files.forEach((f) => {
    const li = document.createElement("li");
    li.className = "status-item";
    const statusInfo = f.error_message ? `${statusLabel(f.status)} (${f.error_message})` : statusLabel(f.status);
    li.innerHTML = `
      <span class="icon" style="background:${statusColor(f.status)}"></span>
      <span>${f.original_name}</span>
      <span style="color:${statusColor(f.status)}">${statusInfo}</span>
      ${f.status === "error" ? `<button data-skip="${f.file_id}">건너뛰기</button>` : "<span></span>"}
    `;
    const skipBtn = li.querySelector("[data-skip]");
    if (skipBtn) {
      skipBtn.addEventListener("click", async () => {
        await fetch(`/api/skip/${state.jobId}/${f.file_id}`, { method: "POST" });
      });
    }
    statusList.appendChild(li);
  });
}

function triggerDownload() {
  if (!state.mergeId) return;
  const url = `/api/download/${state.mergeId}`;
  const a = document.createElement("a");
  a.href = url;
  a.download = "";
  a.click();
}

startBtn.addEventListener("click", startProcess);
downloadBtn.addEventListener("click", triggerDownload);
resetBtn.addEventListener("click", async () => {
  if (state.jobId) await fetch(`/api/cleanup/${state.jobId}`, { method: "DELETE" });
  state.files = [];
  state.jobId = null;
  state.mergeId = null;
  outputName.value = "";
  progressBar.style.width = "0%";
  progressText.textContent = "대기 중";
  statusList.innerHTML = "";
  downloadBtn.classList.add("hidden");
  errorBox.textContent = "";
  renderFiles();
});
