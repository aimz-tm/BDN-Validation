import {


  ANOMALY_FLAG_LABELS,


  CREDIBILITY_FLAG_LABELS,


  IDENTITY_FLAG_LABELS,


  describeFlags,


} from "./flag_labels.js";





const $ = (sel) => document.querySelector(sel);





// ── Toast ──────────────────────────────────────────────────────────────────────


function showToast(message, type = "info", duration = 3500) {


  const container = $("#toast-container");


  if (!container) return;


  const el = document.createElement("div");


  el.className = `toast ${type}`;


  el.textContent = message;


  container.appendChild(el);


  setTimeout(() => { el.style.opacity = "0"; el.style.transition = "opacity 0.3s"; }, duration);


  setTimeout(() => el.remove(), duration + 350);


}





let selectedFile = null;


let historyRows = [];


let previewObjectUrl = null;


let activeHighlightField = null;


let activeTransaction = null;


let _reviewAllRows = [];
let _reviewFilter = "";
let _historyFilter = "";





const FIELD_ROWS = [


  ["vessel_name", "Vessel Name"],


  ["imo", "IMO Number"],


  ["barge_name", "Barge Name"],


  ["mmsi", "MMSI No (Datalastic)"],


  ["start_time", "Pumping Start Time"],


  ["end_time", "Pumping End Time"],


  ["delivery_date", "Delivery Date"],


  ["doc_type", "Document Type"]


];





function renderEmptyFields() {
  const tbody = $("#fields-table tbody");
  if (!tbody) return;
  tbody.innerHTML = FIELD_ROWS.map(([key, label]) =>
    `<tr class="field-row" data-key="${key}">
      <td class="field-label">${label}</td>
      <td class="field-value" data-key="${key}"></td>
    </tr>`
  ).join("");
}

const LOGISTICS_ICONS = {


  correct: "✓",


  incorrect: "✗",


  unknown: "◐",


};





async function checkHealth() {


  const badge = $("#health-badge");


  if (!badge) return;


  try {


    const res = await fetch("/health");


    const data = await res.json();


    const parts = [


      data.pipeline_mode || "unknown",


      data.database_connected ? "DB ✓" : "DB ✗",


      data.model_loaded ? "ML ✓" : "ML ✗",


    ];


    badge.textContent = parts.join(" · ");


  } catch {


    badge.textContent = "API offline";


  }


}





function setupUpload() {


  const dropzone = $("#dropzone");


  const input = $("#file-input");


  // Direct change listener — label+for handles opening the file picker natively


  input.addEventListener("change", () => {


    if (input.files[0]) setFile(input.files[0]);





  });





  // Drag-and-drop


  dropzone.addEventListener("dragover", (e) => {


    e.preventDefault();


    dropzone.classList.add("dragover");


  });


  dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));


  dropzone.addEventListener("drop", (e) => {


    e.preventDefault();


    dropzone.classList.remove("dragover");


    if (e.dataTransfer.files.length) setFile(e.dataTransfer.files[0]);


  });





  $("#validate-btn").addEventListener("click", validateUpload);


}











function showDocumentStage() {


  $("#document-stage").classList.remove("hidden");


}





function setScannerImage(src) {


  const img = $("#scanner-image");


  const placeholder = $("#scanner-placeholder");


  const cacheBust = src.includes("?") ? "&" : "?";


  img.onload = () => {


    img.classList.remove("hidden");


    placeholder.classList.add("hidden");


  };


  img.onerror = () => {


    img.classList.add("hidden");


    placeholder.classList.remove("hidden");


    placeholder.textContent = "Could not load document preview — check server logs.";


  };


  img.src = `${src}${cacheBust}t=${Date.now()}`;


}





function setFile(file) {


  console.log("[upload] setFile called:", file.name, file.type, file.size);


  selectedFile = file;





  // Update validate button


  const btn = $("#validate-btn");


  btn.disabled = false;





  // Update upload status text


  const status = $("#upload-status");


  status.textContent = `✓ ${file.name}`;


  status.classList.remove("error");


  status.style.color = "var(--valid)";


  status.style.fontWeight = "600";





  // Update dropzone visual to show selected state


  const dropzone = $("#dropzone");


  dropzone.classList.add("file-selected");


  const hint = $("#dropzone-hint");


  if (hint) hint.textContent = file.name + " \u2014 click to change";











  showDocumentStage();


  const scanSt = $("#scan-status"); scanSt.textContent = "Document loaded — click Validate to scan and verify"; scanSt.classList.remove("scan-error");





  if (previewObjectUrl) {


    URL.revokeObjectURL(previewObjectUrl);


    previewObjectUrl = null;


  }





  clearHighlights();


  


  // Show empty fields immediately; hide stepper until scan starts
  renderEmptyFields();
  const stepper = $("#pipeline-stepper");
  if (stepper) stepper.classList.add("hidden");





  if (file.type.startsWith("image/")) {


    previewObjectUrl = URL.createObjectURL(file);


    setScannerImage(previewObjectUrl);


  } else {


    $("#scanner-image").classList.add("hidden");


    $("#scanner-placeholder").classList.remove("hidden");


    $("#scanner-placeholder").textContent =


      "PDF uploaded — preview available after server processing";


  }


}





function startScanning() {


  const viewport = $("#scanner-viewport");


  viewport.classList.add("scanning");


  $("#scan-status").textContent = "Scanning document and extracting fields…";


  clearHighlights();


}





function stopScanning(message) {


  $("#scanner-viewport").classList.remove("scanning");


  if (message) $("#scan-status").textContent = message;


}





function clearHighlights() {


  $("#highlight-layer").innerHTML = "";


  activeHighlightField = null;


}





function renderHighlights(highlightData) {


  clearHighlights();


  return;


}





function highlightField(fieldName) {


  activeHighlightField = fieldName;


  document.querySelectorAll(".field-highlight").forEach((el) => {


    if (!fieldName) {


      el.classList.remove("active", "dimmed");


      return;


    }


    if (el.dataset.field === fieldName) {


      el.classList.add("active");


      el.classList.remove("dimmed");


    } else {


      el.classList.remove("active");


      el.classList.add("dimmed");


    }


  });


  document.querySelectorAll(".field-row").forEach((row) => {


    row.classList.toggle("active", row.dataset.field === fieldName);


  });


}





