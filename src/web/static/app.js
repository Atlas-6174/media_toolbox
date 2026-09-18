// Inicializar componentes al cargar
let notifManager = null;

document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  notifManager = new NotificationManager();
  lucide.createIcons();
  checkDockerStatus();
  initDropzones();
  loadStorageInfo();
  initPWA();
  initGlobalDragDrop();
});

// GESTIÓN DE TEMA (CLARO / OSCURO)
function initTheme() {
  const saved = localStorage.getItem("theme");
  const prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  const isDark = saved ? saved === "dark" : prefersDark;
  applyTheme(isDark);
}

function toggleTheme() {
  const isDark = document.documentElement.classList.contains("dark");
  applyTheme(!isDark);
}

function applyTheme(isDark) {
  if (isDark) {
    document.documentElement.classList.add("dark");
    localStorage.setItem("theme", "dark");
  } else {
    document.documentElement.classList.remove("dark");
    localStorage.setItem("theme", "light");
  }
  const icon = document.getElementById("theme-icon");
  if (icon) {
    icon.setAttribute("data-lucide", isDark ? "sun" : "moon");
    lucide.createIcons();
  }
}

// Chequeo de estado de Docker
async function checkDockerStatus() {
  const badge = document.getElementById("docker-status");
  try {
    const res = await fetch("/api/status");
    const data = await res.json();
    if (data.docker) {
      badge.innerHTML = `<span class="w-2 h-2 rounded-full bg-emerald-400"></span><span class="text-emerald-600 dark:text-emerald-300 font-medium">Docker Activo</span>`;
    } else {
      badge.innerHTML = `<span class="w-2 h-2 rounded-full bg-rose-500"></span><span class="text-rose-600 dark:text-rose-300 font-semibold">Docker Desconectado</span>`;
    }
  } catch {
    badge.innerHTML = `<span class="w-2 h-2 rounded-full bg-rose-500"></span><span class="text-rose-600 dark:text-rose-300">Sin conexión</span>`;
  }
}

// ==========================================
// SISTEMA DE NOTIFICACIONES (TOASTS + BROWSER + AUDIO)
// ==========================================

class NotificationManager {
  constructor() {
    this.container = document.getElementById("toast-container");
    this.soundEnabled = localStorage.getItem("mediabox_sound") !== "false";
    
    // Si el usuario ya había otorgado permisos previamente, activar por defecto
    const savedNotif = localStorage.getItem("mediabox_browser_notif");
    if (savedNotif !== null) {
      this.browserNotifEnabled = savedNotif === "true";
    } else {
      this.browserNotifEnabled = typeof Notification !== "undefined" && Notification.permission === "granted";
    }

    this.updateButtonState();
  }

  updateButtonState() {
    const icon = document.getElementById("notif-icon");
    const badge = document.getElementById("notif-badge");
    if (!icon) return;

    const isGranted = typeof Notification !== "undefined" && Notification.permission === "granted";
    if (this.browserNotifEnabled && isGranted) {
      icon.setAttribute("data-lucide", "bell");
      if (badge) badge.classList.remove("hidden");
    } else {
      icon.setAttribute("data-lucide", "bell-off");
      if (badge) badge.classList.add("hidden");
    }
    lucide.createIcons();
  }

  async toggle() {
    if (!("Notification" in window)) {
      this.toast("info", "Notificaciones de escritorio", "Tu navegador no soporta la API de notificaciones nativas, pero los avisos visuales en pantalla están activos.");
      return;
    }

    if (Notification.permission === "default") {
      try {
        const perm = await Notification.requestPermission();
        if (perm === "granted") {
          this.browserNotifEnabled = true;
          localStorage.setItem("mediabox_browser_notif", "true");
          this.playChime(true);
          this.toast("success", "Notificaciones activadas", "Te avisaremos cuando tus conversiones terminen, incluso si cambias de pestaña.");
          this.notifySystem("MediaBox", "¡Las notificaciones del sistema están listas!");
        } else {
          this.browserNotifEnabled = false;
          localStorage.setItem("mediabox_browser_notif", "false");
          this.toast("warning", "Permiso no concedido", "Puedes habilitar las notificaciones cuando desees desde los permisos del navegador.");
        }
      } catch (err) {
        console.error("Error solicitando permisos de notificación:", err);
      }
    } else if (Notification.permission === "granted") {
      this.browserNotifEnabled = !this.browserNotifEnabled;
      localStorage.setItem("mediabox_browser_notif", this.browserNotifEnabled ? "true" : "false");
      if (this.browserNotifEnabled) {
        this.playChime(true);
        this.toast("success", "Notificaciones activadas", "Avisos de escritorio habilitados.");
      } else {
        this.toast("info", "Notificaciones en pausa", "Avisos de escritorio pausados temporalmente.");
      }
    } else {
      this.toast("warning", "Permiso bloqueado", "Las notificaciones están bloqueadas en tu navegador. Puedes desbloquearlas haciendo clic en el icono del candado en la barra de direcciones.");
    }
    this.updateButtonState();
  }

  // Sintetizador de audio sutil con Web Audio API (cero dependencias externas)
  playChime(isSuccess = true) {
    if (!this.soundEnabled) return;
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtx) return;
      const ctx = new AudioCtx();

      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);

      const now = ctx.currentTime;
      if (isSuccess) {
        // Tono doble ascendente agradable (D5 -> A5)
        osc.type = "sine";
        osc.frequency.setValueAtTime(587.33, now);
        osc.frequency.exponentialRampToValueAtTime(880, now + 0.12);
        gain.gain.setValueAtTime(0.001, now);
        gain.gain.linearRampToValueAtTime(0.15, now + 0.04);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.35);
        osc.start(now);
        osc.stop(now + 0.38);
      } else {
        // Tono suave descendente para advertencias
        osc.type = "triangle";
        osc.frequency.setValueAtTime(330, now);
        osc.frequency.exponentialRampToValueAtTime(220, now + 0.18);
        gain.gain.setValueAtTime(0.001, now);
        gain.gain.linearRampToValueAtTime(0.12, now + 0.03);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.3);
        osc.start(now);
        osc.stop(now + 0.35);
      }
    } catch {
      // Ignorar bloqueos de autoplay de audio
    }
  }

  // Notificación del sistema operativo / navegador
  notifySystem(title, body, url = null) {
    if (!this.browserNotifEnabled || !("Notification" in window) || Notification.permission !== "granted") {
      return;
    }
    try {
      const notif = new Notification(title, {
        body,
        icon: "/static/icon.svg",
        badge: "/static/icon.svg",
      });
      notif.onclick = () => {
        window.focus();
        if (url) window.location.href = url;
        notif.close();
      };
    } catch (e) {
      console.warn("No se pudo emitir la notificación del sistema:", e);
    }
  }

  // Toast flotante interactivo y animado
  toast(type, title, message, action = null) {
    if (!this.container) {
      this.container = document.getElementById("toast-container");
      if (!this.container) return;
    }

    const toast = document.createElement("div");
    toast.className = "pointer-events-auto transform translate-y-3 opacity-0 transition-all duration-300 ease-out flex items-start gap-3 p-4 rounded-2xl shadow-2xl border bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-800 text-slate-800 dark:text-slate-100 max-w-sm w-full backdrop-blur-md";

    let iconHtml = '<i data-lucide="info" class="w-5 h-5 text-indigo-500 flex-shrink-0 mt-0.5"></i>';
    if (type === "success") {
      iconHtml = '<i data-lucide="check-circle-2" class="w-5 h-5 text-emerald-500 flex-shrink-0 mt-0.5"></i>';
      toast.classList.add("border-emerald-500/30", "dark:border-emerald-500/20");
    } else if (type === "error") {
      iconHtml = '<i data-lucide="alert-circle" class="w-5 h-5 text-rose-500 flex-shrink-0 mt-0.5"></i>';
      toast.classList.add("border-rose-500/30", "dark:border-rose-500/20");
    } else if (type === "warning") {
      iconHtml = '<i data-lucide="alert-triangle" class="w-5 h-5 text-amber-500 flex-shrink-0 mt-0.5"></i>';
      toast.classList.add("border-amber-500/30", "dark:border-amber-500/20");
    }

    let actionHtml = "";
    if (action && action.label && action.url) {
      actionHtml = `
        <div class="mt-2.5 flex items-center gap-2">
          <a href="${action.url}" ${action.download ? `download="${action.download}"` : ""} class="inline-flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-xs font-semibold shadow-md shadow-indigo-600/20 transition">
            <i data-lucide="download" class="w-3.5 h-3.5"></i> ${action.label}
          </a>
        </div>
      `;
    }

    toast.innerHTML = `
      ${iconHtml}
      <div class="flex-1 min-w-0">
        <h5 class="text-sm font-bold text-slate-900 dark:text-white leading-tight">${title}</h5>
        <p class="text-xs text-slate-500 dark:text-slate-400 mt-1 leading-snug">${message}</p>
        ${actionHtml}
      </div>
      <button class="toast-close text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 p-1 rounded-lg transition" title="Cerrar aviso">
        <i data-lucide="x" class="w-3.5 h-3.5"></i>
      </button>
    `;

    this.container.appendChild(toast);
    lucide.createIcons();

    // Transición de entrada
    requestAnimationFrame(() => {
      toast.classList.remove("translate-y-3", "opacity-0");
    });

    const removeToast = () => {
      toast.classList.add("opacity-0", "translate-x-6");
      setTimeout(() => {
        if (toast.parentNode) toast.parentNode.removeChild(toast);
      }, 300);
    };

    const closeBtn = toast.querySelector(".toast-close");
    if (closeBtn) closeBtn.addEventListener("click", removeToast);

    // Auto-cierre tras 5.5 segundos
    setTimeout(removeToast, 5500);
  }

  onTaskCompleted(filename, message, downloadUrl) {
    this.playChime(true);
    const shortMsg = message || filename || "Archivo procesado";
    this.notifySystem("🎉 ¡Tarea completada!", shortMsg, downloadUrl);
    this.toast("success", "¡Proceso terminado!", shortMsg, {
      label: "Descargar",
      url: downloadUrl,
      download: filename,
    });
  }

  onTaskFailed(message) {
    this.playChime(false);
    this.notifySystem("❌ Error en la tarea", message || "Hubo un fallo en el procesamiento");
    this.toast("error", "Error en el proceso", message || "No se pudo completar la tarea.");
  }
}

