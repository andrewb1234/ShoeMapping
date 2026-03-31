const state = {
  shoes: [],
  selectedShoeId: null,
  terrain: "Both",
};

const terrainSelect = document.getElementById("terrain-select");
const shoeSelect = document.getElementById("shoe-select");
const matchButton = document.getElementById("match-button");
const neighborsInput = document.getElementById("neighbors-input");
const clustersInput = document.getElementById("clusters-input");
const shoeCount = document.getElementById("shoe-count");
const currentTerrain = document.getElementById("current-terrain");
const statusPill = document.getElementById("status-pill");
const clusterStatus = document.getElementById("cluster-status");
const matchedTitle = document.getElementById("matched-title");
const matchedShoe = document.getElementById("matched-shoe");
const recommendations = document.getElementById("recommendations");

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function setStatus(message, variant = "normal") {
  statusPill.textContent = message;
  statusPill.classList.toggle("error-state", variant === "error");
  clusterStatus.textContent = message;
  clusterStatus.classList.toggle("error-state", variant === "error");
}

function setLoading(isLoading) {
  matchButton.disabled = isLoading || shoeSelect.disabled;
  document.body.classList.toggle("loading", isLoading);
  matchButton.textContent = isLoading ? "Matching…" : "Find similar shoes";
}

function terrainQueryParam(terrain) {
  return terrain === "Both" ? "" : `?terrain=${encodeURIComponent(terrain)}`;
}

function currentTerrainSelection() {
  return terrainSelect.value || "Both";
}

function formatMetricValue(value) {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(1);
  }
  return String(value);
}

function renderMetricGrid(container, values, keys) {
  container.innerHTML = keys
    .filter((key) => values[key] !== undefined)
    .map(
      (key) => `
        <div class="detail-item">
          <span class="detail-label">${escapeHtml(key)}</span>
          <span class="detail-value">${escapeHtml(formatMetricValue(values[key]))}</span>
        </div>
      `,
    )
    .join("");
}

function renderMatchedShoe(shoe, result) {
  matchedTitle.textContent = shoe ? shoe.shoe_name : "Choose a shoe to begin";

  if (!shoe) {
    matchedShoe.className = "detail-grid empty-state";
    matchedShoe.innerHTML = `<p>Select a shoe, choose a terrain, and click <strong>Find similar shoes</strong>.</p>`;
    return;
  }

  matchedShoe.className = "detail-grid";
  renderMetricGrid(matchedShoe, {
    Brand: shoe.brand,
    Terrain: shoe.terrain || "—",
    "Audience verdict": shoe.audience_verdict ?? "—",
    "Cluster label": result.cluster_label,
    "Cluster size": result.cluster_size,
    "Nearest shoes": result.recommendations.length,
  }, ["Brand", "Terrain", "Audience verdict", "Cluster label", "Cluster size", "Nearest shoes"]);
}

function renderRecommendations(items) {
  if (!items.length) {
    recommendations.className = "recommendation-list empty-state";
    recommendations.innerHTML = `<p>No recommendations were returned.</p>`;
    return;
  }

  recommendations.className = "recommendation-list";
  recommendations.innerHTML = items
    .map((item) => {
      const featureValues = item.feature_values || {};
      const chipValues = [
        ["Drop", featureValues.Drop],
        ["Heel stack", featureValues["Heel stack"]],
        ["Forefoot stack", featureValues["Forefoot stack"]],
        ["Weight", featureValues.Weight],
        ["Torsional rigidity", featureValues["Torsional rigidity"]],
      ]
        .filter(([, value]) => value !== null && value !== undefined)
        .map(([label, value]) => `<span class="chip">${escapeHtml(label)}: ${escapeHtml(formatMetricValue(value))}</span>`)
        .join("");

      return `
        <article class="recommendation-card">
          <div class="recommendation-header">
            <div>
              <h4 class="recommendation-title">${escapeHtml(item.shoe_name)}</h4>
              <p class="recommendation-subtitle">${escapeHtml(item.brand)} · Cluster ${escapeHtml(item.cluster_label)} · Distance ${escapeHtml(formatMetricValue(item.distance_to_query))}</p>
            </div>
            <span class="chip">Score ${escapeHtml(item.audience_verdict ?? "—")}</span>
          </div>
          <div class="chip-row">${chipValues || '<span class="chip muted-card">No feature values</span>'}</div>
        </article>
      `;
    })
    .join("");
}