function renderFieldsTable(extraction, highlightData) {


  const foundMap = {};


  (highlightData?.highlights || []).forEach((h) => {


    foundMap[h.field] = h.found_on_document;


  });





  const tbody = $("#fields-table tbody");


  tbody.innerHTML = FIELD_ROWS.map(([key, label]) => {


    let val = extraction?.[key];


    if (val === undefined || val === null) {


      if (key === "mmsi") {


        val = activeTransaction?.barge_resolution?.barge_mmsi || activeTransaction?.identity_resolution?.confirmed_mmsi || "—";


      } else {


        val = "—";


      }


    }


    const located = foundMap[key];


    const locBadge = highlightData?.highlights?.length


      ? located


        ? '<span class="loc-badge">on doc</span>'


        : '<span class="loc-badge missing">not located</span>'


      : "";





    return `<tr class="field-row" data-field="${key}">


      <th>${label}</th>


      <td class="field-val-cell" data-field="${key}" data-value="${val === "—" ? "" : val}">${val}</td>


      <td style="width: 25%; text-align: right;">${locBadge}</td>


    </tr>`;


  }).join("");





  // Wire click to edit


  tbody.querySelectorAll(".field-val-cell").forEach((cell) => {


    cell.addEventListener("click", (e) => {


      e.stopPropagation();


      const current = cell.dataset.value;


      if (cell.querySelector("input")) return;


      cell.innerHTML = `<input type="text" class="edit-input" value="${current}" style="width: 100%;" />`;


      const input = cell.querySelector("input");


      input.focus();





      const saveOnBlur = () => {


        const newVal = input.value;


        cell.dataset.value = newVal;


        cell.textContent = newVal || "—";


      };





      input.addEventListener("blur", saveOnBlur);


      input.addEventListener("keypress", (ev) => {


        if (ev.key === "Enter") {


          input.blur();


        }


      });


    });


  });





  tbody.querySelectorAll(".field-row").forEach((row) => {


    row.addEventListener("mouseenter", () => highlightField(row.dataset.field));


    row.addEventListener("mouseleave", () => highlightField(null));


  });


}





function renderLogistics(items) {


  const section = $("#logistics-section");


  const list = $("#validation-logistics");





  if (!section || !list) return;





  if (!items?.length) {


    section.classList.add("hidden");


    return;


  }





  section.classList.remove("hidden");


  list.innerHTML = items


    .map(


      (item) => `


    <li class="status-${item.status}">


      <span class="logistics-icon">${LOGISTICS_ICONS[item.status] || "◐"}</span>


      <div class="logistics-body">


        <span class="logistics-cat">${item.category}</span>


        <strong>${item.check}</strong>


        <span>${item.detail}</span>


      </div>


    </li>`


    )


    .join("");


}





async function validateUpload() {


  if (!selectedFile) return;


  const status = $("#upload-status");


  const btn = $("#validate-btn");





  btn.disabled = true;


  status.textContent = "Initiating pipeline...";





  const stepper = $("#pipeline-stepper");


  const steps = [


    $("#step-1"),


    $("#step-2"),


    $("#step-3"),


    $("#step-4")


  ];





  // Transition to Results View immediately


  if (window.showView) window.showView("view-results");


  startScanning();


  showDocumentStage();





  // Show stepper on results page overlay and hide fields


  stepper.classList.remove("hidden");


  const extractedFields = $("#extracted-fields-container");


  if (extractedFields) extractedFields.classList.add("hidden");


  steps.forEach(s => s.classList.remove("active", "done"));





  const sleep = (ms) => new Promise(r => setTimeout(r, ms));





  // Visual simulation that mimics real backend progress


  let currentStep = 0;


  steps[currentStep].classList.add("active");


  


  // Progress slowly while waiting for backend


  const stepperInterval = setInterval(() => {


    if (currentStep < steps.length - 2) { // Leave the last step for when it actually finishes


      steps[currentStep].classList.remove("active");


      steps[currentStep].classList.add("done");


      currentStep++;


      steps[currentStep].classList.add("active");


    }


  }, 1500);





  status.textContent = "Validating…";





  const form = new FormData();


  form.append("file", selectedFile);





  try {


    const res = await fetch("/validate", { method: "POST", body: form });


    clearInterval(stepperInterval);





    // Backend finished! Rapidly cascade the remaining steps to green


    while (currentStep < steps.length) {


      steps[currentStep].classList.remove("active");


      steps[currentStep].classList.add("done");


      currentStep++;


      if (currentStep < steps.length) {


        steps[currentStep].classList.add("active");


      }


      await sleep(150); // Fast cascade


    }





    const contentType = res.headers.get("content-type") || "";


    const data = contentType.includes("application/json")


      ? await res.json()


      : { detail: await res.text() };


    if (!res.ok) throw new Error(data.detail || "Validation failed");


    renderVerdict(data);


    status.textContent = `Validated: ${data.transaction_id}`;


    stopScanning("Scan complete — extracted fields highlighted on document");


    await loadTransactions();


  } catch (err) {


    status.textContent = err.message;


    status.classList.add("error");


    // Show prominent error in the scan-status bar
    const scanStatusEl = $("#scan-status");
    if (scanStatusEl) {
      scanStatusEl.textContent = "Scan failed — " + (err.message || "processing error");
      scanStatusEl.classList.add("scan-error");
    }
    $("#scanner-viewport").classList.remove("scanning");

    // Keep the fields sidebar visible with empty rows so layout doesn't collapse
    renderEmptyFields();
    const efOnFail = $("#extracted-fields-container");
    if (efOnFail) efOnFail.classList.remove("hidden");
    showDocumentStage();

  } finally {


    btn.disabled = false;


    // hide stepper after a short delay so user sees all green checks


    setTimeout(() => {


      stepper.classList.add("hidden");


      steps.forEach(s => s.classList.remove("active", "done"));


    }, 1500);


  }


}





function lookupDatalasticMMSI(imo) {


  if (!imo) return "";


  if (imo === "9876543") return "538009999";


  if (imo === "1234567") return "538007777";


  return "53800" + imo.substring(Math.max(0, imo.length - 4));


}





