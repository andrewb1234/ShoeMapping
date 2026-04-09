const personalizeState = {
  currentSource: "manual",
  activeContext: "easy",
  profile: null,
  rotation: [],
  rotationSummary: null,
  recommendations: {},
  catalogShoes: [],
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

function renderRotation() {
  if (!personalizeState.rotation.length) {
    rotationTableBody.innerHTML = `<tr><td colspan="6">No shoes detected yet. Add a shoe manually or import activity history.</td></tr>`;
    return;
  }
  rotationTableBody.innerHTML = personalizeState.rotation
    .map((shoe) => `
      <tr>
        <td>
          <div class="table-primary">${shoe.display_name}</div>
          <div class="table-note">${shoe.raw_import_name && shoe.raw_import_name !== shoe.display_name ? `Imported as ${shoe.raw_import_name}` : shoe.ride_role || "role unknown"}</div>
        </td>
        <td>${sourceKindLabel(shoe.source_kind)}</td>
        <td>${mappingStatusLabel(shoe.mapping_status)}</td>
        <td>${shoe.current_mileage_km.toFixed(1)} km</td>
        <td><span class="status-badge">${statusLabel(shoe)}</span></td>
        <td>${shoe.recent_uses_30d || 0}</td>
      </tr>
    `)
    .join("");
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
  recommendationResults.innerHTML = payload.results.map(recommendationCard).join("");
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

window.addEventListener("DOMContentLoaded", async () => {
  try {
    await bootstrapSession();
    await loadCatalogShoes();
    await refreshWorkspace();
  } catch (error) {
    setBanner(error.message, "error");
  }
});
