const state = {
  shoes: [],
  terrain: "Both",
  selectedBrand: "",
  selectedShoeId: "",
  rejectedShoes: [],
};

const terrainButtons = Array.from(document.querySelectorAll(".segmented-button"));
const brandSelect = document.getElementById("brand-select");
const shoeSelect = document.getElementById("shoe-select");
const runButton = document.getElementById("run-match");
const statusText = document.getElementById("status-text");
const selectedShoeCard = document.getElementById("selected-shoe-card");
const recommendationsGrid = document.getElementById("recommendations-grid");
const detailDialog = document.getElementById("shoe-detail-modal");
const detailTitle = document.getElementById("detail-title");
const detailGrid = document.getElementById("detail-grid");
const closeDetailModal = document.getElementById("close-detail-modal");
const personalizationEnabled = Boolean(window.shoeMappingConfig?.personalizationEnabled);

function personalizationCta(label, shoeId) {
  if (!personalizationEnabled) {
    return `<span class="cta-secondary is-disabled" title="Set PERSONALIZATION_BASE_URL to enable the personalized flow">${label}</span>`;
  }
  const baseUrl = window.shoeMappingConfig.personalizationBaseUrl;
  return `<a class="cta-secondary" href="${baseUrl}/?catalog_shoe_id=${encodeURIComponent(shoeId)}">${label}</a>`;
}

function formatMetric(value, suffix = "") {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  return `${Number(value).toFixed(Number.isInteger(value) ? 0 : 1)}${suffix}`;
}

function setStatus(message, level = "muted") {
  statusText.textContent = message;
  statusText.className = `status-text ${level}`;
}

function chip(label, value) {
  return `<span class="chip">${label}: ${value}</span>`;
}

function similarityLabel(score) {
  return `${Math.round(score || 0)}% similar`;
}

function anonymousExplanation(item) {
  const facets = item.facets || {};
  const parts = [];
  if (facets.ride_role) {
    parts.push(`Another ${facets.ride_role} option`);
  }
  if (item.terrain) {
    parts.push(`built for ${item.terrain.toLowerCase()} use`);
  }
  if (facets.cushion_level) {
    parts.push(`with ${facets.cushion_level} cushioning`);
  }
  return `${parts.join(", ")}. Similarity is based on the shared shoe catalog rather than your personal history.`;
}

function renderSelectedShoe(shoe) {
  if (!shoe) {
    selectedShoeCard.innerHTML = `
      <p class="eyebrow">Selected shoe</p>
      <h2>Select a shoe to see its role and neighboring options.</h2>
    `;
    return;
  }
  const facets = shoe.facets || {};
  const metrics = shoe.metric_snapshot || {};
  selectedShoeCard.innerHTML = `
    <p class="eyebrow">Selected shoe</p>
    <h2>${shoe.display_name}</h2>
    <p class="support-copy">Role, terrain, and lab-derived facets from the current static catalog.</p>
    <div class="chip-row">
      ${chip("Terrain", shoe.terrain || "Unknown")}
      ${chip("Role", facets.ride_role || "Unknown")}
      ${chip("Cushion", facets.cushion_level || "Unknown")}
      ${chip("Stability", facets.stability_level || "Unknown")}
      ${chip("Weight", metrics.weight_g ? `${Math.round(metrics.weight_g)} g` : "—")}
      ${chip("Drop", metrics.drop_mm ? `${metrics.drop_mm.toFixed(1)} mm` : "—")}
    </div>
    <div class="result-actions">
      <button class="small-button" type="button" data-detail-shoe="${shoe.shoe_id}">View lab details</button>
      ${personalizationCta("Personalize around this shoe", shoe.shoe_id)}
    </div>
  `;
}

function renderRecommendations(items) {
  if (!items.length) {
    recommendationsGrid.className = "card-grid empty-state";
    recommendationsGrid.innerHTML = `<div class="empty-panel"><p>No matching shoes were returned for this filter.</p></div>`;
    return;
  }
  recommendationsGrid.className = "card-grid";
  recommendationsGrid.innerHTML = items
    .map((item) => {
      const facets = item.facets || {};
      const metrics = item.metric_snapshot || {};
      return `
        <article class="result-card">
          <header>
            <div>
              <p class="eyebrow">Catalog neighbor</p>
              <h3>${item.display_name}</h3>
            </div>
            <span class="score-badge">${similarityLabel(item.similarity_score)}</span>
          </header>
          <div class="chip-row">
            ${chip("Role", facets.ride_role || "Unknown")}
            ${chip("Terrain", item.terrain || "Unknown")}
            ${chip("Cushion", facets.cushion_level || "Unknown")}
            ${chip("Drop", metrics.drop_mm ? `${metrics.drop_mm.toFixed(1)} mm` : "—")}
          </div>
          <p class="support-copy">${anonymousExplanation(item)}</p>
          <div class="result-actions">
            <button class="small-button" type="button" data-detail-shoe="${item.shoe_id}">View lab details</button>
            <button class="small-button" type="button" data-reject-shoe="${item.shoe_id}">Swap this match</button>
            ${personalizationCta("Add in personalization flow", item.shoe_id)}
          </div>
        </article>
      `;
    })
    .join("");
}