function runComplianceLogic(verdict) {


  const ext = verdict.extraction || {};


  const alerts = [];


  let compGapsScore = 1.0;





  // 1. Fuel Density (0.820–1.010 kg/m³)


  const density = parseFloat(ext.density);


  let densityViol = false;


  if (!isNaN(density)) {


    if (density < 0.820 || density > 1.010) {


      densityViol = true;


      compGapsScore -= 0.33;


      alerts.push({


        alert_type: "marpol_density_violation",


        severity: "HIGH",


        explanation: `Fuel Density (${density.toFixed(3)} kg/m³) is outside safe MARPOL Annex VI limits (0.820–1.010 kg/m³).`


      });


    }


  }





  // 2. Sulphur Content (<= 0.50%)


  const sulphur = parseFloat(ext.sulphur_content);


  let sulphurViol = false;


  if (!isNaN(sulphur)) {


    if (sulphur > 0.50) {


      sulphurViol = true;


      compGapsScore -= 0.33;


      alerts.push({


        alert_type: "marpol_sulphur_violation",


        severity: "HIGH",


        explanation: `Sulphur Content (${sulphur.toFixed(2)}%) exceeds the safe MARPOL Annex VI limit of 0.50%.`


      });


    }


  }





  // 3. Flashpoint (>= 60°C)


  const flashpoint = parseFloat(ext.flashpoint);


  let flashpointViol = false;


  if (!isNaN(flashpoint)) {


    if (flashpoint < 60.0) {


      flashpointViol = true;


      compGapsScore -= 0.34;


      alerts.push({


        alert_type: "marpol_flashpoint_violation",


        severity: "HIGH",


        explanation: `Flashpoint (${flashpoint.toFixed(1)}°C) is below the safe MARPOL Annex VI limit of 60°C.`


      });


    }


  }





  compGapsScore = Math.max(0.0, compGapsScore);





  // 4. AIS Data & Barge AIS missing


  let bargeAisMissing = verdict.barge_resolution?.barge_ais_missing || verdict.evidence?.barge_ais_missing || false;


  if (bargeAisMissing) {


    alerts.push({


      alert_type: "barge_ais_missing",


      severity: "MEDIUM",


      explanation: `Barge AIS telemetry is intermittent or missing for the delivery window.`


    });


  }





  if (!verdict.evidence) verdict.evidence = {};


  verdict.evidence.barge_ais_missing = bargeAisMissing;


  if (verdict.barge_resolution) {


    verdict.barge_resolution.barge_ais_missing = bargeAisMissing;


  }





  // Recalculate weights:


  const docIntegrity = verdict.confidence_scores?.ocr ?? 0.95;


  let dataAnomalies = 1.0;


  if (bargeAisMissing) {


    dataAnomalies -= 0.5;


  }


  if (verdict.anomaly_flags?.length) {


    const filteredFlags = verdict.anomaly_flags.filter(f => f !== "ais_unavailable");


    dataAnomalies -= 0.2 * filteredFlags.length;


  }


  dataAnomalies = Math.max(0.0, dataAnomalies);





  const overallConfidence = (docIntegrity * 0.40) + (dataAnomalies * 0.35) + (compGapsScore * 0.25);





  if (!verdict.confidence_scores) verdict.confidence_scores = {};


  verdict.confidence_scores.ocr = docIntegrity;


  verdict.confidence_scores.vessel = dataAnomalies;


  verdict.confidence_scores.geolocation = dataAnomalies;


  verdict.confidence_scores.overall = overallConfidence;


  verdict.confidence = overallConfidence;





  // Force overall status: MARPOL violations only → HIGH_RISK


  // Missing barge AIS → REVIEW_REQUIRED (yellow) NOT SUSPICIOUS


  let classification = verdict.classification || "VALID";


  if (densityViol || sulphurViol || flashpointViol) {


    classification = "HIGH_RISK";


    verdict.verdict_reason = "HIGH RISK: MARPOL Annex VI compliance violation(s) detected.";


  } else if (bargeAisMissing && !verdict.evidence?.ais_anomaly_detected) {


    // Only upgrade if backend did not already set a stronger classification


    if (classification === "VALID" || classification === "SUSPICIOUS") {


      classification = "REVIEW_REQUIRED";


    }


    if (classification === "REVIEW_REQUIRED") {


      verdict.verdict_reason = "AIS evidence unavailable during delivery window. No anomaly detected — geolocation could not be verified.";


    }


  } else if (classification === "REVIEW_REQUIRED") {


    verdict.verdict_reason = verdict.verdict_reason || "AIS evidence unavailable during delivery window.";


  } else if (classification === "VALID") {


    verdict.verdict_reason = verdict.verdict_reason || "All validation checks passed.";


  }


  verdict.classification = classification;


  verdict.fraud_alerts = alerts;





  return {


    docIntegrity,


    dataAnomalies,


    compGaps: compGapsScore,


    overallConfidence,


    classification


  };


}





function updateConfidenceTracks(data) {


  const scores = data.confidence_scores || {};


  const docScore = scores.ocr ?? 0.95;


  const dataScore = scores.vessel ?? (data.evidence?.barge_ais_missing ? 0.5 : 1.0);





  const ext = data.extraction || {};


  let compScore = 1.0;


  const density = parseFloat(ext.density);


  if (!isNaN(density) && (density < 0.820 || density > 1.010)) compScore -= 0.33;


  const sulphur = parseFloat(ext.sulphur_content);


  if (!isNaN(sulphur) && sulphur > 0.50) compScore -= 0.33;


  const flashpoint = parseFloat(ext.flashpoint);


  if (!isNaN(flashpoint) && flashpoint < 60) compScore -= 0.34;


  compScore = Math.max(0.0, compScore);





  const overallScore = data.confidence ?? ((docScore * 0.40) + (dataScore * 0.35) + (compScore * 0.25));





  const setTrack = (id, val) => {


    const valEl = $(`#track-${id}-val`);


    const fillEl = $(`#track-${id}-fill`);


    if (!valEl || !fillEl) return;


    valEl.textContent = val.toFixed(2);


    fillEl.style.width = `${val * 100}%`;


    fillEl.className = "track-bar-fill";


  };





  setTrack("doc", docScore);


  setTrack("data", dataScore);


  setTrack("comp", compScore);





  const overallValEl = $("#track-overall-val");


  const overallFillEl = $("#track-overall-fill");


  if (overallValEl && overallFillEl) {


    overallValEl.textContent = overallScore.toFixed(2);


    overallFillEl.style.width = `${overallScore * 100}%`;


    overallFillEl.className = "track-bar-fill";


  }


}





function updateComplianceChecklist(data) {


  const ext = data.extraction || {};











  const sulphur = parseFloat(ext.sulphur_content);


  const sulphurStatusEl = $("#comp-sulphur-status");


  const sulphurValEl = $("#comp-sulphur-val");


  if (sulphurStatusEl && sulphurValEl) {


    if (isNaN(sulphur)) {


      sulphurValEl.textContent = "(no data)";


      setStatusBadge(sulphurStatusEl, "SUSPICIOUS");


    } else {


      sulphurValEl.textContent = `(${sulphur.toFixed(2)}%)`;


      if (sulphur <= 0.50) {


        setStatusBadge(sulphurStatusEl, "VALID");


      } else {


        setStatusBadge(sulphurStatusEl, "HIGH_RISK");


      }


    }


  }











  const aisMissing = data.barge_resolution?.barge_ais_missing || data.evidence?.barge_ais_missing || false;


  const aisUnavailable = data.ais_evidence_status === "unavailable" || data.evidence?.ais_unavailable;


  const aisStatusEl = $("#comp-ais-status");


  const aisValEl = $("#comp-ais-val");


  if (aisStatusEl && aisValEl) {


    if (aisMissing || aisUnavailable) {


      aisValEl.textContent = "(unavailable)";


      setStatusBadge(aisStatusEl, "REVIEW_REQUIRED");


    } else {


      aisValEl.textContent = "(active)";


      setStatusBadge(aisStatusEl, "VALID");


    }


  }


}





function setStatusBadge(el, state) {


  el.className = `comp-status badge badge-${state}`;


  el.textContent = state.replace(/_/g, " ");


}





function updateChangelogPanel() {


  const lastTimeEl = $("#edit-last-timestamp");


  const countEl = $("#edit-count");


  const logUl = $("#edit-change-log");


  if (!lastTimeEl || !countEl || !logUl) return;





  const details = activeTransaction?.edit_details || { count: 0, last_edited: null, log: [] };





  lastTimeEl.textContent = details.last_edited ? new Date(details.last_edited).toLocaleString() : "—";


  countEl.textContent = details.count;





  if (!details.log || details.log.length === 0) {


    logUl.innerHTML = "<li>No edits made yet</li>";


    return;


  }





  logUl.innerHTML = details.log.map(item => `


    <li style="margin-bottom: 0.5rem; text-align: left;">


      <span style="color: var(--accent); font-weight: 600;">${new Date(item.timestamp).toLocaleTimeString()}:</span>


      <ul style="margin: 0.25rem 0; padding-left: 1rem; list-style-type: circle;">


        ${item.changes.map(ch => `<li>${ch}</li>`).join("")}


      </ul>


    </li>


  `).join("");


}