function toggleNotifications() {
  if (notifManager) notifManager.toggle();
}

// Navegación entre pestañas principales
function switchTab(tabId) {
  document.querySelectorAll(".tab-panel").forEach(p => p.classList.add("hidden"));
  document.querySelectorAll(".tab-btn").forEach(b => {
    b.classList.remove("bg-indigo-600", "text-white", "shadow-lg", "shadow-indigo-600/20");
    b.classList.add("text-slate-500", "dark:text-slate-400");
  });

  const activePanel = document.getElementById(`panel-${tabId}`);
  const activeBtn = document.getElementById(`tab-${tabId}`);
  if (activePanel && activeBtn) {
    activePanel.classList.remove("hidden");
    activeBtn.classList.remove("text-slate-500", "dark:text-slate-400");
    activeBtn.classList.add("bg-indigo-600", "text-white", "shadow-lg", "shadow-indigo-600/20");
  }
  if (tabId === "library") {
    loadLibrary();
    loadStorageInfo();
  }
  lucide.createIcons();
}

// Navegación en subpestañas de Audio
function switchAudioSubtab(subId) {
  document.querySelectorAll(".apanel").forEach(p => p.classList.add("hidden"));
  document.querySelectorAll(".asub-btn").forEach(b => {
    b.classList.remove("bg-indigo-600/10", "dark:bg-indigo-600/20", "text-indigo-600", "dark:text-indigo-400", "border", "border-indigo-500/20", "dark:border-indigo-500/30");
    b.classList.add("text-slate-500", "dark:text-slate-400");
  });

  const activePanel = document.getElementById(`apanel-${subId}`);
  const activeBtn = document.getElementById(`asub-${subId}`);
  if (activePanel && activeBtn) {
    activePanel.classList.remove("hidden");
    activeBtn.classList.remove("text-slate-500", "dark:text-slate-400");
    activeBtn.classList.add("bg-indigo-600/10", "dark:bg-indigo-600/20", "text-indigo-600", "dark:text-indigo-400", "border", "border-indigo-500/20", "dark:border-indigo-500/30");
  }
  lucide.createIcons();
}

function setAudioSpeedPreset(speed) {
  const input = document.getElementById("audio-speed-val");
  if (input) input.value = speed;
}

// Navegación en subpestañas de Video
function switchVideoSubtab(subId) {
  document.querySelectorAll(".vpanel").forEach(p => p.classList.add("hidden"));
  document.querySelectorAll(".vsub-btn").forEach(b => {
    b.classList.remove("bg-indigo-600/10", "dark:bg-indigo-600/20", "text-indigo-600", "dark:text-indigo-400", "border", "border-indigo-500/20", "dark:border-indigo-500/30");
    b.classList.add("text-slate-500", "dark:text-slate-400");
  });

  const activeVpanel = document.getElementById(`vpanel-${subId}`);
  const activeVbtn = document.getElementById(`vsub-${subId}`);
  if (activeVpanel && activeVbtn) {
    activeVpanel.classList.remove("hidden");
    activeVbtn.classList.remove("text-slate-500", "dark:text-slate-400");
    activeVbtn.classList.add("bg-indigo-600/10", "dark:bg-indigo-600/20", "text-indigo-600", "dark:text-indigo-400", "border", "border-indigo-500/20", "dark:border-indigo-500/30");
  }
  lucide.createIcons();
}

// Navegación en subpestañas de Imagen
function switchImageSubtab(subId) {
  document.querySelectorAll(".ipanel").forEach(p => p.classList.add("hidden"));
  document.querySelectorAll(".isub-btn").forEach(b => {
    b.classList.remove("bg-indigo-600/10", "dark:bg-indigo-600/20", "text-indigo-600", "dark:text-indigo-400", "border", "border-indigo-500/20", "dark:border-indigo-500/30");
    b.classList.add("text-slate-500", "dark:text-slate-400");
  });

  const activePanel = document.getElementById(`ipanel-${subId}`);
  const activeBtn = document.getElementById(`isub-${subId}`);
  if (activePanel && activeBtn) {
    activePanel.classList.remove("hidden");
    activeBtn.classList.remove("text-slate-500", "dark:text-slate-400");
    activeBtn.classList.add("bg-indigo-600/10", "dark:bg-indigo-600/20", "text-indigo-600", "dark:text-indigo-400", "border", "border-indigo-500/20", "dark:border-indigo-500/30");
  }
  lucide.createIcons();
}

// Alternar entre extraer / quemar subtítulos
function switchSubtitleMode(mode) {
  document.getElementById("submode-panel-extract").classList.toggle("hidden", mode !== "extract");
  document.getElementById("submode-panel-burn").classList.toggle("hidden", mode !== "burn");
  document.querySelectorAll(".submode-btn").forEach(b => {
    b.classList.remove("bg-indigo-600/10", "dark:bg-indigo-600/20", "text-indigo-600", "dark:text-indigo-400", "border", "border-indigo-500/20");
    b.classList.add("text-slate-500", "dark:text-slate-400");
  });
  const activeBtn = document.getElementById(`submode-${mode}`);
  if (activeBtn) {
    activeBtn.classList.remove("text-slate-500", "dark:text-slate-400");
    activeBtn.classList.add("bg-indigo-600/10", "dark:bg-indigo-600/20", "text-indigo-600", "dark:text-indigo-400", "border", "border-indigo-500/20");
  }
  lucide.createIcons();
}

// Navegación en subpestañas de PDF
function switchPdfSubtab(subId) {
  document.querySelectorAll(".pdfpanel").forEach(p => p.classList.add("hidden"));
  document.querySelectorAll(".pdfsub-btn").forEach(b => {
    b.classList.remove("bg-indigo-600/10", "dark:bg-indigo-600/20", "text-indigo-600", "dark:text-indigo-400", "border", "border-indigo-500/20", "dark:border-indigo-500/30");
    b.classList.add("text-slate-500", "dark:text-slate-400");
  });

  const activePdfPanel = document.getElementById(`pdfpanel-${subId}`);
  const activePdfBtn = document.getElementById(`pdfsub-${subId}`);
  if (activePdfPanel && activePdfBtn) {
    activePdfPanel.classList.remove("hidden");
    activePdfBtn.classList.remove("text-slate-500", "dark:text-slate-400");
    activePdfBtn.classList.add("bg-indigo-600/10", "dark:bg-indigo-600/20", "text-indigo-600", "dark:text-indigo-400", "border", "border-indigo-500/20", "dark:border-indigo-500/30");
  }
  lucide.createIcons();
}

// Presets rápidos para compresión
function setCompressPreset(preset) {
  const select = document.getElementById("compress-profile");
  if (select) {
    select.value = preset;
    select.classList.add("ring-2", "ring-indigo-500");
    setTimeout(() => select.classList.remove("ring-2", "ring-indigo-500"), 500);
  }
}

// GESTIÓN UNIVERSAL DE DROPZONES
function initDropzones() {
  setupMultipleDropzone("dropzone-audio", "file-audio", "selected-audio", "preview-audio", "audio");
  setupDropzone("dropzone-audio-speed", "file-audio-speed", "selected-audio-speed", "preview-audio-speed", "audio");
  setupMultipleDropzone("dropzone-video", "file-video", "selected-video", "preview-video", "video");
  setupDropzone("dropzone-book", "file-book", "selected-book", "preview-book", "book");
  setupMultipleDropzone("dropzone-image", "file-image", "selected-image", "preview-image", "image");
  setupMultipleDropzone("dropzone-pdf", "files-pdf", "selected-pdfs", "preview-pdf", "pdf");
  setupMultipleDropzone("dropzone-pdf-compress", "file-pdf-compress", "selected-pdf-compress", "preview-pdf-compress", "pdf");
  setupDropzone("dropzone-pdf-ocr", "file-pdf-ocr", "selected-pdf-ocr", "preview-pdf-ocr", "pdf");
  setupDropzone("dropzone-pdf-extract", "file-pdf-extract", "selected-pdf-extract", "preview-pdf-extract", "pdf");
  setupDropzone("dropzone-pdf-images", "file-pdf-images", "selected-pdf-images", "preview-pdf-images", "pdf");
  setupMultipleDropzone("dropzone-privacy", "file-privacy", "selected-privacy", "preview-privacy", "privacy");
  setupMultipleDropzone("dropzone-cmyk", "file-cmyk", "selected-cmyk", "preview-cmyk", "cmyk");
  setupDropzone("dropzone-pdf-rotate", "file-pdf-rotate", "selected-pdf-rotate", "preview-pdf-rotate", "pdf");
  setupDropzone("dropzone-pdf-protect", "file-pdf-protect", "selected-pdf-protect", "preview-pdf-protect", "pdf");
  setupDropzone("dropzone-pdf-office", "file-pdf-office", "selected-pdf-office", "preview-pdf-office", "file");
}