async function loadCatalogShoes() {
  const query = state.terrain === "Both" ? "" : `?terrain=${encodeURIComponent(state.terrain)}`;
  const response = await fetch(`/api/catalog/shoes${query}`);
  if (!response.ok) {
    throw new Error("Unable to load catalog shoes.");
  }
  const payload = await response.json();
  state.shoes = payload.shoes || [];
  const brands = [...new Set(state.shoes.map((shoe) => shoe.brand))].sort();
  brandSelect.innerHTML = brands.map((brand) => `<option value="${brand}">${brand}</option>`).join("");
  state.selectedBrand = brands[0] || "";
  brandSelect.value = state.selectedBrand;
  populateShoeSelect();
  setStatus(`Loaded ${payload.count} shoes across ${brands.length} brands.`);
}

function populateShoeSelect() {
  const shoes = state.shoes.filter((shoe) => shoe.brand === state.selectedBrand);
  shoeSelect.innerHTML = shoes
    .map((shoe) => `<option value="${shoe.shoe_id}">${shoe.display_name}</option>`)
    .join("");
  state.selectedShoeId = shoes[0]?.shoe_id || "";
  shoeSelect.value = state.selectedShoeId;
  renderSelectedShoe(shoes[0]);
}

async function runMatcher() {
  if (!state.selectedShoeId) {
    return;
  }
  setStatus("Matching against the current static catalog…");
  const response = await fetch("/api/catalog/recommendations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      shoe_id: state.selectedShoeId,
      terrain: state.terrain === "Both" ? null : state.terrain,
      rejected: state.rejectedShoes,
    }),
  });
  if (!response.ok) {
    throw new Error("Unable to build recommendations.");
  }
  const payload = await response.json();
  renderSelectedShoe(payload.matched_shoe);
  renderRecommendations(payload.recommendations || []);
  setStatus(`Returned ${payload.recommendations?.length || 0} nearby shoes.`);
}

async function openDetail(shoeId) {
  const response = await fetch(`/api/catalog/shoes/${encodeURIComponent(shoeId)}`);
  if (!response.ok) {
    throw new Error("Unable to load shoe detail.");
  }
  const payload = await response.json();
  detailTitle.textContent = payload.display_name;
  const metrics = payload.lab_test_results || {};
  detailGrid.innerHTML = Object.entries(metrics)
    .slice(0, 18)
    .map(([key, value]) => `
      <div class="detail-item">
        <div class="summary-label">${key}</div>
        <div class="support-copy compact">${value}</div>
      </div>
    `)
    .join("");
  detailDialog.showModal();
}

terrainButtons.forEach((button) => {
  button.addEventListener("click", async () => {
    terrainButtons.forEach((candidate) => candidate.classList.remove("active"));
    button.classList.add("active");
    state.terrain = button.dataset.terrain;
    state.rejectedShoes = [];
    try {
      await loadCatalogShoes();
    } catch (error) {
      setStatus(error.message, "error");
    }
  });
});

brandSelect.addEventListener("change", () => {
  state.selectedBrand = brandSelect.value;
  state.rejectedShoes = [];
  populateShoeSelect();
});

shoeSelect.addEventListener("change", () => {
  state.selectedShoeId = shoeSelect.value;
  const shoe = state.shoes.find((item) => item.shoe_id === state.selectedShoeId);
  renderSelectedShoe(shoe);
});

runButton.addEventListener("click", async () => {
  try {
    await runMatcher();
  } catch (error) {
    setStatus(error.message, "error");
  }
});

recommendationsGrid.addEventListener("click", async (event) => {
  const target = event.target.closest("[data-detail-shoe], [data-reject-shoe]");
  if (!target) {
    return;
  }
  try {
    if (target.dataset.detailShoe) {
      await openDetail(target.dataset.detailShoe);
      return;
    }
    if (target.dataset.rejectShoe) {
      state.rejectedShoes.push(target.dataset.rejectShoe);
      await runMatcher();
    }
  } catch (error) {
    setStatus(error.message, "error");
  }
});

selectedShoeCard.addEventListener("click", async (event) => {
  const target = event.target.closest("[data-detail-shoe]");
  if (!target) {
    return;
  }
  try {
    await openDetail(target.dataset.detailShoe);
  } catch (error) {
    setStatus(error.message, "error");
  }
});

closeDetailModal.addEventListener("click", () => detailDialog.close());

window.addEventListener("DOMContentLoaded", async () => {
  try {
    await loadCatalogShoes();
  } catch (error) {
    setStatus(error.message, "error");
  }
});