function populateShoeOptions(shoes, selectedId = null) {
  shoeSelect.innerHTML = shoes
    .map((shoe) => {
      const selected = shoe.shoe_id === selectedId ? "selected" : "";
      return `<option value="${escapeHtml(shoe.shoe_id)}" ${selected}>${escapeHtml(shoe.display_name)}</option>`;
    })
    .join("");

  shoeSelect.disabled = shoes.length === 0;
  matchButton.disabled = shoes.length === 0;

  if (!selectedId && shoes.length > 0) {
    shoeSelect.value = shoes[0].shoe_id;
  }

  state.selectedShoeId = shoeSelect.value || null;
}

async function loadShoes() {
  const terrain = currentTerrainSelection();
  state.terrain = terrain;
  currentTerrain.textContent = terrain;
  setStatus(`Loading ${terrain === "Both" ? "all" : terrain.toLowerCase()} shoes…`);

  shoeSelect.disabled = true;
  matchButton.disabled = true;
  shoeSelect.innerHTML = `<option>Loading shoes…</option>`;

  const response = await fetch(`/api/shoes${terrainQueryParam(terrain)}`);
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Failed to load shoes");
  }

  const data = await response.json();
  state.shoes = data.shoes || [];
  shoeCount.textContent = String(data.count ?? state.shoes.length);
  populateShoeOptions(state.shoes, state.selectedShoeId);
  setStatus(`Loaded ${data.count ?? state.shoes.length} shoes`);
  matchButton.disabled = state.shoes.length === 0;
}

async function runMatcher() {
  if (!shoeSelect.value) {
    setStatus("Choose a shoe first", "error");
    return;
  }

  const selectedTerrain = currentTerrainSelection();
  const payload = {
    shoe_id: shoeSelect.value,
    n_neighbors: Number(neighborsInput.value) || 5,
    n_clusters: Number(clustersInput.value) || 8,
  };

  if (selectedTerrain !== "Both") {
    payload.terrain = selectedTerrain;
  }

  setLoading(true);
  setStatus("Finding similar shoes…");
  recommendations.innerHTML = `<div class="empty-state"><p>Running clustering…</p></div>`;

  try {
    const response = await fetch("/api/recommendations", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => null);
      const detail = error?.detail || "Failed to generate recommendations";
      throw new Error(detail);
    }

    const result = await response.json();
    const matched = state.shoes.find((shoe) => shoe.shoe_id === payload.shoe_id) || {
      shoe_name: result.query,
      brand: result.matched_shoe?.brand || "",
      terrain: selectedTerrain === "Both" ? result.terrain : selectedTerrain,
      audience_verdict: result.matched_shoe?.audience_verdict ?? null,
    };

    renderMatchedShoe(matched, result);
    renderRecommendations(result.recommendations || []);
    setStatus(`Matched ${result.recommendations?.length || 0} shoes`);
  } catch (error) {
    console.error(error);
    setStatus(error.message || "Something went wrong", "error");
    recommendations.className = "recommendation-list empty-state error-state";
    recommendations.innerHTML = `<p>${escapeHtml(error.message || "Unexpected error")}</p>`;
  } finally {
    setLoading(false);
  }
}

terrainSelect.addEventListener("change", async () => {
  try {
    const previousSelection = shoeSelect.value;
    state.selectedShoeId = previousSelection;
    await loadShoes();
    if (previousSelection && Array.from(shoeSelect.options).some((option) => option.value === previousSelection)) {
      shoeSelect.value = previousSelection;
      state.selectedShoeId = previousSelection;
    }
  } catch (error) {
    console.error(error);
    setStatus(error.message || "Could not load shoes", "error");
  }
});

shoeSelect.addEventListener("change", () => {
  state.selectedShoeId = shoeSelect.value || null;
});

matchButton.addEventListener("click", runMatcher);

window.addEventListener("DOMContentLoaded", async () => {
  try {
    await loadShoes();
    if (shoeSelect.value) {
      renderMatchedShoe(null, { recommendations: [], cluster_label: "—", cluster_size: "—" });
    }
  } catch (error) {
    console.error(error);
    setStatus(error.message || "Failed to initialize", "error");
    recommendations.innerHTML = `<div class="empty-state error-state"><p>${escapeHtml(error.message || "Failed to load initial shoe list")}</p></div>`;
  }
});