async function handleUpdateFields() {


  if (!activeTransaction) return;





  const newValues = {};


  const cells = document.querySelectorAll(".field-val-cell");


  cells.forEach(cell => {


    const field = cell.dataset.field;


    const input = cell.querySelector("input");


    const val = input ? input.value : cell.dataset.value;


    newValues[field] = val === "—" ? "" : val;


  });





  const changes = [];


  const oldExt = activeTransaction.extraction || {};


  console.log("oldExt:", JSON.stringify(oldExt));


  console.log("newValues:", JSON.stringify(newValues));





  // Datalastic MMSI Mock lookup


  let mmsiChanged = false;


  if (newValues.imo && newValues.imo !== oldExt.imo) {


    const newMmsi = lookupDatalasticMMSI(newValues.imo);


    newValues.mmsi = newMmsi;


    mmsiChanged = true;


  }





  FIELD_ROWS.forEach(([key, label]) => {


    let oldVal = oldExt[key];


    if (oldVal === undefined || oldVal === null) {


      if (key === "mmsi") {


        oldVal = activeTransaction.barge_resolution?.barge_mmsi || activeTransaction.identity_resolution?.confirmed_mmsi || "";


      } else {


        oldVal = "";


      }


    }


    const newVal = newValues[key] || "";


    if (String(oldVal) !== String(newVal)) {


      changes.push(`${label}: "${oldVal || "—"}" → "${newVal || "—"}"`);


    }


  });





  console.log("changes:", JSON.stringify(changes), "mmsiChanged:", mmsiChanged);





  if (changes.length === 0 && !mmsiChanged) {


    console.log("Returning early because changes are empty and mmsi is unchanged!");


    alert("No changes detected.");


    return;


  }





  if (!activeTransaction.extraction) activeTransaction.extraction = {};





  FIELD_ROWS.forEach(([key]) => {


    if (key !== "mmsi") {


      activeTransaction.extraction[key] = newValues[key];


    }


  });





  if (newValues.vessel_name) {


    if (!activeTransaction.identity_resolution) activeTransaction.identity_resolution = {};


    activeTransaction.identity_resolution.confirmed_name = newValues.vessel_name;


  }


  if (newValues.imo) {


    if (!activeTransaction.identity_resolution) activeTransaction.identity_resolution = {};


    activeTransaction.identity_resolution.confirmed_imo = newValues.imo;


  }


  if (newValues.barge_name) {


    if (!activeTransaction.barge_resolution) activeTransaction.barge_resolution = {};


    activeTransaction.barge_resolution.barge_confirmed_name = newValues.barge_name;


  }


  if (newValues.mmsi) {


    if (!activeTransaction.barge_resolution) activeTransaction.barge_resolution = {};


    activeTransaction.barge_resolution.barge_mmsi = newValues.mmsi;


  }





  runComplianceLogic(activeTransaction);





  if (!activeTransaction.edit_details) {


    activeTransaction.edit_details = { count: 0, last_edited: null, log: [] };


  }


  activeTransaction.edit_details.count += 1;


  activeTransaction.edit_details.last_edited = new Date().toISOString();


  activeTransaction.edit_details.log.unshift({


    timestamp: activeTransaction.edit_details.last_edited,


    changes: changes


  });





  try {


    const saveRes = await fetch(`/transactions/${encodeURIComponent(activeTransaction.transaction_id)}`, {


      method: "PUT",


      headers: { "Content-Type": "application/json" },


      body: JSON.stringify(activeTransaction)


    });


    if (!saveRes.ok) throw new Error("Failed to save transaction to backend");





    renderVerdict(activeTransaction);


    await loadTransactions();


  } catch (err) {


    alert(err.message);


  }


}





function renderVerdict(data) {


  activeTransaction = data;





  // Populate header details bar


  const headerRef = $("#results-header-ref");


  const headerVesselName = $("#results-header-vessel-name");


  const headerImo = $("#results-header-imo");


  const headerVerdict = $("#results-header-verdict");


  const ext = data.extraction || {};





  if (headerRef) {


    headerRef.textContent = `DOCUMENT ${data.transaction_id || ''}`;


  }


  if (headerVesselName) {


    headerVesselName.textContent = data.upload_filename || "";
  }
  if (headerImo) {
    headerImo.textContent = "";
  }


  if (headerVerdict) {


    headerVerdict.textContent = data.classification.replace(/_/g, " ");


    headerVerdict.className = `badge badge-${data.classification}`;


  }





  const panel = $("#verdict-panel");


  panel.classList.remove("hidden");


  panel.className = `panel verdict-card ${data.classification}`;


  $("#identity-panel").classList.remove("hidden");


  $("#evidence-panel").classList.remove("hidden");


  $("#confidence-panel").classList.remove("hidden");


  $("#fraud-panel").classList.remove("hidden");





  showDocumentStage();

  // Always show extracted fields sidebar
  const _ef = document.getElementById("extracted-fields-container");
  if (_ef) _ef.classList.remove("hidden");


  const verdictClassEl = $("#verdict-class");


  if (verdictClassEl) {


    verdictClassEl.textContent = data.classification.replace(/_/g, " ");


    verdictClassEl.className = `classification badge badge-${data.classification}`;


  }





  const pct = Math.round((data.confidence || 0) * 100);


  $("#confidence-fill").style.width = `${pct}%`;


  $("#verdict-confidence").textContent = `Confidence: ${pct}%`;





  renderLogistics(data.validation_logistics);





  $("#verdict-reason").textContent = data.verdict_reason || "";





  const reviewBanner = $("#human-review-banner");


  if (data.human_review_required) reviewBanner.classList.remove("hidden");


  else reviewBanner.classList.add("hidden");





  const preview = data.preview_url || data.document?.preview_url;


  if (preview) {


    setScannerImage(preview);


  } else if (data.document?.processing_error) {


    $("#scanner-placeholder").classList.remove("hidden");


    $("#scanner-placeholder").textContent = data.document.processing_error;


  }





  const highlightData = data.document?.field_highlights || data.field_highlights;





  renderFieldsTable(ext, highlightData);


  renderHighlights(highlightData);





  // Update progress tracks, compliance checklists and changelog


  updateConfidenceTracks(data);


  updateComplianceChecklist(data);


  updateChangelogPanel();





  // Doc type badge


  const dtBadge = $("#doc-type-badge");


  if (dtBadge) {


    dtBadge.textContent = ext.doc_type || data.doc_type || "";


    dtBadge.style.display = dtBadge.textContent ? "" : "none";


  }





  // ── Vessel identity ────────────────────────────────────────────


  const id = data.identity_resolution || {};


  fillTable("#identity-table tbody", [


    ["BDN Name", id.bdn_name],


    ["BDN IMO", id.bdn_imo],


    ["Confirmed Name", id.confirmed_name],


    ["Confirmed IMO", id.confirmed_imo],


    ["MMSI", id.confirmed_mmsi],


    ["Flag", id.registered_flag],


    ["Vessel Type", id.vessel_type],


    ["Method", id.resolution_method],


    ["Confidence", id.identity_confidence != null ? `${Math.round(id.identity_confidence * 100)}%` : null],


  ]);





  const candBlock = $("#candidates-block");


  if (id.candidates?.length) {


    candBlock.classList.remove("hidden");


    candBlock.innerHTML =


      "<strong>Candidate vessels (human review):</strong><ul>" +


      id.candidates.map((c) => `<li>${c.name} — IMO ${c.imo} (${c.source})</li>`).join("") +


      "</ul>";


  } else {


    candBlock.classList.add("hidden");


  }


  renderFlagList("#identity-flags", describeFlags(id.flags, IDENTITY_FLAG_LABELS));





  // ── Barge identity ─────────────────────────────────────────────


  const barge = data.barge_resolution || {};


  fillTable("#barge-table tbody", [


    ["BDN Barge Name", ext.barge_name],


    ["SB Number", ext.barge_sb_number],


    ["Confirmed Name", barge.barge_confirmed_name],


    ["MMSI", barge.barge_mmsi],


    ["Method", barge.resolution_method],


    ["Confidence", barge.barge_confidence != null ? `${Math.round(barge.barge_confidence * 100)}%` : null],


    ["AIS Available", barge.barge_ais_missing === false ? "Yes" : "No"],


  ]);


  renderFlagList("#barge-flags", (barge.barge_flags || []).map(f => ({ code: f, description: "" })));





  // ── Fraud alerts ──────────────────────────────────


  renderFraudAlerts(data.fraud_alerts || [], data.overall_fraud_risk);


  // Info alerts = missing evidence notices (yellow, separate from fraud)


  renderInfoAlerts(data.info_alerts || []);





  // ── Evidence ───────────────────────────────────────────────────


  const ev = data.evidence || {};


  fillTable(


    "#evidence-table tbody",


    Object.entries(ev)


      .filter(([k]) => k !== "map_html")


      .map(([k, v]) => [k.replace(/_/g, " "), v])


  );





  const mapEl = $("#map-container");
  if (mapEl) mapEl.innerHTML = ev.map_html || "<p class='status-msg'>No map data</p>";





  renderFlagList("#credibility-flags", describeFlags(data.credibility_flags, CREDIBILITY_FLAG_LABELS));


  renderFlagList("#anomaly-flags", describeFlags(data.anomaly_flags, ANOMALY_FLAG_LABELS));





  // ── Audit trail ────────────────────────────────────────────────


  renderAuditTrail(data.audit_trail || []);


}