function setupDropzone(zoneId, inputId, labelId, previewId, type) {
  const zone = document.getElementById(zoneId);
  const input = document.getElementById(inputId);
  const label = document.getElementById(labelId);
  if (!zone || !input) return;

  zone.addEventListener("click", (e) => {
    if (e.target.tagName !== "INPUT" && e.target.tagName !== "VIDEO" && e.target.tagName !== "AUDIO") {
      input.click();
    }
  });
  zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("dropzone-active"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("dropzone-active"));
  zone.addEventListener("drop", (e) => {
    e.preventDefault();
    zone.classList.remove("dropzone-active");
    if (e.dataTransfer.files.length) {
      input.files = e.dataTransfer.files;
      updateFileBadge(input.files[0], label);
      renderPreProcessingPreview(input.files, previewId, type);
    }
  });

  input.addEventListener("change", () => {
    if (input.files.length) {
      updateFileBadge(input.files[0], label);
      renderPreProcessingPreview(input.files, previewId, type);
    }
  });
}

function setupMultipleDropzone(zoneId, inputId, containerId, previewId, type) {
  const zone = document.getElementById(zoneId);
  const input = document.getElementById(inputId);
  const container = document.getElementById(containerId);
  if (!zone || !input) return;

  zone.addEventListener("click", (e) => {
    if (e.target.tagName !== "INPUT" && e.target.tagName !== "VIDEO" && e.target.tagName !== "AUDIO") {
      input.click();
    }
  });
  zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("dropzone-active"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("dropzone-active"));
  zone.addEventListener("drop", (e) => {
    e.preventDefault();
    zone.classList.remove("dropzone-active");
    if (e.dataTransfer.files.length) {
      input.files = e.dataTransfer.files;
      renderMultipleBadges(input.files, container);
      renderPreProcessingPreview(input.files, previewId, type);
    }
  });

  input.addEventListener("change", () => {
    if (input.files.length) {
      renderMultipleBadges(input.files, container);
      renderPreProcessingPreview(input.files, previewId, type);
    }
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

  if (files.length > 3) {
    const totalMb = (Array.from(files).reduce((acc, f) => acc + f.size, 0) / (1024 * 1024)).toFixed(1);
    const summaryBadge = document.createElement("span");
    summaryBadge.className = "inline-flex items-center gap-1.5 bg-indigo-500/10 border border-indigo-500/20 text-indigo-600 dark:text-indigo-300 text-xs px-3 py-1 rounded-lg font-semibold";
    summaryBadge.innerHTML = `<i data-lucide="layers" class="w-3.5 h-3.5"></i> Lote: ${files.length} archivos (${totalMb} MB total)`;
    container.appendChild(summaryBadge);
  } else {
    Array.from(files).forEach(f => {
      const badge = document.createElement("span");
      badge.className = "inline-flex items-center gap-1.5 bg-indigo-500/10 border border-indigo-500/20 text-indigo-600 dark:text-indigo-300 text-xs px-2.5 py-1 rounded-lg";
      badge.innerHTML = `<i data-lucide="file" class="w-3 h-3"></i> ${f.name}`;
      container.appendChild(badge);
    });
  }
  lucide.createIcons();
}

// VISTA PREVIA INTERACTIVA PRE-PROCESAMIENTO
function renderPreProcessingPreview(files, previewId, type) {
  if (!previewId) return;
  const previewBox = document.getElementById(previewId);
  if (!previewBox) return;

  if (!files || !files.length) {
    previewBox.innerHTML = "";
    previewBox.classList.add("hidden");
    return;
  }

  const file = files[0];
  const isMultiple = files.length > 1;
  const ext = file.name.split(".").pop().toLowerCase();
  previewBox.classList.remove("hidden");

  if (type === "image") {
    if (ext === "heic" || ext === "heif") {
      previewBox.innerHTML = `
        <div class="p-3 bg-indigo-50 dark:bg-indigo-950/50 border border-indigo-200 dark:border-indigo-800 rounded-xl text-center shadow-sm">
          <div class="flex items-center justify-center gap-2 text-indigo-600 dark:text-indigo-400 font-semibold text-xs mb-1">
            <i data-lucide="apple" class="w-4 h-4"></i> Formato Apple HEIC detectado
          </div>
          <p class="text-xs text-slate-500 dark:text-slate-400">Listo para decodificar y convertir a formato universal (${(file.size / (1024 * 1024)).toFixed(2)} MB)${isMultiple ? ` + ${files.length - 1} imágenes más` : ''}</p>
        </div>
      `;
    } else {
      const blobUrl = URL.createObjectURL(file);
      previewBox.innerHTML = `
        <div class="relative group">
          <img src="${blobUrl}" class="max-h-40 mx-auto rounded-xl shadow-md border border-slate-200 dark:border-slate-800 object-contain">
          ${isMultiple ? `<span class="mt-1 block text-center text-xs text-slate-400 font-medium">+ ${files.length - 1} fotos más en lote</span>` : ''}
        </div>
      `;
    }
  } else if (type === "video") {
    const blobUrl = URL.createObjectURL(file);
    previewBox.innerHTML = `
      <div class="space-y-1">
        <video src="${blobUrl}" controls class="max-h-44 w-full rounded-xl shadow-md bg-black mx-auto"></video>
        ${isMultiple ? `<span class="block text-center text-xs text-slate-400 font-medium">+ ${files.length - 1} videos más</span>` : ''}
      </div>
    `;
  } else if (type === "audio") {
    const blobUrl = URL.createObjectURL(file);
    if (file.type.startsWith("video/") || ["mp4", "mkv", "mov", "webm", "avi"].includes(ext)) {
      previewBox.innerHTML = `
        <video src="${blobUrl}" controls class="max-h-36 w-full rounded-xl shadow-md bg-black mx-auto"></video>
      `;
    } else {
      previewBox.innerHTML = `
        <audio src="${blobUrl}" controls class="w-full mt-2 rounded-lg"></audio>
      `;
    }
  } else if (type === "privacy") {
    if (["jpg", "jpeg", "png", "webp", "tiff", "heic"].includes(ext)) {
      if (ext === "heic" || ext === "heif") {
        previewBox.innerHTML = `
          <div class="p-3 bg-slate-100 dark:bg-slate-800 rounded-xl text-center text-xs text-slate-600 dark:text-slate-300">
            🍏 Imagen Apple HEIC: ${file.name} (${(file.size / (1024 * 1024)).toFixed(2)} MB)
          </div>
        `;
      } else {
        const blobUrl = URL.createObjectURL(file);
        previewBox.innerHTML = `
          <img src="${blobUrl}" class="max-h-36 mx-auto rounded-xl shadow-md border border-slate-200 dark:border-slate-800 object-contain">
        `;
      }
    } else {
      previewBox.innerHTML = `
        <div class="p-3 bg-slate-100 dark:bg-slate-800 rounded-xl text-center text-xs font-mono text-slate-600 dark:text-slate-300 flex items-center justify-center gap-2">
          <i data-lucide="file-text" class="w-4 h-4 text-emerald-500"></i> ${file.name} (${(file.size / (1024 * 1024)).toFixed(2)} MB)
        </div>
      `;
    }
  } else if (type === "pdf") {
    previewBox.innerHTML = `
      <div class="p-2.5 bg-indigo-50 dark:bg-indigo-950/40 border border-indigo-200 dark:border-indigo-800 rounded-xl text-center text-xs text-indigo-700 dark:text-indigo-300 flex items-center justify-center gap-2 font-medium">
        <i data-lucide="file-text" class="w-4 h-4"></i> ${file.name} (${(file.size / (1024 * 1024)).toFixed(2)} MB)${isMultiple ? ` + ${files.length - 1} PDFs` : ''}
      </div>
    `;
  } else if (type === "cmyk") {
    if (ext === "svg") {
      const blobUrl = URL.createObjectURL(file);
      previewBox.innerHTML = `
        <div class="p-3 bg-cyan-50 dark:bg-cyan-950/40 border border-cyan-300 dark:border-cyan-800 rounded-xl text-center shadow-sm">
          <img src="${blobUrl}" class="max-h-40 mx-auto rounded-lg shadow-sm border border-slate-200 dark:border-slate-700 bg-white p-2 object-contain">
          <span class="mt-2 inline-flex items-center gap-1 text-xs font-semibold text-cyan-600 dark:text-cyan-400">
            <i data-lucide="palette" class="w-3.5 h-3.5"></i> Vector Inkscape SVG (${(file.size / 1024).toFixed(1)} KB)${isMultiple ? ` + ${files.length - 1} archivos` : ''}
          </span>
        </div>
      `;
    } else if (ext === "pdf") {
      previewBox.innerHTML = `
        <div class="p-3 bg-cyan-50 dark:bg-cyan-950/40 border border-cyan-300 dark:border-cyan-800 rounded-xl text-center text-xs text-cyan-700 dark:text-cyan-300 flex items-center justify-center gap-2 font-medium">
          <i data-lucide="file-text" class="w-4 h-4 text-cyan-500"></i> ${file.name} (${(file.size / (1024 * 1024)).toFixed(2)} MB)${isMultiple ? ` + ${files.length - 1} archivos` : ''}
        </div>
      `;
    } else {
      const blobUrl = URL.createObjectURL(file);
      previewBox.innerHTML = `
        <img src="${blobUrl}" class="max-h-36 mx-auto rounded-xl shadow-md border border-slate-200 dark:border-slate-800 object-contain">
      `;
    }
  }
  lucide.createIcons();
}

// SEGUIMIENTO VISUAL DE TAREAS INDIVIDUALES
function startTaskMonitoring(taskId, previewType = "generic") {
  const box = document.getElementById("task-feedback");
  const msg = document.getElementById("task-message");
  const percent = document.getElementById("task-percent");
  const bar = document.getElementById("task-bar");
  const resultBox = document.getElementById("result-box");
  const previewContainer = document.getElementById("preview-container");
  const downloadLink = document.getElementById("download-link");
  const batchZipLink = document.getElementById("batch-zip-link");

  box.classList.remove("hidden");
  resultBox.classList.add("hidden");
  batchZipLink.classList.add("hidden");
  downloadLink.classList.remove("hidden");
  previewContainer.innerHTML = "";
  bar.className = "h-full bg-indigo-600 rounded-full transition-all duration-300";

  if (!taskId || taskId === "undefined" || taskId === "null") {
    bar.style.width = "100%";
    bar.className = "h-full bg-rose-500 rounded-full transition-all duration-300";
    percent.innerText = "Error";
    msg.innerHTML = `<i data-lucide="alert-circle" class="w-4 h-4 text-rose-500"></i> No se pudo iniciar la tarea en el servidor.`;
    lucide.createIcons();
    return;
  }

  bar.style.width = "5%";
  percent.innerText = "5%";
  msg.innerHTML = `<i data-lucide="loader" class="w-4 h-4 animate-spin text-indigo-500"></i> Iniciando contenedor...`;
  lucide.createIcons();
  if (notifManager) notifManager.toast("info", "Tarea en cola", "Iniciando contenedor para procesar archivo...");

  const interval = setInterval(async () => {
    try {
      const res = await fetch(`/api/tasks/${taskId}`);
      if (!res.ok) {
        clearInterval(interval);
        bar.style.width = "100%";
        bar.className = "h-full bg-rose-500 rounded-full transition-all duration-300";
        percent.innerText = "Error";
        msg.innerHTML = `<i data-lucide="alert-circle" class="w-4 h-4 text-rose-500"></i> Error HTTP ${res.status}: Tarea no encontrada o falló el servidor.`;
        lucide.createIcons();
        if (notifManager) notifManager.onTaskFailed(`Error HTTP ${res.status}`);
        return;
      }
      const data = await res.json();

      if (data.status === "running") {
        const pct = data.progress || 25;
        bar.style.width = `${pct}%`;
        percent.innerText = `${pct}%`;
        msg.innerHTML = `<i data-lucide="loader" class="w-4 h-4 animate-spin text-indigo-500"></i> ${data.message}`;
        lucide.createIcons();
      } else if (data.status === "done") {
        clearInterval(interval);
        bar.style.width = "100%";
        percent.innerText = "100%";
        msg.innerHTML = `<i data-lucide="check" class="w-4 h-4 text-emerald-500"></i> ${data.message}`;
        downloadLink.href = data.download_url;
        downloadLink.setAttribute("download", data.filename);

        if (data.preview_url) {
          if (previewType === "audio") {
            previewContainer.innerHTML = `<audio controls class="w-full mt-2 rounded-xl" src="${data.preview_url}"></audio>`;
          } else if (previewType === "image" || previewType === "gif") {
            previewContainer.innerHTML = `<img src="${data.preview_url}" class="max-h-64 mx-auto rounded-xl border border-slate-300 dark:border-slate-700 shadow-lg object-contain">`;
          }
        }

        resultBox.classList.remove("hidden");
        lucide.createIcons();
        loadStorageInfo();
        if (notifManager) notifManager.onTaskCompleted(data.filename, data.message, data.download_url);
      } else if (data.status === "error") {
        clearInterval(interval);
        bar.style.width = "100%";
        bar.className = "h-full bg-rose-500 rounded-full transition-all duration-300";
        percent.innerText = "Error";
        msg.innerHTML = `<i data-lucide="alert-circle" class="w-4 h-4 text-rose-500"></i> Falló: ${data.message}`;
        lucide.createIcons();
        if (notifManager) notifManager.onTaskFailed(data.message);
      }
    } catch {
      clearInterval(interval);
      bar.style.width = "100%";
      bar.className = "h-full bg-rose-500 rounded-full transition-all duration-300";
      percent.innerText = "Error";
      msg.innerHTML = `<i data-lucide="alert-circle" class="w-4 h-4 text-rose-500"></i> Error de conexión con el backend.`;
      lucide.createIcons();
      if (notifManager) notifManager.onTaskFailed("Error de conexión con el backend");
    }
  }, 600);
}

// SEGUIMIENTO VISUAL DE LOTES (BATCH)
function startBatchMonitoring(batchId) {
  const box = document.getElementById("task-feedback");
  const msg = document.getElementById("task-message");
  const percent = document.getElementById("task-percent");
  const bar = document.getElementById("task-bar");
  const resultBox = document.getElementById("result-box");
  const previewContainer = document.getElementById("preview-container");
  const downloadLink = document.getElementById("download-link");
  const batchZipLink = document.getElementById("batch-zip-link");

  box.classList.remove("hidden");
  resultBox.classList.add("hidden");
  downloadLink.classList.add("hidden");
  batchZipLink.classList.remove("hidden");
  previewContainer.innerHTML = "";
  bar.className = "h-full bg-indigo-600 rounded-full transition-all duration-300";

  if (!batchId || batchId === "undefined" || batchId === "null") {
    bar.style.width = "100%";
    bar.className = "h-full bg-rose-500 rounded-full transition-all duration-300";
    percent.innerText = "Error";
    msg.innerHTML = `<i data-lucide="alert-circle" class="w-4 h-4 text-rose-500"></i> No se pudo iniciar el lote en el servidor.`;
    lucide.createIcons();
    return;
  }

  bar.style.width = "5%";
  percent.innerText = "5%";
  msg.innerHTML = `<i data-lucide="loader" class="w-4 h-4 animate-spin text-indigo-500"></i> Procesando lote...`;
  lucide.createIcons();
  if (notifManager) notifManager.toast("info", "Lote iniciado", "Procesando lote de archivos en segundo plano...");

  const interval = setInterval(async () => {
    try {
      const res = await fetch(`/api/batch/${batchId}`);
      if (!res.ok) {
        clearInterval(interval);
        bar.style.width = "100%";
        bar.className = "h-full bg-rose-500 rounded-full transition-all duration-300";
        percent.innerText = "Error";
        msg.innerHTML = `<i data-lucide="alert-circle" class="w-4 h-4 text-rose-500"></i> Error HTTP ${res.status}: Lote no encontrado o falló el servidor.`;
        lucide.createIcons();
        if (notifManager) notifManager.onTaskFailed(`Error HTTP ${res.status}`);
        return;
      }
      const data = await res.json();

      bar.style.width = `${data.percent}%`;
      percent.innerText = `${data.percent}%`;
      msg.innerHTML = `<i data-lucide="loader" class="w-4 h-4 animate-spin text-indigo-500"></i> Lote: ${data.completed} de ${data.total} procesados (${data.percent}%)`;
      lucide.createIcons();

      if (data.status === "done") {
        clearInterval(interval);
        bar.style.width = "100%";
        percent.innerText = "100%";
        msg.innerHTML = `<i data-lucide="check-check" class="w-4 h-4 text-emerald-500"></i> ¡Lote de ${data.total} archivos completado!`;
        batchZipLink.href = data.download_zip;
        batchZipLink.setAttribute("download", `mediabox_lote_${batchId.slice(0, 8)}.zip`);
        resultBox.classList.remove("hidden");
        lucide.createIcons();
        loadStorageInfo();
        if (notifManager) {
          notifManager.onTaskCompleted(
            `mediabox_lote_${batchId.slice(0, 8)}.zip`,
            `¡Lote de ${data.total} archivos completado!`,
            data.download_zip
          );
        }
      }
    } catch {
      clearInterval(interval);
      bar.style.width = "100%";
      bar.className = "h-full bg-rose-500 rounded-full transition-all duration-300";
      percent.innerText = "Error";
      msg.innerHTML = `<i data-lucide="alert-circle" class="w-4 h-4 text-rose-500"></i> Error de conexión con el backend.`;
      lucide.createIcons();
      if (notifManager) notifManager.onTaskFailed("Error de conexión con el backend");
    }
  }, 800);
}

// ACCIONES DE PROCESAMIENTO

async function processAudio() {
  const input = document.getElementById("file-audio");
  const files = input.files;
  if (!files || !files.length) return alert("Por favor selecciona o arrastra al menos un video.");

  const formato = document.getElementById("format-audio").value;
  const normalizar = document.getElementById("audio-normalize").checked;

  if (files.length > 1) {
    // Procesamiento por lotes
    const formData = new FormData();
    formData.append("tipo", "audio");
    formData.append("formato", formato);
    formData.append("normalizar", normalizar);
    Array.from(files).forEach(f => formData.append("files", f));

    const res = await fetch("/api/batch/convert", { method: "POST", body: formData });
    const data = await res.json();
    startBatchMonitoring(data.batch_id);
  } else {
    // Archivo individual
    const formData = new FormData();
    formData.append("file", files[0]);
    formData.append("formato", formato);
    formData.append("normalizar", normalizar);

    const res = await fetch("/api/audio", { method: "POST", body: formData });
    const data = await res.json();
    startTaskMonitoring(data.task_id, "audio");
  }
}

async function processCompress() {
  const input = document.getElementById("file-video");
  const files = input.files;
  if (!files || !files.length) return alert("Por favor selecciona o arrastra al menos un video.");

  const perfil = document.getElementById("compress-profile").value;

  if (files.length > 1) {
    // Procesamiento por lotes
    const formData = new FormData();
    formData.append("tipo", "compress");
    formData.append("perfil", perfil);
    Array.from(files).forEach(f => formData.append("files", f));

    const res = await fetch("/api/batch/convert", { method: "POST", body: formData });
    const data = await res.json();
    startBatchMonitoring(data.batch_id);
  } else {
    // Archivo individual
    const formData = new FormData();
    formData.append("file", files[0]);
    formData.append("perfil", perfil);

    const res = await fetch("/api/compress", { method: "POST", body: formData });
    const data = await res.json();
    startTaskMonitoring(data.task_id, "video");
  }
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
  const input = document.getElementById("file-image");
  const files = input.files;
  if (!files || !files.length) return alert("Por favor selecciona o arrastra al menos una imagen.");

  const formato = document.getElementById("img-format").value;
  const calidad = document.getElementById("img-quality").value;
  const width = document.getElementById("img-width").value;

  if (files.length > 1) {
    // Procesamiento por lotes
    const formData = new FormData();
    formData.append("tipo", "image");
    formData.append("formato", formato);
    formData.append("calidad", calidad);
    Array.from(files).forEach(f => formData.append("files", f));

    const res = await fetch("/api/batch/convert", { method: "POST", body: formData });
    const data = await res.json();
    startBatchMonitoring(data.batch_id);
  } else {
    // Archivo individual
    const formData = new FormData();
    formData.append("file", files[0]);
    formData.append("formato", formato);
    formData.append("calidad", calidad);
    if (width) formData.append("ancho", width);

    const res = await fetch("/api/image", { method: "POST", body: formData });
    const data = await res.json();
    startTaskMonitoring(data.task_id, "image");
  }
}

// INSPECTOR DE ENLACES (YOUTUBE / YT-DLP)
let urlInspectTimeout = null;
function debounceInspectUrl() {
  clearTimeout(urlInspectTimeout);
  urlInspectTimeout = setTimeout(() => {
    inspectDownloadUrlNow();
  }, 900);
}

async function inspectDownloadUrlNow() {
  const url = document.getElementById("dl-url").value.trim();
  const previewBox = document.getElementById("dl-preview");
  if (!url || (!url.startsWith("http://") && !url.startsWith("https://"))) {
    previewBox.classList.add("hidden");
    return;
  }

  previewBox.classList.remove("hidden");
  previewBox.innerHTML = `<div class="flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400 py-2"><i data-lucide="loader" class="w-4 h-4 animate-spin text-indigo-500"></i> Analizando enlace con yt-dlp...</div>`;
  lucide.createIcons();

  try {
    const formData = new FormData();
    formData.append("url", url);
    const res = await fetch("/api/download/inspect", { method: "POST", body: formData });
    const data = await res.json();
    if (data.title && !data.error) {
      previewBox.innerHTML = `
        ${data.thumbnail ? `<img src="${data.thumbnail}" class="w-32 h-20 rounded-lg object-cover shadow border border-slate-200 dark:border-slate-700">` : `<div class="w-20 h-20 rounded-lg bg-slate-200 dark:bg-slate-800 flex items-center justify-center"><i data-lucide="video" class="w-8 h-8 text-slate-400"></i></div>`}
        <div class="flex-1 min-w-0">
          <h4 class="text-sm font-bold text-slate-800 dark:text-slate-100 truncate">${data.title}</h4>
          <p class="text-xs text-slate-500 dark:text-slate-400 mt-1 flex flex-wrap items-center gap-3">
            <span>👤 ${data.uploader || "Desconocido"}</span>
            ${data.duration_string ? `<span>⏱️ ${data.duration_string}</span>` : ""}
          </p>
        </div>
      `;
    } else {
      previewBox.innerHTML = `<span class="text-xs text-amber-500 flex items-center gap-1.5 py-1"><i data-lucide="alert-triangle" class="w-3.5 h-3.5"></i> Vista previa no disponible para este enlace, pero puedes descargarlo directamente.</span>`;
    }
  } catch {
    previewBox.classList.add("hidden");
  }
  lucide.createIcons();
}

// COMPRESIÓN DE PDF
async function processPdfCompress() {
  const input = document.getElementById("file-pdf-compress");
  const files = input.files;
  if (!files || !files.length) return alert("Por favor selecciona o arrastra al menos un archivo PDF.");

  const perfil = document.getElementById("pdf-compress-profile").value;

  try {
    if (files.length > 1) {
      const formData = new FormData();
      formData.append("tipo", "pdf_compress");
      formData.append("perfil", perfil);
      Array.from(files).forEach(f => formData.append("files", f));

      const res = await fetch("/api/batch/convert", { method: "POST", body: formData });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || `Error HTTP ${res.status}`);
      startBatchMonitoring(data.batch_id);
    } else {
      const formData = new FormData();
      formData.append("file", files[0]);
      formData.append("perfil", perfil);

      const res = await fetch("/api/pdf/compress", { method: "POST", body: formData });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || `Error HTTP ${res.status}`);
      startTaskMonitoring(data.task_id, "generic");
    }
  } catch (err) {
    alert(`Error al iniciar compresión PDF: ${err.message}`);
  }
}

