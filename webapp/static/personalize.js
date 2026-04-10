const personalizeState = {
  currentSource: "manual",
  activeContext: "easy",
  profile: null,
  rotation: [],
  rotationSummary: null,
  recommendations: {},
  catalogShoes: [],
  visualizations: null,
  hasData: false,
  sourceCollapsed: false,
  recsCollapsed: false,
};

const banner = document.getElementById("personalize-banner");
const sourceCards = Array.from(document.querySelectorAll(".source-card"));
const manualPanel = document.getElementById("manual-panel");
const uploadPanel = document.getElementById("upload-panel");
const stravaPanel = document.getElementById("strava-panel");
const manualForm = document.getElementById("manual-shoe-form");
const uploadForm = document.getElementById("upload-form");
const profileForm = document.getElementById("profile-form");
const profileSummary = document.getElementById("profile-summary");
const rotationTableBody = document.getElementById("rotation-table-body");
const recommendationMeta = document.getElementById("recommendation-meta");
const recommendationResults = document.getElementById("recommendation-results");
const contextTabs = Array.from(document.querySelectorAll(".tab-button"));
const catalogSelect = document.getElementById("manual-catalog-shoe");

// Visualization elements
const vizEmptyState = document.getElementById("viz-empty-state");
const vizEfficiency = document.getElementById("viz-efficiency");
const vizMonthly = document.getElementById("viz-monthly");
const vizMileage = document.getElementById("viz-mileage");
const vizPace = document.getElementById("viz-pace");
const vizCalendar = document.getElementById("viz-calendar");
const vizEfficiencyContent = document.getElementById("viz-efficiency-content");
const vizMonthlyContent = document.getElementById("viz-monthly-content");
const vizMileageContent = document.getElementById("viz-mileage-content");
const vizPaceContent = document.getElementById("viz-pace-content");
const vizCalendarContent = document.getElementById("viz-calendar-content");

// State sections
const landingState = document.getElementById("landing-state");
const importState = document.getElementById("import-state");
const mappingState = document.getElementById("mapping-state");
const dashboardState = document.getElementById("dashboard-state");

// Landing elements
const getStartedBtn = document.getElementById("get-started-btn");

// Import elements
const dropZone = document.getElementById("drop-zone");
const importFileInput = document.getElementById("import-file-input");
const uploadBtn = document.getElementById("upload-btn");
const uploadProgress = document.getElementById("upload-progress");
const backToLandingBtn = document.getElementById("back-to-landing");
const continueToMappingBtn = document.getElementById("continue-to-mapping");
const previewMileage = document.getElementById("preview-mileage");
const previewShoes = document.getElementById("preview-shoes");
const previewActivities = document.getElementById("preview-activities");
const previewDateRange = document.getElementById("preview-date-range");

// Mapping elements
const detectedShoesList = document.getElementById("detected-shoes-list");
const saveAndContinueMappingBtn = document.getElementById("save-and-continue-mapping");
const skipMappingBtn = document.getElementById("skip-mapping");

// Dashboard elements
const dashboardTabs = document.querySelectorAll(".dashboard-tabs .tab-btn");
const tabContents = document.querySelectorAll(".tab-content");
const recsHeader = document.getElementById("recs-header");
const recsContent = document.getElementById("recs-content");
const recsIndicator = document.getElementById("recs-indicator");
const resultsStep = document.getElementById("results-step");

function setBanner(message, level = "info") {
  banner.textContent = message;
  banner.className = `message-banner ${level}`;
}

async function apiFetch(url, options = {}) {
  const response = await fetch(url, {
    credentials: "same-origin",
    ...options,
  });
  if (!response.ok) {
    let detail = "Request failed";
    try {
      const payload = await response.json();
      detail = payload.detail || payload.error || detail;
    } catch (error) {
      detail = await response.text();
    }
    throw new Error(detail);
  }
  return response.json();
}

function chip(label, value) {
  return `<span class="chip">${label}: ${value}</span>`;
}

function formatCount(value) {
  return Number(value || 0).toLocaleString();
}

function formatList(items) {
  if (!items?.length) {
    return `<p class="support-copy compact">No major gaps right now.</p>`;
  }
  return `<ul class="signal-list">${items.map((item) => `<li>${item}</li>`).join("")}</ul>`;
}

function sourceKindLabel(value) {
  if (value === "manual_with_import") {
    return "manual + imported activity";
  }
  if (value === "imported") {
    return "imported activity";
  }
  return "manual";
}

function mappingStatusLabel(value) {
  return value === "catalog_matched" ? "matched" : "unmapped";
}

function statusLabel(shoe) {
  const label = shoe.status.replaceAll("_", " ");
  if (shoe.remaining_km === null || shoe.remaining_km === undefined) {
    return label;
  }
  return `${label} · ${Math.max(shoe.remaining_km, 0).toFixed(0)} km left`;
}