// ── Gauge renderer ──────────────────────────────────────────────────────


const CIRCUMFERENCE = 251.2; // 2π × 40





function renderGauge(id, value) {


  const pctEl = $(`#g-${id}-pct`);


  const fillEl = $(`#g-${id}-fill`);


  if (!pctEl || !fillEl) return;





  const val = value != null ? Math.round(value * 100) : null;


  if (val == null) {


    pctEl.textContent = "—";


    fillEl.style.strokeDashoffset = CIRCUMFERENCE;


    return;


  }





  pctEl.textContent = `${val}%`;


  const offset = CIRCUMFERENCE - (val / 100) * CIRCUMFERENCE;


  fillEl.style.strokeDashoffset = offset;


  fillEl.classList.remove("green", "amber", "red");


  if (val >= 75) fillEl.classList.add("green");


  else if (val >= 50) fillEl.classList.add("amber");


  else fillEl.classList.add("red");


}





// ── Info alerts renderer (missing evidence, yellow) ────────────────


function renderInfoAlerts(alerts) {


  let container = $("#info-alerts-list");


  if (!container) {


    // Create section if HTML doesn’t have it yet


    const fraudPanel = $("#fraud-panel");


    if (fraudPanel) {


      container = document.createElement("div");


      container.id = "info-alerts-list";


      fraudPanel.appendChild(container);


    } else return;


  }


  if (!alerts.length) {


    container.innerHTML = "";


    return;


  }


  container.innerHTML = `


    <div class="info-alerts-section">


      <h4 style="color:var(--warning,#f59e0b);margin:1rem 0 0.5rem;">&#x26A0; Missing Evidence Notices</h4>


      ${alerts.map(a => `


        <div class="fraud-alert sev-INFO">


          <div class="fraud-alert-header">


            <span class="sev-badge INFO">INFO</span>


            <span class="fraud-alert-type">${a.alert_type.replace(/_/g, " ")}</span>


          </div>


          <p class="fraud-alert-explanation">${a.explanation}</p>


        </div>`).join("")}


    </div>`;


}





// ── Fraud alerts renderer ────────────────────────────────────────────────


function renderFraudAlerts(alerts, overallRisk) {


  const container = $("#fraud-alerts-list");


  const noMsg = $("#no-fraud-msg");





  if (!alerts.length) {


    noMsg.classList.remove("hidden");


    container.innerHTML = "";


    return;


  }





  noMsg.classList.add("hidden");


  container.innerHTML = alerts.map(alert => `


    <div class="fraud-alert sev-${alert.severity}">


      <div class="fraud-alert-header">


        <span class="sev-badge ${alert.severity}">${alert.severity}</span>


        <span class="fraud-alert-type">${alert.alert_type.replace(/_/g, " ")}</span>


      </div>


      <p class="fraud-alert-explanation">${alert.explanation}</p>


    </div>


  `).join("");


}





// ── Audit trail renderer ─────────────────────────────────────────────────


function renderAuditTrail(steps) {


  const tbody = $("#audit-table tbody");


  if (!tbody) return;


  if (!steps.length) {


    tbody.innerHTML = "<tr><td colspan='5'>No audit trail available</td></tr>";


    return;


  }


  tbody.innerHTML = steps.map(s => `


    <tr>


      <td>${s.step}</td>


      <td>${s.result}</td>


      <td>${s.threshold}</td>


      <td class="${s.passed ? "audit-pass" : "audit-fail"}">${s.passed ? "✓ Pass" : "✗ Fail"}</td>


      <td>${s.method || "—"}</td>


    </tr>


  `).join("");


}





function fillTable(tbodySel, rows) {


  const tbody = typeof tbodySel === "string" ? $(tbodySel) : tbodySel;


  tbody.innerHTML = rows


    .map(


      ([label, val]) =>


        `<tr><th>${label}</th><td>${val === null || val === undefined ? "—" : val}</td></tr>`


    )


    .join("");


}





function renderFlagList(sel, items) {


  const el = $(sel);


  if (!items || !items.length) {


    el.innerHTML = "<li>None</li>";


    return;


  }


  el.innerHTML = items


    .map((f) => `<li><strong>${f.code}</strong>${f.description || ""}</li>`)


    .join("");


}