// SEGURIDAD Y PRIVACIDAD DE METADATOS (MAT2)
async function inspectPrivacyMetadata() {
  const input = document.getElementById("file-privacy");
  const files = input.files;
  if (!files || !files.length) return alert("Por favor selecciona o arrastra un archivo primero.");

  const inspectBox = document.getElementById("privacy-inspect-box");
  const content = document.getElementById("privacy-inspect-content");
  const badge = document.getElementById("privacy-meta-badge");

  inspectBox.classList.remove("hidden");
  content.innerHTML = `<div class="flex items-center gap-2 py-2 text-slate-500"><i data-lucide="loader" class="w-4 h-4 animate-spin text-indigo-500"></i> Analizando metadatos con MAT2...</div>`;
  lucide.createIcons();

  const formData = new FormData();
  formData.append("file", files[0]);

  try {
    const res = await fetch("/api/privacy/inspect", { method: "POST", body: formData });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `Error HTTP ${res.status}`);
    const meta = data.metadata || {};
    const keys = Object.keys(meta);

    if (keys.length === 0) {
      badge.className = "text-xs font-semibold px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-500 border border-emerald-500/20";
      badge.textContent = "✅ Limpio / Sin metadatos";
      content.innerHTML = `<p class="text-emerald-500 py-2">No se detectaron metadatos sensibles ni rastros de privacidad en este archivo.</p>`;
    } else {
      badge.className = "text-xs font-semibold px-2.5 py-0.5 rounded-full bg-rose-500/10 text-rose-500 border border-rose-500/20";
      badge.textContent = `⚠️ ${keys.length} Metadatos detectados`;
      let html = `<div class="divide-y divide-slate-200 dark:divide-slate-800">`;
      for (const [k, v] of Object.entries(meta)) {
        html += `<div class="py-1 flex justify-between gap-4"><span class="font-bold text-slate-700 dark:text-slate-300">${k}:</span><span class="truncate max-w-xs text-slate-500">${v}</span></div>`;
      }
      html += `</div>`;
      content.innerHTML = html;
    }
  } catch (err) {
    content.innerHTML = `<p class="text-rose-500 py-2">Error al analizar metadatos: ${err.message}</p>`;
  }
  lucide.createIcons();
}