function switchSource(nextSource) {
  personalizeState.currentSource = nextSource;
  sourceCards.forEach((card) => card.classList.toggle("active", card.dataset.source === nextSource));
  manualPanel.classList.toggle("active", nextSource === "manual");
  uploadPanel.classList.toggle("active", nextSource === "csv" || nextSource === "gpx");
  stravaPanel.classList.toggle("active", nextSource === "strava");
  updateSourceSummary();
}

// State management
let currentState = "landing"; // landing, import, mapping, dashboard

function showState(state) {
  currentState = state;
  
  // Hide all states
  landingState.style.display = "none";
  importState.style.display = "none";
  mappingState.style.display = "none";
  dashboardState.style.display = "none";
  
  // Show target state
  switch (state) {
    case "landing":
      landingState.style.display = "block";
      break;
    case "import":
      importState.style.display = "block";
      break;
    case "mapping":
      mappingState.style.display = "block";
      renderDetectedShoesForMapping();
      break;
    case "dashboard":
      dashboardState.style.display = "block";
      refreshWorkspace();
      break;
  }
  
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function showLanding() {
  showState("landing");
}

function showImport() {
  showState("import");
}

function showMapping() {
  showState("mapping");
}

function showDashboard() {
  showState("dashboard");
}

// Toggle recommendations panel
function toggleRecsPanel() {
  personalizeState.recsCollapsed = !personalizeState.recsCollapsed;
  const isCollapsed = personalizeState.recsCollapsed;
  recsContent.classList.toggle("collapsed", isCollapsed);
  recsIndicator.textContent = isCollapsed ? "+" : "−";
  if (recsHeader) {
    recsHeader.classList.toggle("collapsed", isCollapsed);
  }
}

// Show/hide recommendations based on data availability
function updateRecommendationsVisibility() {
  const hasData = personalizeState.rotation.length > 0 || 
                  (personalizeState.visualizations && 
                   (personalizeState.visualizations.efficiency_heatmap?.length > 0 ||
                    personalizeState.visualizations.monthly_mileage?.length > 0));
  
  personalizeState.hasData = hasData;
  
  if (resultsStep) {
    resultsStep.style.display = hasData ? "block" : "none";
  }
  
  updateProgressIndicator();
}

function renderProfile() {
  const profile = personalizeState.profile;
  if (!profile) {
    profileSummary.innerHTML = `<div class="empty-panel"><p>No runner profile yet.</p></div>`;
    return;
  }
  const summary = profile.summary || {};
  const coverage = profile.coverage || {};
  const overrides = profile.manual_overrides || {};
  const rotationSummary = personalizeState.rotationSummary || {};
  const detectedShoes = personalizeState.rotation.length;
  profileSummary.innerHTML = `
    <div class="summary-stack">
      <section class="summary-block">
        <p class="eyebrow">Training history we have</p>
        <div class="summary-grid">
          <div class="summary-tile">
            <span class="summary-label">Imported runs</span>
            <span class="summary-value">${formatCount(summary.total_runs)}</span>
          </div>
          <div class="summary-tile">
            <span class="summary-label">Weekly mileage</span>
            <span class="summary-value">${summary.weekly_mileage_km ?? 0} km</span>
          </div>
          <div class="summary-tile">
            <span class="summary-label">Terrain preference</span>
            <span class="summary-value">${summary.terrain_preference || "unknown"}</span>
          </div>
        </div>
      </section>
      <section class="summary-block">
        <p class="eyebrow">Shoes we detected</p>
        <div class="summary-grid">
          <div class="summary-tile">
            <span class="summary-label">Detected shoes</span>
            <span class="summary-value">${formatCount(detectedShoes)}</span>
          </div>
          <div class="summary-tile">
            <span class="summary-label">Manual shoes</span>
            <span class="summary-value">${formatCount(rotationSummary.manual_count)}</span>
          </div>
          <div class="summary-tile">
            <span class="summary-label">Imported only</span>
            <span class="summary-value">${formatCount(rotationSummary.imported_count)}</span>
          </div>
          <div class="summary-tile">
            <span class="summary-label">Mapped shoes</span>
            <span class="summary-value">${formatCount(rotationSummary.mapped_count)}</span>
          </div>
          <div class="summary-tile">
            <span class="summary-label">Unmapped shoes</span>
            <span class="summary-value">${formatCount(rotationSummary.unmapped_count)}</span>
          </div>
        </div>
      </section>
      <section class="summary-block">
        <p class="eyebrow">What’s missing</p>
        <div class="summary-tile field-wide">
          <span class="summary-label">Data gaps</span>
          ${formatList(coverage.missing_signals || [])}
        </div>
      </section>
    </div>
  `;
  document.getElementById("profile-preferred-terrain").value = overrides.preferred_terrain || "";
  document.getElementById("profile-weekly-override").value = overrides.weekly_mileage_override_km ?? "";
  document.getElementById("profile-notes").value = overrides.notes || "";
  const targetSet = new Set(overrides.target_contexts || []);
  document.querySelectorAll(".checkbox-row input[type='checkbox']").forEach((checkbox) => {
    checkbox.checked = targetSet.has(checkbox.value);
  });
}

function canEditShoe(shoe) {
  // All shoes can be edited now - imported shoes will create OwnedShoe records on first edit
  return true;
}

function renderRotation() {
  if (!personalizeState.rotation.length) {
    rotationTableBody.innerHTML = `<tr><td colspan="6">No shoes detected yet. Add a shoe manually or import activity history.</td></tr>`;
    renderUnmappedShoes();
    return;
  }
  rotationTableBody.innerHTML = personalizeState.rotation
    .map((shoe) => `
      <tr data-shoe-id="${shoe.id}">
        <td>
          <div class="table-primary">${shoe.display_name}</div>
          <div class="table-note">${shoe.raw_import_name && shoe.raw_import_name !== shoe.display_name ? `Imported as ${shoe.raw_import_name}` : shoe.ride_role || "role unknown"}</div>
        </td>
        <td>${sourceKindLabel(shoe.source_kind)}</td>
        <td>${mappingStatusLabel(shoe.mapping_status)}</td>
        <td>${shoe.current_mileage_km.toFixed(1)} km</td>
        <td>
          <span class="status-badge">${statusLabel(shoe)}</span>
          <button class="small-button edit-target-btn" data-shoe-id="${shoe.id}" data-current-target="${shoe.retirement_target_km || ''}" title="Edit retirement target">✎</button>
          ${shoe.mapping_status === "unmapped" ? `<button class="small-button map-shoe-btn" data-shoe-id="${shoe.id}" data-shoe-name="${shoe.raw_import_name || shoe.display_name}" title="Map to catalog shoe">🔗</button>` : ""}
        </td>
        <td>${shoe.recent_uses_30d || 0}</td>
      </tr>
    `)
    .join("");
  
  renderUnmappedShoes();
}

function recommendationCard(item) {
  return `
    <article class="result-card">
      <header>
        <div>
          <p class="eyebrow">Personalized recommendation</p>
          <h3>${item.display_name}</h3>
        </div>
        <span class="score-badge">${item.final_score.toFixed(1)} / 100</span>
      </header>
      <div class="chip-row">
        ${chip("Role", item.facets.ride_role || "Unknown")}
        ${chip("Terrain", item.terrain || "Unknown")}
        ${chip("Cushion", item.facets.cushion_level || "Unknown")}
        ${chip("Confidence", item.confidence)}
      </div>
      <p class="support-copy">${item.explanation}</p>
      <ul class="explanation-list">
        ${(item.positive_drivers || []).map((driver) => `<li>${driver}</li>`).join("")}
      </ul>
      ${item.penalties?.length ? `<ul class="penalty-list">${item.penalties.map((penalty) => `<li>${penalty}</li>`).join("")}</ul>` : ""}
      <div class="result-actions">
        <button class="small-button" type="button" data-add-shoe="${item.shoe_id}">Add to rotation</button>
        <button class="small-button" type="button" data-feedback-like="${item.shoe_id}">Useful</button>
        <button class="small-button" type="button" data-feedback-dislike="${item.shoe_id}">Not for me</button>
      </div>
    </article>
  `;
}

function renderRecommendations(context) {
  const payload = personalizeState.recommendations[context];
  if (!payload) {
    recommendationResults.className = "card-grid empty-state";
    recommendationResults.innerHTML = `<div class="empty-panel"><p>Generate profile data to see recommendations.</p></div>`;
    recommendationMeta.textContent = "No recommendation payload loaded yet.";
    return;
  }
  recommendationMeta.className = "message-banner muted";
  recommendationMeta.textContent = `${payload.confidence.toUpperCase()} confidence. ${payload.missing_signals.join(" ") || "Data coverage is currently sufficient for this context."}`;
  recommendationResults.className = "card-grid";
  // Limit to 4 recommendations as per UX requirement
  const limitedResults = payload.results.slice(0, 4);
  recommendationResults.innerHTML = limitedResults.map(recommendationCard).join("");
}

// Render detected shoes for the mapping page (matches reference image 3)
function renderDetectedShoesForMapping() {
  if (!detectedShoesList) return;
  
  // Get shoes that need mapping (unmapped or custom entries)
  const shoesToMap = personalizeState.rotation.filter((shoe) => 
    shoe.mapping_status === "unmapped" || shoe.mapping_status === "custom"
  );
  
  if (shoesToMap.length === 0) {
    // If no shoes need mapping, show a message and enable continue
    detectedShoesList.innerHTML = `
      <div class="mapping-card">
        <div class="detected-info">
          <h3>All shoes mapped!</h3>
          <p class="detected-subtitle">Your shoes have been matched to the catalog.</p>
        </div>
      </div>
    `;
    if (continueToMappingBtn) {
      continueToMappingBtn.disabled = false;
    }
    return;
  }
  
  detectedShoesList.innerHTML = shoesToMap.map((shoe, index) => {
    const isDetected = shoe.source_kind === "detected";
    const displayName = shoe.raw_import_name || shoe.gear_name || shoe.custom_name || `Shoe ${index + 1}`;
    const matchedCatalog = shoe.mapped_catalog_shoe;
    
    return `
      <div class="mapping-card ${isDetected ? 'detected' : ''}" data-shoe-id="${shoe.id}">
        <div class="detected-info">
          <h3>DETECTED SHOE ${index + 1}</h3>
          <p class="detected-subtitle">(e.g., ${displayName})</p>
          <div class="detected-stats">
            <div class="detected-stat">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"/>
                <path d="M12 6v6l4 2"/>
              </svg>
              <span>Total Miles: ${(shoe.current_mileage_km * 0.621371).toFixed(0)} mi / ${shoe.current_mileage_km.toFixed(1)} km</span>
            </div>
            <div class="detected-stat">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="3" y="4" width="18" height="18" rx="2"/>
                <line x1="16" y1="2" x2="16" y2="6"/>
                <line x1="8" y1="2" x2="8" y2="6"/>
                <line x1="3" y1="10" x2="21" y2="10"/>
              </svg>
              <span>Last Run: ${shoe.last_used_date ? new Date(shoe.last_used_date).toLocaleDateString('en-US', {month:'short', day:'numeric'}) : 'N/A'}</span>
            </div>
            <div class="detected-stat">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
              </svg>
              <span>Avg. Pace: ${shoe.avg_pace || 'N/A'}</span>
            </div>
          </div>
        </div>
        <div class="match-section">
          <h4>MATCH TO CATALOG</h4>
          <div class="match-search">
            <input type="text" placeholder="Search official catalog..." class="catalog-search" data-shoe-id="${shoe.id}" />
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="11" cy="11" r="8"/>
              <path d="M21 21l-4.35-4.35"/>
            </svg>
          </div>
          <select class="match-select" data-shoe-id="${shoe.id}">
            <option value="">${matchedCatalog ? matchedCatalog.display_name : 'Select a match...'}</option>
            ${personalizeState.catalogShoes.map((catalogShoe) => `
              <option value="${catalogShoe.shoe_id}" ${matchedCatalog && matchedCatalog.shoe_id === catalogShoe.shoe_id ? 'selected' : ''}>
                ${catalogShoe.display_name}
              </option>
            `).join("")}
            <option value="clear">Clear / Manual Entry</option>
          </select>
          <button class="cta-primary match-btn" data-shoe-id="${shoe.id}">
            ${matchedCatalog ? 'Update Match' : 'Confirm Match'}
          </button>
        </div>
      </div>
    `;
  }).join("");
  
  // Add event listeners for mapping
  detectedShoesList.querySelectorAll(".match-btn").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      const shoeId = e.target.dataset.shoeId;
      const select = detectedShoesList.querySelector(`select[data-shoe-id="${shoeId}"]`);
      const catalogShoeId = select?.value;
      
      if (!catalogShoeId || catalogShoeId === "clear") {
        // Handle clear/manual entry
        setBanner("Shoe set to manual entry.", "info");
        renderDetectedShoesForMapping();
        return;
      }
      
      try {
        await apiFetch(`/api/rotation/shoes/${shoeId}/map`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ catalog_shoe_id: catalogShoeId }),
        });
        setBanner("Shoe mapped successfully!", "success");
        await refreshWorkspace();
        renderDetectedShoesForMapping();
      } catch (error) {
        setBanner(error.message, "error");
      }
    });
  });
}