async function loadTransactions() {


  const res = await fetch("/transactions");


  const data = await res.json();


  historyRows = data.transactions || [];


  renderHistoryStats(historyRows);


  const toShow = _historyFilter ? historyRows.filter(r => r.classification === _historyFilter) : historyRows;


  renderHistoryTable(toShow);


  await loadReviewQueue();


}





function isBargeMissing(tx) {
  const ext = tx.extraction || {};
  const barge = tx.barge_resolution || {};
  return !ext.barge_name && !barge.barge_confirmed_name;
}


function renderHistoryStats(rows) {


  const el = $("#history-stats");


  if (!el) return;


  const total = rows.length;
  const valid = rows.filter(r => r.classification === "VALID").length;
  const susp  = rows.filter(r => r.classification === "SUSPICIOUS").length;
  const high  = rows.filter(r => r.classification === "HIGH_RISK").length;
  const rej   = rows.filter(r => r.classification === "REJECTED").length;


  const cards = [
    { label: "All",       filter: "",           value: total, cls: ""         },
    { label: "Valid",     filter: "VALID",      value: valid, cls: "valid"    },
    { label: "Suspicious",filter: "SUSPICIOUS", value: susp,  cls: "suspicious"},
    { label: "High Risk", filter: "HIGH_RISK",  value: high,  cls: "high-risk"},
    { label: "Rejected",  filter: "REJECTED",   value: rej,   cls: "high-risk"},
  ];


  el.innerHTML = cards.map(c =>
    `<div class="stat-card filter-card${_historyFilter === c.filter ? " active" : ""}" data-filter="${c.filter}" style="cursor:pointer;">
      <span class="stat-card-label">${c.label}</span>
      <span class="stat-card-value ${c.cls}">${c.value}</span>
    </div>`
  ).join("");


  el.querySelectorAll(".filter-card").forEach(card => {
    card.addEventListener("click", () => {
      _historyFilter = card.dataset.filter;
      renderHistoryStats(historyRows);
      const filtered = _historyFilter ? historyRows.filter(r => r.classification === _historyFilter) : historyRows;
      renderHistoryTable(filtered);
    });
  });


}





async function loadReviewQueue() {


  const res = await fetch("/transactions?human_review_only=true");


  const data = await res.json();


  const tbody = $("#review-table tbody");


  const rows = (data.transactions || []).filter(
    (r) => r.classification !== "MANUALLY_APPROVED"
        && r.classification !== "REJECTED"
        && r.classification !== "VALID"
  );





  const alarm = $("#review-alarm");


  if (alarm) {
    alarm.classList.toggle("hidden", rows.length === 0);
  }

  _reviewAllRows = rows;

   renderReviewStats();
  renderReviewRows(rows, _reviewFilter);
}

function renderReviewStats() {
  const statsEl = document.getElementById("review-stats");
  if (!statsEl) return;
  const high = _reviewAllRows.filter(function(r) { return r.classification === "HIGH_RISK"; }).length;
  const susp = _reviewAllRows.filter(function(r) { return r.classification === "SUSPICIOUS"; }).length;
  statsEl.innerHTML =
    '<div class="stat-card filter-card' + (_reviewFilter === "" ? " active" : "") + '" data-filter="" style="cursor:pointer;">' +
      '<span class="stat-card-label">All Pending</span>' +
      '<span class="stat-card-value pending">' + _reviewAllRows.length + '</span>' +
    '</div>' +
    '<div class="stat-card filter-card' + (_reviewFilter === "HIGH_RISK" ? " active" : "") + '" data-filter="HIGH_RISK" style="cursor:pointer;">' +
      '<span class="stat-card-label">High Risk</span>' +
      '<span class="stat-card-value high-risk">' + high + '</span>' +
    '</div>' +
    '<div class="stat-card filter-card' + (_reviewFilter === "SUSPICIOUS" ? " active" : "") + '" data-filter="SUSPICIOUS" style="cursor:pointer;">' +
      '<span class="stat-card-label">Suspicious</span>' +
      '<span class="stat-card-value suspicious">' + susp + '</span>' +
    '</div>';
  statsEl.querySelectorAll(".filter-card").forEach(function(card) {
    card.addEventListener("click", function() {
      _reviewFilter = card.dataset.filter;
      renderReviewStats();
      renderReviewRows(_reviewAllRows, _reviewFilter);
    });
  });
}
function renderReviewRows(rows, filter) {
  const tbody = $("#review-table tbody");
  const filtered = filter ? rows.filter(r => r.classification === filter) : rows;
  if (!filtered.length) {
    tbody.innerHTML = `<tr><td colspan='6' style='text-align:center;color:var(--text-muted);padding:24px'>No items${filter ? " matching this filter" : " pending review"}</td></tr>`;
    return;
  }
  tbody.innerHTML = filtered.map((r) => {


    const pct = Math.round((r.confidence || 0) * 100);


    return `<tr>

      <td><span style="font-size:11px;color:var(--text-muted)">${r.transaction_id}</span></td>

      <td class="td-vessel">${r.vessel_name || ""}</td>

      <td>${r.imo || ""}</td>

      <td><span class="badge badge-${r.classification}">${r.classification.replace(/_/g, ' ')}</span></td>

      <td>

        <div class="table-conf-wrap">

          <div class="table-conf-bar"><div class="table-conf-fill" style="width:${pct}%"></div></div>

          <span class="table-conf-pct">${pct}%</span>

        </div>

      </td>

      <td><button type="button" class="btn-review-row" data-review-id="${r.transaction_id}">Review</button></td>

    </tr>`;


  }).join("");





  tbody.querySelectorAll(".btn-review-row").forEach((btn) => {


    btn.addEventListener("click", () => openReviewPanel(btn.dataset.reviewId));


  });


}





function renderHistoryTable(rows) {


  const tbody = $("#history-table tbody");


  tbody.innerHTML = rows


    .map((r) => {


      const pct = Math.round((r.confidence || 0) * 100);


      const cls = r.classification || "UNKNOWN";


      // For manually approved rows show a reviewer note tooltip if present


      const badgeExtra = cls === "MANUALLY_APPROVED" && r.reviewer_notes


        ? ` title="${r.reviewer_notes.replace(/"/g, "&quot;")}"` : "";


      const rowClass = cls === "MANUALLY_APPROVED" ? ' class="row-approved"' : cls === "REJECTED" ? ' class="row-rejected"' : "";
      return `<tr${rowClass}>


        <td>${formatDate(r.validated_at)}</td>


        <td><a href="#" data-id="${r.transaction_id}">${r.transaction_id}</a></td>


        <td class="td-vessel">${r.vessel_name || "\u2014"}</td>


        <td>${r.port || "\u2014"}</td>


        <td><span class="badge badge-${cls}"${badgeExtra}>${cls.replace(/_/g, ' ')}</span></td>


        <td>


          <div class="table-conf-wrap">


            <div class="table-conf-bar"><div class="table-conf-fill" style="width:${pct}%"></div></div>


            <span class="table-conf-pct">${pct}%</span>


          </div>


        </td>


        <td>${r.upload_filename || "\u2014"}</td>


      </tr>`;


    })


    .join("");


  bindTransactionLinks(tbody);


}





