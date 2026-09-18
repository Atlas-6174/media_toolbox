// Inicializar iconos de Lucide
document.addEventListener("DOMContentLoaded", () => {
  lucide.createIcons();
  checkDockerStatus();
  initDropzones();
});

// Chequeo de estado de Docker
async function checkDockerStatus() {
  const badge = document.getElementById("docker-status");
  try {
    const res = await fetch("/api/status");
    const data = await res.json();
    if (data.docker) {
      badge.innerHTML = \`<span class="w-2 h-2 rounded-full bg-emerald-400"></span><span class="text-emerald-300">Docker Activo</span>\`;
    } else {
      badge.innerHTML = \`<span class="w-2 h-2 rounded-full bg-rose-500"></span><span class="text-rose-300 font-semibold">Docker Desconectado</span>\`;
    }
  } catch {
    badge.innerHTML = \`<span class="w-2 h-2 rounded-full bg-rose-500"></span><span class="text-rose-300">Sin conexión</span>\`;
  }
}

// Navegación entre pestañas principales
function switchTab(tabId) {
  document.querySelectorAll(".tab-panel").forEach(p => p.classList.add("hidden"));
  document.querySelectorAll(".tab-btn").forEach(b => {
    b.classList.remove("bg-indigo-600", "text-white", "shadow-lg", "shadow-indigo-600/20");
    b.classList.add("text-slate-400");
  });

  const activePanel = document.getElementById(`panel-${tabId}`);
  const activeBtn = document.getElementById(`tab-${tabId}`);
  if (activePanel && activeBtn) {
    activePanel.classList.remove("hidden");
    activeBtn.classList.remove("text-slate-400");
    activeBtn.classList.add("bg-indigo-600", "text-white", "shadow-lg", "shadow-indigo-600/20");
  }
  lucide.createIcons();
}

// Navegación en subpestañas de Video
function switchVideoSubtab(subId) {
  document.querySelectorAll(".vpanel").forEach(p => p.classList.add("hidden"));
  document.querySelectorAll(".vsub-btn").forEach(b => {
    b.classList.remove("bg-indigo-600/20", "text-indigo-400", "border", "border-indigo-500/30");
    b.classList.add("text-slate-400");
  });

  const activeVpanel = document.getElementById(`vpanel-${subId}`);
  const activeVbtn = document.getElementById(`vsub-${subId}`);
  if (activeVpanel && activeVbtn) {
    activeVpanel.classList.remove("hidden");
    activeVbtn.classList.remove("text-slate-400");
    activeVbtn.classList.add("bg-indigo-600/20", "text-indigo-400", "border", "border-indigo-500/30");
  }
  lucide.createIcons();
}

// Gestión universal de Dropzones
function initDropzones() {
  setupDropzone("dropzone-audio", "file-audio", "selected-audio");
  setupDropzone("dropzone-video", "file-video", "selected-video");
  setupDropzone("dropzone-book", "file-book", "selected-book");
  setupDropzone("dropzone-image", "file-image", "selected-image");
  setupMultipleDropzone("dropzone-pdf", "files-pdf", "selected-pdfs");
}

function setupDropzone(zoneId, inputId, labelId) {
  const zone = document.getElementById(zoneId);
  const input = document.getElementById(inputId);
  const label = document.getElementById(labelId);
  if (!zone || !input) return;

  zone.addEventListener("click", () => input.click());
  zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("dropzone-active"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("dropzone-active"));
  zone.addEventListener("drop", (e) => {
    e.preventDefault();
    zone.classList.remove("dropzone-active");
    if (e.dataTransfer.files.length) {
      input.files = e.dataTransfer.files;
      updateFileBadge(input.files[0], label);
    }
  });

  input.addEventListener("change", () => {
    if (input.files.length) updateFileBadge(input.files[0], label);
  });
}

function setupMultipleDropzone(zoneId, inputId, containerId) {
  const zone = document.getElementById(zoneId);
  const input = document.getElementById(inputId);
  const container = document.getElementById(containerId);
  if (!zone || !input) return;

  zone.addEventListener("click", () => input.click());
  zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("dropzone-active"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("dropzone-active"));
  zone.addEventListener("drop", (e) => {
    e.preventDefault();
    zone.classList.remove("dropzone-active");
    if (e.dataTransfer.files.length) {
      input.files = e.dataTransfer.files;
      renderMultipleBadges(input.files, container);
    }
  });

  input.addEventListener("change", () => {
    if (input.files.length) renderMultipleBadges(input.files, container);
  });
}

function updateFileBadge(file, label) {
  if (!label || !file) return;
  const sizeMb = (file.size / (1024 * 1024)).toFixed(2);
  label.innerHTML = `<i data-lucide="file-check" class="w-3.5 h-3.5"></i> ${file.name} (${sizeMb} MB)`;
  label.classList.remove("hidden");
  lucide.createIcons();
}

function renderMultipleBadges(files, container) {
  if (!container || !files.length) return;
  container.innerHTML = "";
  container.classList.remove("hidden");
  container.classList.add("flex");
  Array.from(files).forEach(f => {
    const badge = document.createElement("span");
    badge.className = "inline-flex items-center gap-1.5 bg-indigo-500/10 border border-indigo-500/20 text-indigo-300 text-xs px-2.5 py-1 rounded-lg";
    badge.innerHTML = `<i data-lucide="file" class="w-3 h-3"></i> ${f.name}`;
    container.appendChild(badge);
  });
  lucide.createIcons();
}

// Seguimiento visual de tareas en tiempo real
function startTaskMonitoring(taskId, previewType = "generic") {
  const box = document.getElementById("task-feedback");
  const msg = document.getElementById("task-message");
  const percent = document.getElementById("task-percent");
  const bar = document.getElementById("task-bar");
  const resultBox = document.getElementById("result-box");
  const previewContainer = document.getElementById("preview-container");
  const downloadLink = document.getElementById("download-link");

  box.classList.remove("hidden");
  resultBox.classList.add("hidden");
  previewContainer.innerHTML = "";
  bar.style.width = "5%";
  percent.innerText = "5%";
  msg.innerHTML = `<i data-lucide="loader" class="w-4 h-4 animate-spin text-indigo-400"></i> Iniciando micro-contenedor...`;
  lucide.createIcons();

  const interval = setInterval(async () => {
    try {
      const res = await fetch(`/api/tasks/${taskId}`);
      const data = await res.json();

      if (data.status === "running") {
        const pct = data.progress || 25;
        bar.style.width = `${pct}%`;
        percent.innerText = `${pct}%`;
        msg.innerHTML = `<i data-lucide="loader" class="w-4 h-4 animate-spin text-indigo-400"></i> ${data.message}`;
        lucide.createIcons();
      } else if (data.status === "done") {
        clearInterval(interval);
        bar.style.width = "100%";
        percent.innerText = "100%";
        msg.innerHTML = `<i data-lucide="check" class="w-4 h-4 text-emerald-400"></i> ${data.message}`;
        downloadLink.href = data.download_url;
        downloadLink.setAttribute("download", data.filename);

        // Previsualización interactiva
        if (data.preview_url) {
          if (previewType === "audio") {
            previewContainer.innerHTML = `<audio controls class="w-full mt-2 rounded-xl" src="${data.preview_url}"></audio>`;
          } else if (previewType === "image" || previewType === "gif") {
            previewContainer.innerHTML = `<img src="${data.preview_url}" class="max-h-64 mx-auto rounded-xl border border-slate-700 shadow-lg object-contain">`;
          }
        }

        resultBox.classList.remove("hidden");
        lucide.createIcons();
      } else if (data.status === "error") {
        clearInterval(interval);
        bar.style.width = "100%";
        bar.classList.add("bg-rose-500");
        msg.innerHTML = `<i data-lucide="alert-circle" class="w-4 h-4 text-rose-400"></i> Falló: ${data.message}`;
        lucide.createIcons();
      }
    } catch {
      clearInterval(interval);
    }
  }, 600);
}

// ACCIONES DE PROCESAMIENTO
async function processAudio() {
  const file = document.getElementById("file-audio").files[0];
  if (!file) return alert("Por favor selecciona o arrastra un video primero.");
  const formData = new FormData();
  formData.append("file", file);
  formData.append("formato", document.getElementById("format-audio").value);

  const res = await fetch("/api/audio", { method: "POST", body: formData });
  const data = await res.json();
  startTaskMonitoring(data.task_id, "audio");
}

async function processCompress() {
  const file = document.getElementById("file-video").files[0];
  if (!file) return alert("Por favor selecciona o arrastra un video primero.");
  const formData = new FormData();
  formData.append("file", file);
  formData.append("perfil", document.getElementById("compress-profile").value);

  const res = await fetch("/api/compress", { method: "POST", body: formData });
  const data = await res.json();
  startTaskMonitoring(data.task_id, "video");
}

async function processTrim() {
  const file = document.getElementById("file-video").files[0];
  if (!file) return alert("Por favor selecciona o arrastra un video primero.");
  const formData = new FormData();
  formData.append("file", file);
  formData.append("desde", document.getElementById("trim-start").value);
  formData.append("hasta", document.getElementById("trim-end").value || "");

  const res = await fetch("/api/trim", { method: "POST", body: formData });
  const data = await res.json();
  startTaskMonitoring(data.task_id, "video");
}

async function processGif() {
  const file = document.getElementById("file-video").files[0];
  if (!file) return alert("Por favor selecciona o arrastra un video primero.");
  const formData = new FormData();
  formData.append("file", file);
  formData.append("desde", document.getElementById("gif-start").value);
  formData.append("duracion", document.getElementById("gif-dur").value);
  formData.append("fps", document.getElementById("gif-fps").value);

  const res = await fetch("/api/gif", { method: "POST", body: formData });
  const data = await res.json();
  startTaskMonitoring(data.task_id, "gif");
}

async function processMute() {
  const file = document.getElementById("file-video").files[0];
  if (!file) return alert("Por favor selecciona o arrastra un video primero.");
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch("/api/mute", { method: "POST", body: formData });
  const data = await res.json();
  startTaskMonitoring(data.task_id, "video");
}

async function processSnapshot() {
  const file = document.getElementById("file-video").files[0];
  if (!file) return alert("Por favor selecciona o arrastra un video primero.");
  const formData = new FormData();
  formData.append("file", file);
  formData.append("tiempo", document.getElementById("snap-time").value);

  const res = await fetch("/api/snapshot", { method: "POST", body: formData });
  const data = await res.json();
  startTaskMonitoring(data.task_id, "image");
}

async function processDownload() {
  const url = document.getElementById("dl-url").value.trim();
  if (!url) return alert("Por favor ingresa una URL válida.");
  const formData = new FormData();
  formData.append("url", url);
  formData.append("audio", document.getElementById("dl-audio").checked);
  formData.append("calidad", document.getElementById("dl-quality").value);

  const res = await fetch("/api/download", { method: "POST", body: formData });
  const data = await res.json();
  startTaskMonitoring(data.task_id, document.getElementById("dl-audio").checked ? "audio" : "video");
}

async function processBook() {
  const file = document.getElementById("file-book").files[0];
  if (!file) return alert("Por favor selecciona o arrastra un libro electrónico primero.");
  const formData = new FormData();
  formData.append("file", file);
  formData.append("pagina", document.getElementById("book-page").value);
  const profile = document.getElementById("book-profile").value;
  if (profile) formData.append("perfil", profile);

  const res = await fetch("/api/convert", { method: "POST", body: formData });
  const data = await res.json();
  startTaskMonitoring(data.task_id, "generic");
}

async function processPdfMerge() {
  const files = document.getElementById("files-pdf").files;
  if (!files || files.length < 2) return alert("Por favor selecciona al menos 2 archivos PDF para unir.");
  const formData = new FormData();
  Array.from(files).forEach(f => formData.append("files", f));
  formData.append("salida", document.getElementById("pdf-output-name").value);

  const res = await fetch("/api/pdf/merge", { method: "POST", body: formData });
  const data = await res.json();
  startTaskMonitoring(data.task_id, "generic");
}

async function processImage() {
  const file = document.getElementById("file-image").files[0];
  if (!file) return alert("Por favor selecciona o arrastra una imagen primero.");
  const formData = new FormData();
  formData.append("file", file);
  formData.append("formato", document.getElementById("img-format").value);
  formData.append("calidad", document.getElementById("img-quality").value);
  const width = document.getElementById("img-width").value;
  if (width) formData.append("ancho", width);

  const res = await fetch("/api/image", { method: "POST", body: formData });
  const data = await res.json();
  startTaskMonitoring(data.task_id, "image");
}