// Legacy function - no longer used but kept for compatibility
function renderUnmappedShoes() {
  // Redirect to new mapping UI if on mapping state
  if (currentState === "mapping") {
    renderDetectedShoesForMapping();
  }
}

async function loadCatalogShoes() {
  const payload = await apiFetch("/api/catalog/shoes");
  personalizeState.catalogShoes = payload.shoes || [];
  catalogSelect.innerHTML =
    `<option value="">Choose a catalog shoe</option>` +
    personalizeState.catalogShoes
      .map((shoe) => `<option value="${shoe.shoe_id}">${shoe.display_name}</option>`)
      .join("");
  const params = new URLSearchParams(window.location.search);
  const preselected = params.get("catalog_shoe_id");
  if (preselected) {
    catalogSelect.value = preselected;
  }
}

async function bootstrapSession() {
  const payload = await apiFetch("/api/personalization/session/bootstrap", { method: "POST" });
  setBanner(
    payload.session_status === "created"
      ? "Session ready. Add shoes or import activity history so we can show exactly what data we have about you."
      : "Session restored. Continue where you left off.",
    "success",
  );
}

async function loadProfile() {
  personalizeState.profile = await apiFetch("/api/profile");
  renderProfile();
}

async function loadRotation() {
  const payload = await apiFetch("/api/rotation");
  personalizeState.rotation = payload.shoes || [];
  personalizeState.rotationSummary = payload.summary || null;
  renderRotation();
}