function bindTransactionLinks(container) {


  container.querySelectorAll("a[data-id]").forEach((a) => {


    a.addEventListener("click", async (e) => {


      e.preventDefault();


      await openTransaction(a.dataset.id);


    });


  });


}





async function openTransaction(id) {


  const res = await fetch(`/transactions/${encodeURIComponent(id)}`);


  if (!res.ok) return;


  const data = await res.json();


  if (window.showView) window.showView("view-results");


  renderVerdict(data);


  document.getElementById("document-stage").scrollIntoView({ behavior: "smooth" });


}





// ── Review Panel ────────────────────────────────────────────────────────────





const _REVIEW_FIELDS = [


  { key: "vessel_name",     label: "Vessel Name",      full: false },


  { key: "imo",             label: "IMO",               full: false },


  { key: "barge_name",      label: "Barge Name",        full: false },


  { key: "port",            label: "Port",              full: false },


  { key: "delivery_date",   label: "Delivery Date",     full: false },


  { key: "start_time",      label: "Pumping Start",     full: false },


  { key: "end_time",        label: "Pumping End",       full: false },


  { key: "quantity_mt",     label: "Quantity (MT)",     full: false },


  { key: "density",         label: "Density",           full: false },


  { key: "sulphur_content", label: "Sulphur %",         full: false },


  { key: "flashpoint",      label: "Flashpoint (°C)",   full: false },


  { key: "fuel_type",       label: "Fuel Type",         full: false },


  { key: "supplier",        label: "Supplier",          full: true  },


];





let _reviewTxId = null;





async function openReviewPanel(id) {


  _reviewTxId = id;


  const res = await fetch(`/transactions/${encodeURIComponent(id)}`);


  if (!res.ok) return;


  const tx = await res.json();





  const ext = tx.extraction || {};


  const cls = tx.classification || "UNKNOWN";


  const pct = Math.round((tx.confidence || 0) * 100);





  // Header


  $("#rp-title").textContent = id;


  const badgeEl = $("#rp-current-badge");


  badgeEl.className = `badge badge-${cls}`;


  badgeEl.textContent = cls.replace(/_/g, " ");


  $("#rp-current-conf").textContent = `${pct}% confidence`;


  // Verdict reason — one-liner explaining what triggered the flag


  const reasonEl = $("#rp-verdict-reason");


  if (reasonEl) {


    reasonEl.textContent = tx.verdict_reason || "";


  }





  // Build editable fields


  const fieldsEl = $("#rp-fields");


  fieldsEl.innerHTML = _REVIEW_FIELDS.map(({ key, label, full }) => {


    const val = ext[key] != null ? ext[key] : "";


    return `<div class="rp-field${full ? " rp-full" : ""}">


      <label for="rp-field-${key}">${label}</label>


      <input id="rp-field-${key}" type="text" value="${String(val).replace(/"/g, "&quot;")}" data-field="${key}" />


    </div>`;


  }).join("");





  // Notes


  $("#rp-notes").value = tx.reviewer_notes || "";





  // Status


  const statusEl = $("#rp-status");


  statusEl.textContent = "";


  statusEl.className = "rp-status";





  // Wire approve / reject


  const approveBtn = $("#rp-approve-btn");


  const rejectBtn = $("#rp-reject-btn");


  approveBtn.disabled = false;





  approveBtn.onclick = () => submitReview(tx, "approve");


  rejectBtn.onclick  = () => submitReview(tx, "reject");





  // Fraud alerts accordion


  const fraudSection = $("#rp-fraud-section");


  const fraudBody = $("#rp-fraud-body");


  const fraudLabel = $("#rp-fraud-label");


  if (fraudSection && fraudBody) {


    const alerts = tx.fraud_alerts || [];


    if (alerts.length) {


      fraudSection.classList.remove("hidden");


      if (fraudLabel) fraudLabel.textContent = `Fraud & Violation Alerts (${alerts.length})`;


      fraudBody.innerHTML = alerts.map(a => `


        <div class="fraud-alert sev-${a.severity}" style="margin:6px 0 0;">


          <div class="fraud-alert-header">


            <span class="sev-badge ${a.severity}">${a.severity}</span>


            <span class="fraud-alert-type">${a.alert_type.replace(/_/g, ' ')}</span>


          </div>


          <p class="fraud-alert-explanation">${a.explanation}</p>


        </div>`).join("");


      const toggle = $("#rp-fraud-toggle");


      if (toggle) {


        toggle.onclick = () => {


          const hidden = fraudBody.classList.toggle("hidden");


          const chevron = $("#rp-fraud-chevron");


          if (chevron) chevron.style.transform = hidden ? "" : "rotate(180deg)";


        };


      }


    } else {


      fraudSection.classList.add("hidden");


    }


  }


  // Document preview
  const previewEl = $("#rp-doc-preview");
  if (previewEl) {
    const imgUrl = tx.preview_url || (tx.upload_filename ? `/static/uploads/${encodeURIComponent(tx.upload_filename)}` : null);
    if (imgUrl) {
      previewEl.innerHTML = `<img src="${imgUrl}" alt="Document preview" style="width:100%;border-radius:6px;display:block;" onerror="this.parentElement.style.display='none'" />`;
      previewEl.style.display = "block";
    } else {
      previewEl.style.display = "none";
    }
  }

  // Show panel + overlay
  $("#review-overlay").classList.remove("hidden");
  $("#review-panel").classList.remove("hidden");
  lucide.createIcons();
}





function closeReviewPanel() {


  $("#review-overlay").classList.add("hidden");


  $("#review-panel").classList.add("hidden");


  _reviewTxId = null;


}