async function processPrivacyClean() {
  const input = document.getElementById("file-privacy");
  const files = input.files;
  if (!files || !files.length) return alert("Por favor selecciona o arrastra al menos un archivo.");

  try {
    if (files.length > 1) {
      const formData = new FormData();
      formData.append("tipo", "privacy");
      Array.from(files).forEach(f => formData.append("files", f));

      const res = await fetch("/api/batch/convert", { method: "POST", body: formData });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || `Error HTTP ${res.status}`);
      startBatchMonitoring(data.batch_id);
    } else {
      const formData = new FormData();
      formData.append("file", files[0]);

      const res = await fetch("/api/privacy/clean", { method: "POST", body: formData });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || `Error HTTP ${res.status}`);
      startTaskMonitoring(data.task_id, "generic");
    }
  } catch (err) {
    alert(`Error al limpiar metadatos: ${err.message}`);
  }
}

// PRENSA & EXPORTACIÓN CMYK (INKSCAPE / VECTORIAL / IMÁGENES)
async function processCmyk() {
  const input = document.getElementById("file-cmyk");
  const files = input.files;
  if (!files || !files.length) return alert("Por favor selecciona o arrastra al menos un diseño o archivo.");

  const formato = document.getElementById("cmyk-format").value;
  const perfil = document.getElementById("cmyk-profile").value;
  const dpi = document.getElementById("cmyk-dpi").value;

  try {
    if (files.length > 1) {
      const formData = new FormData();
      formData.append("tipo", "cmyk");
      formData.append("formato", formato);
      formData.append("perfil", perfil);
      Array.from(files).forEach(f => formData.append("files", f));

      const res = await fetch("/api/batch/convert", { method: "POST", body: formData });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || `Error HTTP ${res.status}`);
      startBatchMonitoring(data.batch_id);
    } else {
      const formData = new FormData();
      formData.append("file", files[0]);
      formData.append("formato", formato);
      formData.append("perfil", perfil);
      formData.append("dpi", dpi);

      const res = await fetch("/api/cmyk/convert", { method: "POST", body: formData });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || `Error HTTP ${res.status}`);
      startTaskMonitoring(data.task_id, formato === "jpg" ? "image" : "generic");
    }
  } catch (err) {
    alert(`Error al iniciar conversión CMYK: ${err.message}`);
  }
}