async function loadRecommendations(context = personalizeState.activeContext) {
  const payload = await apiFetch(`/api/recommendations/personalized?context=${encodeURIComponent(context)}`);
  personalizeState.recommendations[context] = payload;
  personalizeState.activeContext = context;
  renderRecommendations(context);
}

async function refreshWorkspace() {
  await Promise.all([loadProfile(), loadRotation()]);
  renderProfile();
  updateRecommendationsVisibility();
  await loadRecommendations(personalizeState.activeContext);
}

sourceCards.forEach((card) => {
  card.addEventListener("click", () => {
    if (card.disabled) {
      return;
    }
    switchSource(card.dataset.source);
  });
});

manualForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await apiFetch("/api/rotation/shoes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        catalog_shoe_id: catalogSelect.value || null,
        custom_brand: document.getElementById("manual-brand").value || null,
        custom_name: document.getElementById("manual-name").value || null,
        start_mileage_km: Number(document.getElementById("manual-start-mileage").value || 0),
        retirement_target_km: document.getElementById("manual-retirement-target").value
          ? Number(document.getElementById("manual-retirement-target").value)
          : null,
        notes: document.getElementById("manual-notes").value || null,
      }),
    });
    setBanner("Added the shoe to your rotation and refreshed the profile.", "success");
    manualForm.reset();
    await refreshWorkspace();
    collapseSourcePanel();
  } catch (error) {
    setBanner(error.message, "error");
  }
});

uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const fileInput = document.getElementById("import-file");
  if (!fileInput.files.length) {
    setBanner("Choose a CSV or GPX file first.", "warning");
    return;
  }
  try {
    const file = fileInput.files[0];
    const formData = new FormData();
    formData.append("file", file);
    const sourceType = file.name.toLowerCase().endsWith(".gpx") ? "gpx" : "csv";
    formData.append("source_type", sourceType);
    const payload = await apiFetch("/api/imports", {
      method: "POST",
      body: formData,
    });
    const summary = payload.summary || {};
    const warnings = payload.warnings?.length ? ` ${payload.warnings.join(" ")}` : "";
    setBanner(
      `Imported ${summary.imported_activities || 0} runs. Detected ${summary.detected_shoe_count || 0} shoe names, ${summary.mapped_shoe_count || 0} matched to the catalog, ${summary.unmapped_shoe_count || 0} still unmapped.${warnings}`.trim(),
      "success",
    );
    fileInput.value = "";
    await refreshWorkspace();
    collapseSourcePanel();
  } catch (error) {
    setBanner(error.message, "error");
  }
});

profileForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const targetContexts = Array.from(document.querySelectorAll(".checkbox-row input[type='checkbox']"))
      .filter((checkbox) => checkbox.checked)
      .map((checkbox) => checkbox.value);
    personalizeState.profile = await apiFetch("/api/profile", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        preferred_terrain: document.getElementById("profile-preferred-terrain").value || null,
        weekly_mileage_override_km: document.getElementById("profile-weekly-override").value
          ? Number(document.getElementById("profile-weekly-override").value)
          : null,
        target_contexts: targetContexts,
        notes: document.getElementById("profile-notes").value || null,
      }),
    });
    renderProfile();
    setBanner("Saved profile overrides and refreshed recommendation scoring.", "success");
    await loadRecommendations(personalizeState.activeContext);
  } catch (error) {
    setBanner(error.message, "error");
  }
});

contextTabs.forEach((tab) => {
  tab.addEventListener("click", async () => {
    contextTabs.forEach((candidate) => candidate.classList.remove("active"));
    tab.classList.add("active");
    try {
      await loadRecommendations(tab.dataset.context);
    } catch (error) {
      setBanner(error.message, "error");
    }
  });
});

// Modal for editing retirement target
const editTargetModal = document.getElementById("edit-target-modal");
const editTargetForm = document.getElementById("edit-target-form");
const editShoeIdInput = document.getElementById("edit-shoe-id");
const editRetirementTargetInput = document.getElementById("edit-retirement-target");
const modalCloseBtn = document.getElementById("modal-close-btn");
const modalCancelBtn = document.getElementById("modal-cancel-btn");

function openEditTargetModal(shoeId, currentTarget) {
  editShoeIdInput.value = shoeId;
  editRetirementTargetInput.value = currentTarget || "";
  editTargetModal.style.display = "flex";
}

function closeEditTargetModal() {
  editTargetModal.style.display = "none";
  editTargetForm.reset();
}

modalCloseBtn.addEventListener("click", closeEditTargetModal);
modalCancelBtn.addEventListener("click", closeEditTargetModal);
editTargetModal.addEventListener("click", (event) => {
  if (event.target === editTargetModal) {
    closeEditTargetModal();
  }
});

editTargetForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const shoeId = editShoeIdInput.value;
  const targetValue = editRetirementTargetInput.value;
  try {
    await apiFetch(`/api/rotation/shoes/${shoeId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        retirement_target_km: targetValue ? Number(targetValue) : null,
      }),
    });
    setBanner("Updated retirement target.", "success");
    closeEditTargetModal();
    await refreshWorkspace();
  } catch (error) {
    setBanner(error.message, "error");
  }
});

recommendationResults.addEventListener("click", async (event) => {
  const addButton = event.target.closest("[data-add-shoe]");
  const likeButton = event.target.closest("[data-feedback-like]");
  const dislikeButton = event.target.closest("[data-feedback-dislike]");
  try {
    if (addButton) {
      await apiFetch("/api/rotation/shoes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ catalog_shoe_id: addButton.dataset.addShoe }),
      });
      setBanner("Added recommendation to your rotation.", "success");
      await refreshWorkspace();
      return;
    }
    if (likeButton || dislikeButton) {
      const shoeId = (likeButton || dislikeButton).dataset.feedbackLike || (likeButton || dislikeButton).dataset.feedbackDislike;
      await apiFetch("/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          catalog_shoe_id: shoeId,
          signal: likeButton ? "like" : "dislike",
          context: personalizeState.activeContext,
        }),
      });
      setBanner("Stored your feedback and refreshed the ranking.", "success");
      await loadRecommendations(personalizeState.activeContext);
    }
  } catch (error) {
    setBanner(error.message, "error");
  }
});

// Handle edit target button clicks in rotation table
rotationTableBody.addEventListener("click", (event) => {
  const editBtn = event.target.closest(".edit-target-btn");
  const mapBtn = event.target.closest(".map-shoe-btn");
  
  if (editBtn) {
    const shoeId = editBtn.dataset.shoeId;
    const currentTarget = editBtn.dataset.currentTarget;
    openEditTargetModal(shoeId, currentTarget);
  }
  
  if (mapBtn) {
    const shoeId = mapBtn.dataset.shoeId;
    const shoeName = mapBtn.dataset.shoeName;
    openMapShoeModal(shoeId, shoeName);
  }
});

// Mapping modal elements
const mapShoeModal = document.getElementById("map-shoe-modal");
const mapShoeForm = document.getElementById("map-shoe-form");
const mapShoeIdInput = document.getElementById("map-shoe-id");
const mapImportedNameInput = document.getElementById("map-imported-name");
const mapCatalogShoeSelect = document.getElementById("map-catalog-shoe");
const mapModalCloseBtn = document.getElementById("map-modal-close-btn");
const mapModalCancelBtn = document.getElementById("map-modal-cancel-btn");

function openMapShoeModal(shoeId, shoeName) {
  mapShoeIdInput.value = shoeId;
  mapImportedNameInput.value = shoeName;
  
  // Populate catalog select
  mapCatalogShoeSelect.innerHTML = 
    `<option value="">Leave unmapped</option>` +
    personalizeState.catalogShoes
      .map((shoe) => `<option value="${shoe.shoe_id}">${shoe.display_name}</option>`)
      .join("");
  
  mapShoeModal.style.display = "flex";
}

function closeMapShoeModal() {
  mapShoeModal.style.display = "none";
  mapShoeForm.reset();
}

mapModalCloseBtn.addEventListener("click", closeMapShoeModal);
mapModalCancelBtn.addEventListener("click", closeMapShoeModal);
mapShoeModal.addEventListener("click", (event) => {
  if (event.target === mapShoeModal) {
    closeMapShoeModal();
  }
});

mapShoeForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const shoeId = mapShoeIdInput.value;
  const catalogShoeId = mapCatalogShoeSelect.value;
  
  try {
    await apiFetch(`/api/rotation/shoes/${shoeId}/map`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        catalog_shoe_id: catalogShoeId || null,
      }),
    });
    setBanner(catalogShoeId ? "Shoe mapped to catalog." : "Shoe left unmapped.", "success");
    closeMapShoeModal();
    await refreshWorkspace();
  } catch (error) {
    setBanner(error.message, "error");
  }
});

// Visualization functions
async function loadVisualizations() {
  try {
    const payload = await apiFetch("/api/visualizations");
    personalizeState.visualizations = payload;
    renderVisualizations();
    updateRecommendationsVisibility();
  } catch (error) {
    // Silently fail - visualizations are optional
    console.log("Visualizations not available:", error.message);
  }
}

function renderVisualizations() {
  const viz = personalizeState.visualizations;
  if (!viz) {
    return;
  }

  const hasData = viz.efficiency_heatmap?.length > 0 || 
                  viz.monthly_mileage?.length > 0 || 
                  viz.shoe_mileage?.length > 0;

  if (!hasData) {
    vizEmptyState.style.display = "block";
    vizEfficiency.style.display = "none";
    vizMonthly.style.display = "none";
    vizMileage.style.display = "none";
    vizPace.style.display = "none";
    vizCalendar.style.display = "none";
    return;
  }

  vizEmptyState.style.display = "none";

  // Render efficiency heatmap
  if (viz.efficiency_heatmap?.length > 0) {
    vizEfficiency.style.display = "block";
    renderEfficiencyHeatmap(viz.efficiency_heatmap);
  } else {
    vizEfficiency.style.display = "none";
  }

  // Render monthly mileage
  if (viz.monthly_mileage?.length > 0) {
    vizMonthly.style.display = "block";
    renderMonthlyMileage(viz.monthly_mileage);
  } else {
    vizMonthly.style.display = "none";
  }

  // Render shoe mileage tracker
  if (viz.shoe_mileage?.length > 0) {
    vizMileage.style.display = "block";
    renderShoeMileage(viz.shoe_mileage);
  } else {
    vizMileage.style.display = "none";
  }

  // Render pace distribution
  if (viz.pace_distribution?.length > 0) {
    vizPace.style.display = "block";
    renderPaceDistribution(viz.pace_distribution);
  } else {
    vizPace.style.display = "none";
  }

  // Render rotation calendar
  if (viz.rotation_calendar?.length > 0) {
    vizCalendar.style.display = "block";
    renderRotationCalendar(viz.rotation_calendar);
  } else {
    vizCalendar.style.display = "none";
  }
}

function renderEfficiencyHeatmap(data) {
  const maxEfficiency = Math.max(...data.map(d => d.avg_efficiency), 6);
  
  vizEfficiencyContent.innerHTML = `
    <div class="efficiency-bar-container">
      ${data.map(shoe => {
        const pct = Math.min((shoe.avg_efficiency / maxEfficiency) * 100, 100);
        return `
          <div class="efficiency-row">
            <div class="efficiency-label">
              ${shoe.display_name}
              <div class="efficiency-meta">${shoe.run_count} runs · ${shoe.total_distance_km.toFixed(0)} km</div>
            </div>
            <div class="efficiency-bar-wrap">
              <div class="efficiency-bar ${shoe.efficiency_tier}" style="width: ${pct}%"></div>
            </div>
            <div class="efficiency-value">${shoe.avg_efficiency.toFixed(2)}</div>
          </div>
        `;
      }).join("")}
    </div>
  `;
}

function renderMonthlyMileage(data) {
  // Flatten into rows: month -> shoe entries
  const rows = [];
  data.forEach(month => {
    rows.push({ type: "month", label: month.month_label, total: month.total_distance_km });
    month.shoes.forEach(shoe => {
      rows.push({ 
        type: "shoe", 
        label: shoe.gear_ref, 
        distance: shoe.distance_km, 
        pace: shoe.avg_pace_min_km,
        hr: shoe.avg_hr,
        runs: shoe.run_count 
      });
    });
  });

  vizMonthlyContent.innerHTML = `
    <table class="monthly-table">
      <thead>
        <tr>
          <th>Period</th>
          <th>Distance</th>
          <th>Avg Pace</th>
          <th>Avg HR</th>
          <th>Runs</th>
        </tr>
      </thead>
      <tbody>
        ${rows.map(row => {
          if (row.type === "month") {
            return `
              <tr style="border-top: 2px solid var(--grid-line);">
                <td><strong>${row.label}</strong></td>
                <td><strong>${row.total.toFixed(1)} km</strong></td>
                <td colspan="3"></td>
              </tr>
            `;
          } else {
            return `
              <tr>
                <td class="monthly-shoe-cell">${row.label}</td>
                <td>${row.distance.toFixed(1)} km</td>
                <td>${row.pace ? row.pace.toFixed(2) + "/km" : "-"}</td>
                <td>${row.hr ? row.hr.toFixed(0) + " bpm" : "-"}</td>
                <td>${row.runs}</td>
              </tr>
            `;
          }
        }).join("")}
      </tbody>
    </table>
  `;
}

function renderShoeMileage(data) {
  vizMileageContent.innerHTML = `
    <div class="mileage-tracker">
      ${data.map(shoe => {
        const pct = shoe.retirement_pct || 0;
        const barWidth = Math.min(pct, 100);
        return `
          <div class="mileage-row zone-${shoe.zone}">
            <div class="mileage-shoe-name">
              ${shoe.display_name}
              ${shoe.mapping_status === "unmapped" ? '<span style="color: var(--text-muted); font-size: 0.7rem;"> (unmapped)</span>' : ""}
            </div>
            <div class="mileage-bar-wrap">
              <div class="mileage-bar zone-${shoe.zone}" style="width: ${barWidth}%"></div>
            </div>
            <div class="mileage-stats">
              <span class="mileage-pct">${pct.toFixed(0)}%</span>
              <span class="mileage-km">${shoe.current_mileage_km.toFixed(0)} / ${shoe.retirement_target_km ? shoe.retirement_target_km.toFixed(0) + " km" : "no target"}</span>
            </div>
          </div>
        `;
      }).join("")}
    </div>
  `;
}

function renderPaceDistribution(data) {
  vizPaceContent.innerHTML = `
    <div class="pace-distribution">
      ${data.map(shoe => `
        <div class="pace-shoe-block">
          <div class="pace-shoe-name">${shoe.gear_ref}</div>
          ${shoe.contexts.map(ctx => {
            // Create a simple box plot visualization
            const min = ctx.min;
            const max = ctx.max;
            const q1 = ctx.q1;
            const q3 = ctx.q3;
            const median = ctx.median;
            const range = max - min || 1;
            
            const left = ((q1 - min) / range) * 100;
            const width = ((q3 - q1) / range) * 100;
            const medianPos = ((median - min) / range) * 100;
            
            return `
              <div class="pace-context-row">
                <div class="pace-context-label">${ctx.run_context}</div>
                <div class="pace-boxplot">
                  <div class="pace-box" style="left: ${left}%; width: ${width}%"></div>
                  <div class="pace-median" style="left: ${medianPos}%"></div>
                </div>
                <div class="pace-range">${min.toFixed(1)}-${max.toFixed(1)} /km</div>
              </div>
            `;
          }).join("")}
        </div>
      `).join("")}
    </div>
  `;
}

function renderRotationCalendar(data) {
  vizCalendarContent.innerHTML = `
    <div class="calendar-grid">
      ${data.map(week => `
        <div class="calendar-week">
          <div class="calendar-week-label">${week.week}</div>
          <div class="calendar-shoes">
            ${week.shoes.map(shoe => {
              const daysClass = shoe.days_used >= 4 ? "days-4" : `days-${shoe.days_used}`;
              return `
                <span class="calendar-shoe-badge ${daysClass}" title="${shoe.days_used} days, ${shoe.total_distance_km.toFixed(1)} km">
                  ${shoe.gear_ref}
                </span>
              `;
            }).join("")}
          </div>
        </div>
      `).join("")}
    </div>
  `;
}

window.addEventListener("DOMContentLoaded", async () => {
  try {
    await bootstrapSession();
    await loadCatalogShoes();
    await refreshWorkspace();
    await loadVisualizations();
    
    // Set up state transitions
    if (getStartedBtn) {
      getStartedBtn.addEventListener("click", showImport);
    }
    
    if (backToLandingBtn) {
      backToLandingBtn.addEventListener("click", showLanding);
    }
    
    if (continueToMappingBtn) {
      continueToMappingBtn.addEventListener("click", showMapping);
    }
    
    if (saveAndContinueMappingBtn) {
      saveAndContinueMappingBtn.addEventListener("click", showDashboard);
    }
    
    if (skipMappingBtn) {
      skipMappingBtn.addEventListener("click", showDashboard);
    }
    
    // Dashboard tabs
    dashboardTabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        const targetTab = tab.dataset.tab;
        
        // Update active tab
        dashboardTabs.forEach((t) => t.classList.remove("active"));
        tab.classList.add("active");
        
        // Update active content
        tabContents.forEach((content) => {
          content.classList.remove("active");
          content.style.display = "none";
        });
        const targetContent = document.getElementById(`tab-${targetTab}`);
        if (targetContent) {
          targetContent.classList.add("active");
          targetContent.style.display = "block";
        }
      });
    });
    
    // Import page: drag and drop
    if (dropZone) {
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
        const files = e.dataTransfer.files;
        if (files.length > 0) {
          handleFileUpload(files[0]);
        }
      });
      
      dropZone.addEventListener("click", () => {
        if (importFileInput) {
          importFileInput.click();
        }
      });
    }
    
    if (importFileInput) {
      importFileInput.addEventListener("change", (e) => {
        if (e.target.files.length > 0) {
          handleFileUpload(e.target.files[0]);
        }
      });
    }
    
    if (uploadBtn) {
      uploadBtn.addEventListener("click", () => {
        if (importFileInput) {
          importFileInput.click();
        }
      });
    }
    
    // Set up collapsible recommendations panel
    if (recsHeader) {
      recsHeader.addEventListener("click", toggleRecsPanel);
    }
    
    // Initialize visibility
    updateRecommendationsVisibility();
    
    // Check if user has data - if so, show dashboard directly
    if (personalizeState.hasData) {
      showDashboard();
    } else {
      showLanding();
    }
  } catch (error) {
    setBanner(error.message, "error");
  }
});

// Handle file upload for import page
async function handleFileUpload(file) {
  if (!file) return;
  
  // Show progress
  if (uploadProgress) {
    uploadProgress.style.display = "block";
  }
  
  try {
    const formData = new FormData();
    formData.append("file", file);
    const sourceType = file.name.toLowerCase().endsWith(".gpx") ? "gpx" : "csv";
    formData.append("source_type", sourceType);
    
    const payload = await apiFetch("/api/imports", {
      method: "POST",
      body: formData,
    });
    
    const summary = payload.summary || {};
    
    // Update preview panel
    if (previewMileage) {
      const km = summary.total_distance_km || 0;
      previewMileage.textContent = `${(km * 0.621371).toFixed(0)} mi / ${km.toFixed(1)} km`;
    }
    if (previewShoes) {
      previewShoes.textContent = summary.detected_shoe_count || 0;
    }
    if (previewActivities) {
      previewActivities.textContent = summary.imported_activities || 0;
    }
    if (previewDateRange && summary.date_range) {
      previewDateRange.textContent = `${summary.date_range.start} - ${summary.date_range.end}`;
    }
    
    // Enable continue button
    if (continueToMappingBtn) {
      continueToMappingBtn.disabled = false;
    }
    
    setBanner(
      `Imported ${summary.imported_activities || 0} runs. Detected ${summary.detected_shoe_count || 0} shoes.`,
      "success"
    );
    
    // Refresh workspace to get new data
    await refreshWorkspace();
  } catch (error) {
    setBanner(error.message, "error");
  } finally {
    if (uploadProgress) {
      uploadProgress.style.display = "none";
    }
  }
}