async function submitReview(tx, action) {
  const id = tx.transaction_id;
  const newClassification = action === "approve" ? "VALID" : "REJECTED";
  const statusEl = $("#rp-status");
  const approveBtn = $("#rp-approve-btn");
  approveBtn.disabled = true;
  statusEl.textContent = "Saving...";
  statusEl.className = "rp-status";

  // Collect edited field values
  const updatedExt = Object.assign({}, tx.extraction || {});
  $("#rp-fields").querySelectorAll("input[data-field]").forEach((inp) => {
    updatedExt[inp.dataset.field] = inp.value.trim();
  });

  const notes = $("#rp-notes").value.trim();
  const now = new Date().toISOString();

  const verdictReason = action === "approve"
    ? ("Manually approved by reviewer" + (notes ? ": " + notes : "") + ".")
    : ("Rejected by reviewer" + (notes ? ": " + notes : "") + ".");

  const payload = {
    extraction: updatedExt,
    classification: newClassification,
    confidence: tx.confidence,
    human_review_required: false,
    manually_approved: action === "approve",
    manually_rejected: action === "reject",
    reviewer_notes: notes,
    reviewed_at: now,
    verdict_reason: verdictReason,
  };

  try {
    const res = await fetch("/transactions/" + encodeURIComponent(id), {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!res.ok) throw new Error("Server error " + res.status);

    // --- Optimistic update: mutate in-memory state immediately ---
    // Remove from review queue
    _reviewAllRows = _reviewAllRows.filter((r) => r.transaction_id !== id);

    // Update or insert in history rows
    const updatedRow = Object.assign({}, tx, {
      classification: newClassification,
      human_review_required: false,
      verdict_reason: verdictReason,
      reviewed_at: now,
    });
    const hIdx = historyRows.findIndex((r) => r.transaction_id === id);
    if (hIdx >= 0) {
      historyRows[hIdx] = updatedRow;
    } else {
      historyRows.unshift(updatedRow);
    }

    // Re-render review queue (stats + table + alarm)
    const alarm = document.getElementById("review-alarm");
    if (alarm) alarm.classList.toggle("hidden", _reviewAllRows.length === 0);
    renderReviewStats();
    renderReviewRows(_reviewAllRows, _reviewFilter);

    // Re-render history (stats + table)
    renderHistoryStats(historyRows);
    const toShow = _historyFilter
      ? historyRows.filter((r) => r.classification === _historyFilter)
      : historyRows;
    renderHistoryTable(toShow);

    closeReviewPanel();
    showToast(
      action === "approve"
        ? "Document approved and moved to history."
        : "Document rejected and moved to history.",
      action === "approve" ? "success" : "info"
    );

    // Sync history immediately (non-blocking) — updates history table with server truth
    loadTransactions();

  } catch (err) {
    statusEl.textContent = "Error: " + err.message;
    statusEl.className = "rp-status error";
    showToast("Failed: " + err.message, "error");
    approveBtn.disabled = false;
  }
}

function formatDate(iso) {


  if (!iso) return "—";


  try {


    return new Date(iso).toLocaleString();


  } catch {


    return iso;


  }


}





function setupHistorySort() {


  $("#history-table thead").addEventListener("click", (e) => {


    const th = e.target.closest("th[data-sort]");


    if (!th) return;


    const key = th.dataset.sort;


    const sorted = [...historyRows].sort((a, b) => {


      const av = a[key] ?? "";


      const bv = b[key] ?? "";


      if (typeof av === "number") return av - bv;


      return String(av).localeCompare(String(bv));


    });


    renderHistoryTable(sorted);


  });


}





function setupAuditToggle() {


  const btn = $("#audit-toggle");


  const body = $("#audit-body");


  if (!btn || !body) return;


  btn.addEventListener("click", () => {


    const expanded = btn.getAttribute("aria-expanded") === "true";


    btn.setAttribute("aria-expanded", !expanded);


    body.classList.toggle("hidden", expanded);


  });


}





async function loadConfig() {


  const res = await fetch("/config");


  const data = await res.json();


  $("#config-editor").value = JSON.stringify(data, null, 2);


}





async function saveConfig() {


  const status = $("#config-status");


  try {


    const parsed = JSON.parse($("#config-editor").value);


    const res = await fetch("/config", {


      method: "PUT",


      headers: { "Content-Type": "application/json" },


      body: JSON.stringify({ config: parsed }),


    });


    const data = await res.json();


    if (!res.ok) throw new Error(data.detail || "Save failed");


    status.textContent = "Configuration saved.";


    status.classList.remove("error");


    await checkHealth();


  } catch (err) {


    status.textContent = err.message;


    status.classList.add("error");


  }


}





function setupRouting() {


  const views = document.querySelectorAll(".view");


  const navItems = document.querySelectorAll(".nav-item");


  const sidebar = $("#sidebar");





  function showView(viewId) {


    sessionStorage.setItem("activeView", viewId);


    views.forEach(v => {


      v.classList.add("hidden");


      v.classList.remove("active");


    });


    views.forEach(v => {


      if (v.id === viewId) {


        v.classList.remove("hidden");


        // small timeout to trigger css animation


        setTimeout(() => v.classList.add("active"), 10);


      }


    });





    navItems.forEach(n => n.classList.remove("active"));


    const activeNav = document.querySelector(`.nav-item[data-view="${viewId}"]`);


    if (activeNav) activeNav.classList.add("active");





    // Hide Review Hub if on review queue


    const hub = $("#review-hub");


    if (hub) {


      if (viewId === "view-review") hub.style.display = "none";


      else hub.style.display = "";


    }


  }





  navItems.forEach(item => {


    item.addEventListener("click", e => {


      e.preventDefault();


      const viewId = item.dataset.view;





      if (viewId === "view-history") {
        loadTransactions();
      }

      if (viewId === "view-review") {
        loadReviewQueue();
      }

      if (viewId === "view-landing") {


        // Reset file input


        $("#file-input").value = "";


        selectedFile = null;


        $("#validate-btn").disabled = true;


        const status = $("#upload-status");


        status.textContent = "";


        status.classList.remove("error");


        status.style.color = "";


        status.style.fontWeight = "";


        // Reset dropzone visual


        const dz = $("#dropzone");


        dz.classList.remove("file-selected");


        const hint = $("#dropzone-hint");


        if (hint) hint.textContent = "Supports PNG, JPG, PDF";





      }





      showView(viewId);


    });


  });





  // Hub click routes to review


  const hub = $("#review-hub");


  if (hub) {


    hub.addEventListener("click", () => {


      showView("view-review");


    });


  }





  // Restore last active view on page load (survives browser refresh)


  const savedView = sessionStorage.getItem("activeView");


  if (savedView && document.getElementById(savedView)) {


    showView(savedView);


  }


  // Expose for other functions


  window.showView = showView;


}





function setupTheme() {


  const toggleBtn = $("#theme-toggle");


  if (!toggleBtn) return;


  const iconSun = toggleBtn.querySelector(".icon-sun");


  const iconMoon = toggleBtn.querySelector(".icon-moon");


  const logos = document.querySelectorAll(".theme-aware-logo");





  function setTheme(theme) {


    document.documentElement.dataset.theme = theme;


    localStorage.setItem("theme", theme);


    if (theme === "light") {


      iconSun.classList.add("hidden");


      iconMoon.classList.remove("hidden");


      logos.forEach(l => l.src = "/static/img/logo-light.png");


    } else {


      iconSun.classList.remove("hidden");


      iconMoon.classList.add("hidden");


      logos.forEach(l => l.src = "/static/img/logo-dark.png");


    }


  }





  // Check saved theme or system preference


  const saved = localStorage.getItem("theme");


  setTheme(saved === "light" ? "light" : "dark");





  toggleBtn.addEventListener("click", () => {


    const current = document.documentElement.dataset.theme;


    setTheme(current === "light" ? "dark" : "light");


  });


}





function init() {


  try {


    setupUpload();


    setupHistorySort();


    setupAuditToggle();


    setupRouting();


    setupTheme();


    const cs = $("#config-save");


    if (cs) cs.addEventListener("click", saveConfig);


    const cr = $("#config-reload");


    if (cr) cr.addEventListener("click", loadConfig);


    // Review panel close handlers


    const rpClose = $("#review-panel-close");


    if (rpClose) rpClose.addEventListener("click", closeReviewPanel);


    const overlay = $("#review-overlay");


    if (overlay) overlay.addEventListener("click", closeReviewPanel);





    checkHealth();


    loadTransactions();


    loadConfig();


  } catch (err) {


    alert("Initialization Error: " + err.message + "\nLine: " + err.lineNumber);


  }


}





init();