// ==========================================
// AJUSTE DE VELOCIDAD DE AUDIO (FFmpeg)
// ==========================================
async function processAudioSpeed() {
  const file = document.getElementById("file-audio-speed").files[0];
  if (!file) return alert("Por favor selecciona o arrastra un archivo de audio o video primero.");
  const velocidad = parseFloat(document.getElementById("audio-speed-val").value) || 1.5;

  const formData = new FormData();
  formData.append("file", file);
  formData.append("velocidad", velocidad);

  try {
    const res = await fetch("/api/audio/speed", { method: "POST", body: formData });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `Error HTTP ${res.status}`);
    startTaskMonitoring(data.task_id, "audio");
  } catch (err) {
    alert(`Error al cambiar velocidad de audio: ${err.message}`);
  }
}

// ==========================================
// HERRAMIENTAS AVANZADAS DE PDF (OCR, EXTRAER, IMÁGENES)
// ==========================================
async function processPdfOcr() {
  const file = document.getElementById("file-pdf-ocr").files[0];
  if (!file) return alert("Por favor selecciona o arrastra un archivo PDF para aplicar OCR.");
  const idioma = document.getElementById("pdf-ocr-lang").value || "spa+eng";

  const formData = new FormData();
  formData.append("file", file);
  formData.append("idioma", idioma);

  try {
    const res = await fetch("/api/pdf/ocr", { method: "POST", body: formData });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `Error HTTP ${res.status}`);
    startTaskMonitoring(data.task_id, "generic");
  } catch (err) {
    alert(`Error al iniciar OCR: ${err.message}`);
  }
}

async function processPdfExtract() {
  const file = document.getElementById("file-pdf-extract").files[0];
  if (!file) return alert("Por favor selecciona o arrastra un archivo PDF para extraer páginas.");
  const paginas = document.getElementById("pdf-extract-pages").value.trim() || "1";

  const formData = new FormData();
  formData.append("file", file);
  formData.append("paginas", paginas);

  try {
    const res = await fetch("/api/pdf/extract-pages", { method: "POST", body: formData });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `Error HTTP ${res.status}`);
    startTaskMonitoring(data.task_id, "generic");
  } catch (err) {
    alert(`Error al extraer páginas: ${err.message}`);
  }
}

async function processPdfToImages() {
  const file = document.getElementById("file-pdf-images").files[0];
  if (!file) return alert("Por favor selecciona o arrastra un archivo PDF para convertir a imágenes.");
  const formato = document.getElementById("pdf-images-format").value || "png";
  const dpi = parseInt(document.getElementById("pdf-images-dpi").value) || 300;

  const formData = new FormData();
  formData.append("file", file);
  formData.append("formato", formato);
  formData.append("dpi", dpi);

  try {
    const res = await fetch("/api/pdf/to-images", { method: "POST", body: formData });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `Error HTTP ${res.status}`);
    startTaskMonitoring(data.task_id, "generic");
  } catch (err) {
    alert(`Error al convertir PDF a imágenes: ${err.message}`);
  }
}

async function processPdfRotate() {
  const file = document.getElementById("file-pdf-rotate").files[0];
  if (!file) return alert("Por favor selecciona o arrastra un archivo PDF para rotar.");
  const angulo = document.getElementById("pdf-rotate-angle").value;
  const paginas = document.getElementById("pdf-rotate-pages").value.trim() || "1-z";

  const formData = new FormData();
  formData.append("file", file);
  formData.append("angulo", angulo);
  formData.append("paginas", paginas);

  try {
    const res = await fetch("/api/pdf/rotate", { method: "POST", body: formData });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `Error HTTP ${res.status}`);
    startTaskMonitoring(data.task_id, "generic");
  } catch (err) {
    alert(`Error al rotar el PDF: ${err.message}`);
  }
}

async function processPdfProtect() {
  const file = document.getElementById("file-pdf-protect").files[0];
  if (!file) return alert("Por favor selecciona o arrastra un archivo PDF para proteger.");
  const password = document.getElementById("pdf-protect-password").value;
  if (!password) return alert("Ingresa una contraseña para proteger el PDF.");

  const formData = new FormData();
  formData.append("file", file);
  formData.append("password", password);

  try {
    const res = await fetch("/api/pdf/protect", { method: "POST", body: formData });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `Error HTTP ${res.status}`);
    startTaskMonitoring(data.task_id, "generic");
  } catch (err) {
    alert(`Error al proteger el PDF: ${err.message}`);
  }
}

async function processOfficeToPdf() {
  const file = document.getElementById("file-pdf-office").files[0];
  if (!file) return alert("Por favor selecciona o arrastra un documento de oficina.");

  const formData = new FormData();
  formData.append("file", file);

  try {
    const res = await fetch("/api/pdf/from-office", { method: "POST", body: formData });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `Error HTTP ${res.status}`);
    startTaskMonitoring(data.task_id, "generic");
  } catch (err) {
    alert(`Error al convertir el documento a PDF: ${err.message}`);
  }
}

// ==========================================
// SUBTÍTULOS DE VIDEO (FFmpeg)
// ==========================================
async function processSubtitleExtract() {
  const file = document.getElementById("file-video").files[0];
  if (!file) return alert("Por favor selecciona o arrastra un video primero.");
  const pista = parseInt(document.getElementById("sub-track-index").value) || 0;

  const formData = new FormData();
  formData.append("file", file);
  formData.append("pista", pista);

  try {
    const res = await fetch("/api/subtitles/extract", { method: "POST", body: formData });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `Error HTTP ${res.status}`);
    startTaskMonitoring(data.task_id, "generic");
  } catch (err) {
    alert(`Error al extraer subtítulos: ${err.message}`);
  }
}

async function processSubtitleBurn() {
  const file = document.getElementById("file-video").files[0];
  if (!file) return alert("Por favor selecciona o arrastra un video primero.");
  const subtitleFile = document.getElementById("file-subtitle-track").files[0];
  if (!subtitleFile) return alert("Selecciona un archivo de subtítulos (.srt, .vtt o .ass).");

  const formData = new FormData();
  formData.append("file", file);
  formData.append("subtitle_file", subtitleFile);

  try {
    const res = await fetch("/api/subtitles/burn", { method: "POST", body: formData });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `Error HTTP ${res.status}`);
    startTaskMonitoring(data.task_id, "video");
  } catch (err) {
    alert(`Error al quemar subtítulos: ${err.message}`);
  }
}

// ==========================================
// MARCA DE AGUA (Imagen y Video)
// ==========================================
async function processImageWatermark() {
  const file = document.getElementById("file-image").files[0];
  if (!file) return alert("Por favor selecciona o arrastra una imagen primero.");
  const texto = document.getElementById("img-wm-text").value.trim();
  const logo = document.getElementById("img-wm-logo").files[0];
  if (!texto && !logo) return alert("Ingresa un texto o selecciona un logo para la marca de agua.");

  const formData = new FormData();
  formData.append("file", file);
  if (texto) formData.append("texto", texto);
  if (logo) formData.append("logo", logo);
  formData.append("posicion", document.getElementById("img-wm-position").value);

  try {
    const res = await fetch("/api/watermark/image", { method: "POST", body: formData });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `Error HTTP ${res.status}`);
    startTaskMonitoring(data.task_id, "image");
  } catch (err) {
    alert(`Error al aplicar la marca de agua: ${err.message}`);
  }
}

async function processVideoWatermark() {
  const file = document.getElementById("file-video").files[0];
  if (!file) return alert("Por favor selecciona o arrastra un video primero.");
  const texto = document.getElementById("vid-wm-text").value.trim();
  const logo = document.getElementById("vid-wm-logo").files[0];
  if (!texto && !logo) return alert("Ingresa un texto o selecciona un logo para la marca de agua.");

  const formData = new FormData();
  formData.append("file", file);
  if (texto) formData.append("texto", texto);
  if (logo) formData.append("logo", logo);
  formData.append("posicion", document.getElementById("vid-wm-position").value);

  try {
    const res = await fetch("/api/watermark/video", { method: "POST", body: formData });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `Error HTTP ${res.status}`);
    startTaskMonitoring(data.task_id, "video");
  } catch (err) {
    alert(`Error al aplicar la marca de agua: ${err.message}`);
  }
}

// ==========================================
// QUITAR FONDO DE IMÁGENES (rembg)
// ==========================================
async function processRemoveBackground() {
  const file = document.getElementById("file-image").files[0];
  if (!file) return alert("Por favor selecciona o arrastra una imagen primero.");

  const formData = new FormData();
  formData.append("file", file);

  try {
    const res = await fetch("/api/image/remove-background", { method: "POST", body: formData });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `Error HTTP ${res.status}`);
    startTaskMonitoring(data.task_id, "image");
  } catch (err) {
    alert(`Error al quitar el fondo: ${err.message}`);
  }
}

// ==========================================
// PWA (PROGRESSIVE WEB APP)
// ==========================================
let deferredPrompt = null;

function initPWA() {
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/static/sw.js").catch(err => {
        console.warn("ServiceWorker registration failed:", err);
      });
    });
  }

  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    deferredPrompt = e;
    const btn = document.getElementById("pwa-install-btn");
    if (btn) btn.classList.remove("hidden");
  });

  window.addEventListener("appinstalled", () => {
    deferredPrompt = null;
    const btn = document.getElementById("pwa-install-btn");
    if (btn) btn.classList.add("hidden");
    if (notifManager) notifManager.toast("success", "App instalada", "MediaBox Suite se instaló exitosamente como aplicación nativa.");
  });
}

async function installPWA() {
  if (!deferredPrompt) {
    if (notifManager) notifManager.toast("info", "PWA", "Para instalar MediaBox Suite, usa el menú 'Instalar' o 'Añadir a la pantalla de inicio' de tu navegador.");
    return;
  }
  deferredPrompt.prompt();
  const choice = await deferredPrompt.userChoice;
  if (choice && choice.outcome === "accepted") {
    deferredPrompt = null;
    const btn = document.getElementById("pwa-install-btn");
    if (btn) btn.classList.add("hidden");
  }
}

