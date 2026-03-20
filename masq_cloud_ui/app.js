/* ═══════════════════════════════════════════════════════════════
   Masq Master Cloud UI — Application Logic
   Drag-drop queue → Modal API → Results gallery
   ═══════════════════════════════════════════════════════════════ */

(() => {
  "use strict";

  // ── STATE ──────────────────────────────────────────────────
  let queue = [];          // { id, file, task, status }
  let results = [];        // { id, name, blobUrl, task }
  let processing = false;

  // ── DOM REFS ───────────────────────────────────────────────
  const $  = (s) => document.querySelector(s);
  const $$ = (s) => document.querySelectorAll(s);

  const dropZone      = $("#drop-zone");
  const fileInput      = $("#file-input");
  const queueSection   = $("#queue-section");
  const queueList      = $("#queue-list");
  const resultsSection = $("#results-section");
  const resultsGrid    = $("#results-grid");
  const progressSection = $("#progress-section");
  const progressBar    = $("#progress-bar");
  const progressText   = $("#progress-text");
  const btnFire        = $("#btn-fire");
  const btnClear       = $("#btn-clear");
  const btnHealth      = $("#btn-health");
  const btnDownloadAll = $("#btn-download-all");
  const endpointInput  = $("#endpoint-url");
  const scaleSlider    = $("#upscale-factor");
  const scaleLabel     = $("#scale-label");
  const costValue      = $("#cost-value");
  const healthStatus   = $("#health-status");
  const finalStats     = $("#final-stats");

  // ── INIT ───────────────────────────────────────────────────
  function init() {
    // Restore saved endpoint
    const saved = localStorage.getItem("masq_endpoint");
    if (saved) endpointInput.value = saved;

    // Events
    endpointInput.addEventListener("change", () => {
      localStorage.setItem("masq_endpoint", endpointInput.value.trim());
    });

    scaleSlider.addEventListener("input", () => {
      scaleLabel.textContent = scaleSlider.value;
      updateCost();
    });

    // Drop zone
    dropZone.addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", (e) => addFiles(e.target.files));

    dropZone.addEventListener("dragover", (e) => {
      e.preventDefault();
      dropZone.classList.add("drag-over");
    });
    dropZone.addEventListener("dragleave", () => {
      dropZone.classList.remove("drag-over");
    });
    dropZone.addEventListener("drop", (e) => {
      e.preventDefault();
      dropZone.classList.remove("drag-over");
      addFiles(e.dataTransfer.files);
    });

    // Buttons
    btnFire.addEventListener("click", fireQueue);
    btnClear.addEventListener("click", clearQueue);
    btnHealth.addEventListener("click", testHealth);
    btnDownloadAll.addEventListener("click", downloadAll);
  }

  // ── FILE HANDLING ──────────────────────────────────────────
  const VALID_TYPES = new Set(["image/png", "image/jpeg", "image/webp"]);
  let idCounter = 0;

  function addFiles(fileList) {
    for (const file of fileList) {
      if (!VALID_TYPES.has(file.type)) continue;
      queue.push({
        id: ++idCounter,
        file,
        task: "bg",
        status: "pending",
      });
    }
    renderQueue();
    fileInput.value = "";
  }

  // ── RENDER QUEUE ───────────────────────────────────────────
  function renderQueue() {
    if (queue.length === 0) {
      queueSection.classList.add("hidden");
      return;
    }
    queueSection.classList.remove("hidden");
    queueList.innerHTML = "";

    queue.forEach((item) => {
      const row = document.createElement("div");
      row.className = `queue-item ${item.status}`;
      row.dataset.id = item.id;

      // Thumbnail
      const thumb = document.createElement("img");
      thumb.className = "queue-thumb";
      thumb.src = URL.createObjectURL(item.file);
      thumb.alt = item.file.name;

      // Name
      const name = document.createElement("span");
      name.className = "queue-name";
      name.textContent = item.file.name;
      name.title = item.file.name;

      // Task selector
      const select = document.createElement("select");
      select.className = "queue-task-select";
      select.disabled = processing;
      select.innerHTML = `
        <option value="bg" ${item.task === "bg" ? "selected" : ""}>✂️ Remove BG</option>
        <option value="upscale" ${item.task === "upscale" ? "selected" : ""}>🔍 Upscale</option>
      `;
      select.addEventListener("change", () => {
        item.task = select.value;
        updateCost();
      });

      // Remove button
      const removeBtn = document.createElement("button");
      removeBtn.className = "queue-remove";
      removeBtn.innerHTML = "×";
      removeBtn.title = "Remove";
      removeBtn.disabled = processing;
      removeBtn.addEventListener("click", () => {
        queue = queue.filter((q) => q.id !== item.id);
        renderQueue();
      });

      row.append(thumb, name, select, removeBtn);
      queueList.appendChild(row);
    });

    updateCost();
  }

  function updateCost() {
    if (queue.length === 0) {
      costValue.textContent = "$0.00";
      return;
    }
    // ~$0.07 cold start + $0.01 per operation
    const cost = 0.07 + 0.01 * (queue.length - 1);
    costValue.textContent = `$${cost.toFixed(2)}`;
  }

  function clearQueue() {
    if (processing) return;
    queue = [];
    renderQueue();
    // Also clear results
    results = [];
    resultsGrid.innerHTML = "";
    resultsSection.classList.add("hidden");
    finalStats.textContent = "";
  }

  // ── FIRE QUEUE ─────────────────────────────────────────────
  async function fireQueue() {
    const endpoint = endpointInput.value.trim();
    if (!endpoint) {
      shakeElement(endpointInput);
      healthStatus.className = "health-msg health-err";
      healthStatus.textContent = "Set your Modal endpoint URL first";
      return;
    }
    if (queue.length === 0 || processing) return;

    processing = true;
    btnFire.disabled = true;
    progressSection.classList.remove("hidden");
    progressBar.style.width = "0%";
    results = [];
    resultsGrid.innerHTML = "";
    resultsSection.classList.remove("hidden");

    const totalItems = queue.length;
    const startTime = performance.now();
    let completed = 0;
    let errors = 0;

    for (const item of queue) {
      // Mark processing
      item.status = "processing";
      updateQueueRow(item);
      progressText.textContent = `Processing ${completed + 1}/${totalItems}: ${item.file.name}…`;

      try {
        const formData = new FormData();
        formData.append("file", item.file);
        formData.append("task", item.task);
        if (item.task === "upscale") {
          formData.append("scale", scaleSlider.value);
        }

        const resp = await fetch(`${endpoint}/process`, {
          method: "POST",
          body: formData,
        });

        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

        const blob = await resp.blob();
        const blobUrl = URL.createObjectURL(blob);

        const suffix = item.task === "bg" ? "_no_bg" : `_${scaleSlider.value}x`;
        const outName = item.file.name.replace(/\.[^.]+$/, `${suffix}.png`);

        results.push({ id: item.id, name: outName, blobUrl, task: item.task });
        addResultCard(outName, blobUrl, item.task);

        item.status = "done";
      } catch (err) {
        console.error(`Failed: ${item.file.name}`, err);
        item.status = "error";
        errors++;
      }

      updateQueueRow(item);
      completed++;
      progressBar.style.width = `${(completed / totalItems) * 100}%`;
    }

    const elapsed = ((performance.now() - startTime) / 1000).toFixed(1);
    const cost = (0.07 + 0.01 * (totalItems - 1)).toFixed(2);
    progressText.textContent = `Done! ${completed - errors}/${totalItems} succeeded`;
    finalStats.textContent = `Processed ${completed - errors} images in ${elapsed}s · Est. cost: $${cost}`;

    if (errors > 0) {
      finalStats.textContent += ` · ${errors} failed`;
    }

    processing = false;
    btnFire.disabled = false;
  }

  function updateQueueRow(item) {
    const row = queueList.querySelector(`[data-id="${item.id}"]`);
    if (row) {
      row.className = `queue-item ${item.status}`;
    }
  }

  // ── RESULTS GALLERY ────────────────────────────────────────
  function addResultCard(name, blobUrl, task) {
    const card = document.createElement("div");
    card.className = "result-card";

    const img = document.createElement("img");
    img.src = blobUrl;
    img.alt = name;
    img.loading = "lazy";

    const info = document.createElement("div");
    info.className = "result-card-info";

    const nameEl = document.createElement("span");
    nameEl.className = "result-card-name";
    nameEl.textContent = name;
    nameEl.title = name;

    const dl = document.createElement("a");
    dl.className = "result-download";
    dl.href = blobUrl;
    dl.download = name;
    dl.textContent = "⬇ Save";

    info.append(nameEl, dl);
    card.append(img, info);
    resultsGrid.appendChild(card);
  }

  function downloadAll() {
    results.forEach((r) => {
      const a = document.createElement("a");
      a.href = r.blobUrl;
      a.download = r.name;
      a.click();
    });
  }

  // ── HEALTH CHECK ───────────────────────────────────────────
  async function testHealth() {
    const endpoint = endpointInput.value.trim();
    if (!endpoint) {
      healthStatus.className = "health-msg health-err";
      healthStatus.textContent = "Enter endpoint URL first";
      return;
    }

    healthStatus.className = "health-msg";
    healthStatus.textContent = "Testing…";

    try {
      const resp = await fetch(`${endpoint}/health`, { method: "GET" });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      healthStatus.className = "health-msg health-ok";
      healthStatus.textContent = `✅ Connected — ${data.engines.join(" + ")}`;
    } catch (err) {
      healthStatus.className = "health-msg health-err";
      healthStatus.textContent = `❌ ${err.message}`;
    }
  }

  // ── UTILS ──────────────────────────────────────────────────
  function shakeElement(el) {
    el.style.animation = "none";
    el.offsetHeight; // trigger reflow
    el.style.animation = "shake 0.4s ease";
    el.style.borderColor = "var(--accent-red)";
    setTimeout(() => { el.style.borderColor = ""; }, 1500);
  }

  // Add shake keyframes dynamically
  const style = document.createElement("style");
  style.textContent = `@keyframes shake { 0%,100% { transform: translateX(0); } 20%,60% { transform: translateX(-4px); } 40%,80% { transform: translateX(4px); } }`;
  document.head.appendChild(style);

  // ── BOOT ───────────────────────────────────────────────────
  init();
})();