// ==========================================
// MÉTRICAS DE ALMACENAMIENTO & LIMPIEZA
// ==========================================
async function loadStorageInfo() {
  const textEl = document.getElementById("storage-size-text");
  const tempEl = document.getElementById("lib-temp-size");
  try {
    const res = await fetch("/api/storage/info");
    if (!res.ok) return;
    const data = await res.json();
    const outSize = data.output_human || data.output_size || "0 B";
    const tempSize = data.temp_human || data.temp_size || "0 B";
    if (textEl) {
      textEl.innerText = `${outSize} en disco`;
    }
    if (tempEl) {
      tempEl.innerText = tempSize;
    }
  } catch {
    // Backend desconectado
  }
}

async function cleanTempStorage() {
  if (!confirm("¿Deseas vaciar la caché y archivos temporales? Las carpetas por defecto se conservarán.")) {
    return;
  }
  try {
    const res = await fetch("/api/storage/clean-temp", { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `Error HTTP ${res.status}`);
    const freed = data.freed_human || "0 B";
    if (notifManager) notifManager.toast("success", "Caché vaciada", `Se eliminaron ${data.deleted_count || 0} archivos temporales (${freed} liberados).`);
    await loadStorageInfo();
  } catch (err) {
    if (notifManager) notifManager.toast("error", "Error", `No se pudo vaciar la caché: ${err.message}`);
  }
}

async function purgeStorage(target) {
  const descriptions = {
    all: "¿Estás seguro de vaciar TODO el almacenamiento (archivos subidos y generados)?\n\nLas carpetas clasificatorias por defecto se conservarán intactas.",
    input: "¿Estás seguro de vaciar todas las subidas en storage/input/?\n\nLas carpetas clasificatorias por defecto se conservarán intactas.",
    output: "¿Estás seguro de vaciar toda la biblioteca de archivos generados en storage/output/?\n\nLas carpetas clasificatorias por defecto se conservarán intactas.",
  };

  const confirmMsg = descriptions[target] || descriptions.all;
  if (!confirm(confirmMsg)) return;

  try {
    const res = await fetch(`/api/storage/purge?target=${target}`, { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `Error HTTP ${res.status}`);

    const count = data.deleted_count || 0;
    const freed = data.freed_human || "0 B";

    if (notifManager) {
      notifManager.toast(
        "success",
        "Almacenamiento purgado",
        `Se eliminaron ${count} archivos (${freed} liberados). Las carpetas se mantienen intactas.`
      );
    }

    await loadLibrary();
    await loadStorageInfo();
  } catch (err) {
    if (notifManager) notifManager.toast("error", "Error en la purga", err.message);
  }
}

// ==========================================
// BIBLIOTECA / HISTORIAL DE ARCHIVOS
// ==========================================
let allLibraryItems = [];
let currentLibCategory = "all";

async function loadLibrary(category = null) {
  if (category) currentLibCategory = category;
  const container = document.getElementById("library-items-container");
  const emptyEl = document.getElementById("library-empty");
  if (!container) return;

  container.innerHTML = `<div class="col-span-full text-center py-12 text-slate-400 flex items-center justify-center gap-2"><i data-lucide="loader" class="w-5 h-5 animate-spin"></i> Cargando biblioteca...</div>`;
  lucide.createIcons();

  try {
    const res = await fetch("/api/library");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    allLibraryItems = data.items || data.files || [];
    renderLibraryItems();
    loadStorageInfo();
  } catch (err) {
    container.innerHTML = `<div class="col-span-full text-center py-12 text-rose-500 flex items-center justify-center gap-2"><i data-lucide="alert-circle" class="w-5 h-5"></i> Error al cargar biblioteca: ${err.message}</div>`;
    lucide.createIcons();
  }
}

function setLibraryCategory(category) {
  currentLibCategory = category;
  document.querySelectorAll(".libcat-btn").forEach(btn => {
    btn.className = "libcat-btn text-xs font-semibold px-3 py-1 rounded-lg text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white";
  });
  const activeBtn = document.getElementById(`libcat-${category}`);
  if (activeBtn) {
    activeBtn.className = "libcat-btn text-xs font-semibold px-3 py-1 rounded-lg bg-purple-600 text-white shadow-sm";
  }
  renderLibraryItems();
}

function filterLibrary() {
  renderLibraryItems();
}

function renderLibraryItems() {
  const container = document.getElementById("library-items-container");
  const emptyEl = document.getElementById("library-empty");
  const searchInput = document.getElementById("lib-search-input");
  const query = (searchInput ? searchInput.value : "").trim().toLowerCase();

  if (!container) return;

  let filtered = allLibraryItems.filter(item => {
    const itemName = item.filename || item.name || "";
    const itemCat = item.category || "";
    const matchCategory = currentLibCategory === "all" || itemCat === currentLibCategory;
    const matchQuery = !query || itemName.toLowerCase().includes(query) || itemCat.toLowerCase().includes(query);
    return matchCategory && matchQuery;
  });

  if (!filtered.length) {
    container.innerHTML = "";
    if (emptyEl) emptyEl.classList.remove("hidden");
    return;
  }

  if (emptyEl) emptyEl.classList.add("hidden");

  container.innerHTML = filtered.map(item => {
    const fileName = item.filename || item.name || "archivo";
    const fileSize = item.size_human || item.size_formatted || "0 KB";
    const fileDate = item.mtime_human || item.created_at || "";
    const cat = item.category || "general";

    let iconName = "file";
    let badgeColor = "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300";
    if (cat === "audio" || cat === "audios") {
      iconName = "music";
      badgeColor = "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20";
    } else if (cat === "video" || cat === "videos") {
      iconName = "video";
      badgeColor = "bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border border-indigo-500/20";
    } else if (cat === "pdf" || cat === "pdfs" || cat.startsWith("pdf_")) {
      iconName = "file-text";
      badgeColor = "bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20";
    } else if (cat === "image" || cat === "images" || cat === "imagenes") {
      iconName = "image";
      badgeColor = "bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20";
    } else if (cat === "cmyk") {
      iconName = "palette";
      badgeColor = "bg-cyan-500/10 text-cyan-600 dark:text-cyan-400 border border-cyan-500/20";
    } else if (cat === "archive" || cat === "zips") {
      iconName = "archive";
      badgeColor = "bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20";
    }

    let previewHtml = "";
    if ((cat === "audio" || cat === "audios") && item.preview_url) {
      previewHtml = `
        <div class="mt-2.5">
          <audio controls preload="none" class="w-full h-8 rounded-lg" src="${item.preview_url}"></audio>
        </div>
      `;
    } else if ((cat === "image" || cat === "images") && item.preview_url) {
      previewHtml = `
        <div class="mt-2.5 max-h-36 overflow-hidden rounded-lg bg-slate-100 dark:bg-slate-950 flex items-center justify-center">
          <img src="${item.preview_url}" loading="lazy" class="max-h-36 w-full object-contain rounded-lg">
        </div>
      `;
    } else if ((cat === "video" || cat === "videos") && item.preview_url) {
      previewHtml = `
        <div class="mt-2.5 max-h-36 overflow-hidden rounded-lg bg-black flex items-center justify-center">
          <video controls preload="none" class="max-h-36 w-full rounded-lg" src="${item.preview_url}"></video>
        </div>
      `;
    }

    return `
      <div class="bg-slate-50 dark:bg-slate-950/60 border border-slate-200 dark:border-slate-800 rounded-2xl p-4 flex flex-col justify-between hover:border-purple-500/40 transition group">
        <div>
          <div class="flex items-start justify-between gap-2 mb-2">
            <span class="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-md ${badgeColor}">
              <i data-lucide="${iconName}" class="w-3 h-3"></i> ${cat.toUpperCase()}
            </span>
            <span class="text-[11px] font-mono text-slate-400">${fileSize}</span>
          </div>

          <h4 class="font-medium text-sm text-slate-800 dark:text-slate-200 truncate" title="${fileName}">${fileName}</h4>
          <p class="text-[11px] text-slate-400 dark:text-slate-500 mt-0.5">${fileDate}</p>

          ${previewHtml}
        </div>

        <div class="flex items-center justify-between gap-2 mt-4 pt-3 border-t border-slate-200 dark:border-slate-800">
          <a href="${item.download_url}" download="${fileName}" class="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-xl bg-purple-600 hover:bg-purple-500 text-white shadow-sm transition">
            <i data-lucide="download" class="w-3.5 h-3.5"></i> Descargar
          </a>
          <button onclick="deleteLibraryItem('${cat}', '${encodeURIComponent(fileName)}')" title="Eliminar archivo" class="p-1.5 rounded-lg text-slate-400 hover:text-rose-500 hover:bg-rose-500/10 transition">
            <i data-lucide="trash-2" class="w-4 h-4"></i>
          </button>
        </div>
      </div>
    `;
  }).join("");

  lucide.createIcons();
}

async function deleteLibraryItem(category, encodedName) {
  const filename = decodeURIComponent(encodedName);
  if (!confirm(`¿Estás seguro de eliminar el archivo "${filename}"?`)) return;

  try {
    const res = await fetch(`/api/library/${category}/${encodeURIComponent(filename)}`, { method: "DELETE" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    if (notifManager) notifManager.toast("info", "Archivo eliminado", `Se eliminó "${filename}"`);
    await loadLibrary();
  } catch (err) {
    if (notifManager) notifManager.toast("error", "Error al eliminar", err.message);
  }
}

// ==========================================
// SMART DRAG & DROP GLOBAL
// ==========================================
function initGlobalDragDrop() {
  const overlay = document.getElementById("global-drag-overlay");
  if (!overlay) return;

  let dragCounter = 0;

  window.addEventListener("dragenter", (e) => {
    e.preventDefault();
    dragCounter++;
    if (dragCounter === 1) {
      overlay.classList.remove("pointer-events-none", "opacity-0");
      overlay.classList.add("opacity-100");
    }
  });

  window.addEventListener("dragover", (e) => {
    e.preventDefault();
  });

  window.addEventListener("dragleave", (e) => {
    e.preventDefault();
    dragCounter--;
    if (dragCounter <= 0) {
      dragCounter = 0;
      overlay.classList.add("pointer-events-none", "opacity-0");
      overlay.classList.remove("opacity-100");
    }
  });

  window.addEventListener("drop", (e) => {
    e.preventDefault();
    dragCounter = 0;
    overlay.classList.add("pointer-events-none", "opacity-0");
    overlay.classList.remove("opacity-100");

    const files = e.dataTransfer.files;
    if (!files || !files.length) return;

    routeFilesToTool(files);
  });
}

function routeFilesToTool(files) {
  const first = files[0];
  const ext = "." + first.name.split(".").pop().toLowerCase();

  if ([".svg"].includes(ext)) {
    switchTab("cmyk");
    const input = document.getElementById("file-cmyk");
    if (input) {
      input.files = files;
      renderMultipleBadges(files, document.getElementById("selected-cmyk"));
      renderPreProcessingPreview(files, "preview-cmyk", "cmyk");
    }
    if (notifManager) notifManager.toast("info", "Smart Drag & Drop", `Archivo vectorial detectado. Abierto en Imprenta CMYK.`);
  } else if ([".epub", ".mobi", ".azw3", ".fb2"].includes(ext)) {
    switchTab("books");
    const input = document.getElementById("file-book");
    if (input) {
      input.files = files;
      updateFileBadge(files[0], document.getElementById("selected-book"));
      renderPreProcessingPreview(files, "preview-book", "book");
    }
    if (notifManager) notifManager.toast("info", "Smart Drag & Drop", `Libro digital detectado. Abierto en Libros a PDF.`);
  } else if ([".pdf"].includes(ext)) {
    switchTab("pdf");
    switchPdfSubtab("compress");
    const input = document.getElementById("file-pdf-compress");
    if (input) {
      input.files = files;
      renderMultipleBadges(files, document.getElementById("selected-pdf-compress"));
      renderPreProcessingPreview(files, "preview-pdf-compress", "pdf");
    }
    if (notifManager) notifManager.toast("info", "Smart Drag & Drop", `PDF detectado. Abierto en PDF Suite (Comprimir).`);
  } else if ([".heic", ".heif", ".webp", ".jpg", ".jpeg", ".png", ".bmp"].includes(ext)) {
    switchTab("image");
    const input = document.getElementById("file-image");
    if (input) {
      input.files = files;
      renderMultipleBadges(files, document.getElementById("selected-image"));
      renderPreProcessingPreview(files, "preview-image", "image");
    }
    if (notifManager) notifManager.toast("info", "Smart Drag & Drop", `Imagen detectada. Abierta en Optimizar Imágenes.`);
  } else if ([".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"].includes(ext)) {
    switchTab("audio");
    switchAudioSubtab("speed");
    const input = document.getElementById("file-audio-speed");
    if (input) {
      input.files = files;
      updateFileBadge(files[0], document.getElementById("selected-audio-speed"));
      renderPreProcessingPreview(files, "preview-audio-speed", "audio");
    }
    if (notifManager) notifManager.toast("info", "Smart Drag & Drop", `Audio detectado. Abierto en Ajustar Velocidad.`);
  } else if ([".mp4", ".mkv", ".mov", ".webm", ".avi"].includes(ext)) {
    switchTab("video");
    switchVideoSubtab("compress");
    const input = document.getElementById("file-video");
    if (input) {
      input.files = files;
      renderMultipleBadges(files, document.getElementById("selected-video"));
      renderPreProcessingPreview(files, "preview-video", "video");
    }
    if (notifManager) notifManager.toast("info", "Smart Drag & Drop", `Video detectado. Abierto en Video Suite.`);
  } else if ([".docx", ".pptx", ".xlsx", ".xls", ".epub", ".csv"].includes(ext)) {
    switchTab("pdf");
    switchPdfSubtab("markdown");
    const input = document.getElementById("file-markdown");
    if (input) {
      input.files = files;
      updateFileBadge(files[0], document.getElementById("selected-markdown"));
      renderPreProcessingPreview(files, "preview-markdown", "file");
    }
    if (notifManager) notifManager.toast("info", "Smart Drag & Drop", `Documento detectado. Abierto en Convertir a Markdown.`);
  }
}


// ─── MARKDOWN CONVERTER ────────────────────────────────────────────────────

let _markdownCurrentText = "";

function switchMarkdownSource(source) {
  document.getElementById("mdsource-file").classList.toggle("hidden", source !== "file");
  document.getElementById("mdsource-url").classList.toggle("hidden", source !== "url");
  document.querySelectorAll(".mdsrc-btn").forEach(btn => {
    const isActive = btn.id === `mdsrc-${source}`;
    btn.classList.toggle("bg-indigo-600/10", isActive);
    btn.classList.toggle("dark:bg-indigo-600/20", isActive);
    btn.classList.toggle("text-indigo-600", isActive);
    btn.classList.toggle("dark:text-indigo-400", isActive);
    btn.classList.toggle("border-indigo-500", isActive);
    btn.classList.toggle("text-slate-500", !isActive);
    btn.classList.toggle("dark:text-slate-400", !isActive);
    btn.classList.toggle("border-transparent", !isActive);
  });
}

async function processMarkdownConvert() {
  const fileInput = document.getElementById("file-markdown");
  if (!fileInput?.files?.length) {
    showToast("warning", "Sin archivo", "Por favor, selecciona un archivo para convertir.");
    return;
  }
  const file = fileInput.files[0];
  const fd = new FormData();
  fd.append("file", file);

  showGlobalProgress(`Convirtiendo "${file.name}" a Markdown…`, 40);
  try {
    const res = await fetch("/api/convert/markdown", { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Error en la conversión.");
    showMarkdownResult(data);
    if (notifManager) notifManager.success("Conversión completada", `"${file.name}" convertido: ${data.line_count} líneas.`);
    loadStorageInfo();
  } catch (err) {
    showToast("error", "Error de conversión", err.message);
    if (notifManager) notifManager.error("Error", err.message);
  } finally {
    hideGlobalProgress();
  }
}

async function processMarkdownUrl() {
  const urlInput = document.getElementById("markdown-url-input");
  const url = urlInput?.value?.trim();
  if (!url) {
    showToast("warning", "Sin URL", "Por favor, ingresa una URL válida.");
    return;
  }
  const fd = new FormData();
  fd.append("url", url);

  showGlobalProgress(`Convirtiendo URL a Markdown…`, 40);
  try {
    const res = await fetch("/api/convert/markdown/url", { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Error al convertir la URL.");
    showMarkdownResult(data);
    if (notifManager) notifManager.success("URL convertida", `Página convertida: ${data.line_count} líneas.`);
    loadStorageInfo();
  } catch (err) {
    showToast("error", "Error de conversión", err.message);
    if (notifManager) notifManager.error("Error", err.message);
  } finally {
    hideGlobalProgress();
  }
}

function showMarkdownResult(data) {
  _markdownCurrentText = data.markdown || "";
  const resultEl = document.getElementById("markdown-result");
  const previewEl = document.getElementById("markdown-preview-text");
  const metaEl = document.getElementById("markdown-meta");
  const downloadBtn = document.getElementById("markdown-download-btn");

  previewEl.textContent = _markdownCurrentText;
  metaEl.textContent = `${data.char_count?.toLocaleString() || 0} caracteres · ${data.line_count?.toLocaleString() || 0} líneas`;

  if (downloadBtn && data.download_url) {
    downloadBtn.href = data.download_url;
    downloadBtn.setAttribute("download", data.filename || "documento.md");
  }

  resultEl.classList.remove("hidden");
  resultEl.scrollIntoView({ behavior: "smooth", block: "nearest" });

  // Re-render lucide icons inside the result panel
  if (typeof lucide !== "undefined") lucide.createIcons();
}

function copyMarkdownToClipboard() {
  if (!_markdownCurrentText) return;
  navigator.clipboard.writeText(_markdownCurrentText).then(() => {
    showToast("success", "Copiado", "El Markdown fue copiado al portapapeles.");
  }).catch(() => {
    showToast("error", "Error", "No se pudo copiar al portapapeles.");
  });
}

// Inicializar dropzone de Markdown al cargar la página
document.addEventListener("DOMContentLoaded", () => {
  const dz = document.getElementById("dropzone-markdown");
  const input = document.getElementById("file-markdown");
  if (dz && input) {
    dz.addEventListener("click", () => input.click());
    dz.addEventListener("dragover", e => { e.preventDefault(); dz.classList.add("dropzone-active"); });
    dz.addEventListener("dragleave", () => dz.classList.remove("dropzone-active"));
    dz.addEventListener("drop", e => {
      e.preventDefault();
      dz.classList.remove("dropzone-active");
      if (e.dataTransfer.files.length) {
        input.files = e.dataTransfer.files;
        updateFileBadge(e.dataTransfer.files[0], document.getElementById("selected-markdown"));
        renderPreProcessingPreview(e.dataTransfer.files, "preview-markdown", "file");
      }
    });
    input.addEventListener("change", () => {
      if (input.files.length) {
        updateFileBadge(input.files[0], document.getElementById("selected-markdown"));
        renderPreProcessingPreview(input.files, "preview-markdown", "file");
      }
    });
  }
});


