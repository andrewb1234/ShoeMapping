const state = {
  shoes: [],
  brands: [],
  selectedShoeId: null,
  selectedBrand: null,
  terrain: "Both",
  rejectedShoes: [], // Track rejected shoe IDs
  currentQuery: null, // Track current search query
};

const terrainSelect = document.getElementById("terrain-select");
const brandSelect = document.getElementById("brand-select");
const shoeSelect = document.getElementById("shoe-select");
const matchButton = document.getElementById("match-button");
const shoeCount = document.getElementById("shoe-count");
const currentTerrain = document.getElementById("current-terrain");
const statusPill = document.getElementById("status-pill");
const matchedTitle = document.getElementById("matched-title");
const matchedShoe = document.getElementById("matched-shoe");
const recommendations = document.getElementById("recommendations");

// Statistics Modal
const statisticsOverlay = document.getElementById("statistics-overlay");
const statisticsTitle = document.getElementById("statistics-title");
const statisticsContent = document.getElementById("statistics-content");
const closeStatisticsBtn = document.getElementById("close-statistics-btn");

// How It Works Modal
const howItWorksBtn = document.getElementById("how-it-works-btn");
const howItWorksOverlay = document.getElementById("how-it-works-overlay");
const closeModalBtn = document.getElementById("close-modal-btn");

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

function formatMetricValue(value, key) {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  if (typeof value === "number") {
    let formattedValue = Number.isInteger(value) ? String(value) : value.toFixed(1);
    
    // Add units based on the metric key
    if (key === "Weight") {
      return formattedValue + "g";
    } else if (key === "Drop" || key === "Heel stack" || key === "Forefoot stack") {
      return formattedValue + "mm";
    } else if (key === "Torsional rigidity") {
      // Add context for rigidity (assuming 1-5 scale where higher is stiffer)
      const rigidityLevel = value <= 2 ? "(Flexible)" : value <= 3 ? "(Moderate)" : "(Stiff)";
      return `${formattedValue}/5 ${rigidityLevel}`;
    }
    return formattedValue;
  }
  return String(value);
}

function renderMetricGridContent(values, keys) {
  return keys
    .filter((key) => values[key] !== undefined)
    .map(
      (key) => `
        <div class="detail-item">
          <span class="detail-label">${escapeHtml(key)}</span>
          <span class="detail-value">${escapeHtml(formatMetricValue(values[key], key))}</span>
        </div>
      `,
    )
    .join("");
}

function renderMetricGrid(container, values, keys) {
  container.innerHTML = renderMetricGridContent(values, keys);
}

function renderMatchedShoe(shoe, result) {
  matchedTitle.textContent = shoe ? shoe.shoe_name : "Choose a shoe to begin";

  if (!shoe) {
    matchedShoe.className = "detail-grid empty-state";
    matchedShoe.innerHTML = `<p>Select a shoe, choose a terrain, and click <strong>Find similar shoes</strong>.</p>`;
    return;
  }

  matchedShoe.className = "detail-grid";
  
  // Create URL link if source_url exists
  const urlLink = shoe.source_url 
    ? `<a href="${escapeHtml(shoe.source_url)}" target="_blank" rel="noopener noreferrer" class="url-link">View RunRepeat Review →</a>`
    : '';
  
  const metricsHtml = renderMetricGridContent({
    Brand: shoe.brand,
    Terrain: shoe.terrain || "—",
    "Audience verdict": shoe.audience_verdict ?? "—",
    "Similar shoes found": result.recommendations.length,
  }, ["Brand", "Terrain", "Audience verdict", "Similar shoes found"]);
  
  matchedShoe.innerHTML = metricsHtml + urlLink;
}

function convertDistanceToMatchPercentage(distance, similarityScore) {
  // Handle both supervised model (similarity_score) and K-Means (distance)
  if (similarityScore !== undefined && similarityScore !== null) {
    // Supervised model: similarity_score is already 0-100
    return Math.round(similarityScore);
  }
  
  // K-Means: Convert Euclidean distance to match percentage
  // Distance is in scaled feature space, not normalized 0-1
  // We'll use a more appropriate scaling: higher distance = lower match
  console.log(`Raw distance: ${distance}`); // Debug logging
  const maxReasonableDistance = 10.0; // Adjust based on actual distances
  const normalizedDistance = Math.min(distance / maxReasonableDistance, 1.0);
  const matchPercentage = Math.max(0, (1 - normalizedDistance) * 100);
  const result = Math.round(matchPercentage);
  console.log(`Converted to ${result}% match`); // Debug logging
  return result;
}

function renderRecommendations(items) {
  if (!items.length) {
    recommendations.className = "recommendation-list empty-state";
    recommendations.innerHTML = `<p>No recommendations were returned.</p>`;
    return;
  }

  recommendations.className = "recommendation-list";
  recommendations.innerHTML = items
    .map((item, index) => {
      const featureValues = item.feature_values || {};
      const matchPercentage = convertDistanceToMatchPercentage(item.distance_to_query, item.similarity_score);
      
      // Handle both supervised and K-Means outputs
      const chipValues = [];
      
      // For supervised model, use terrain and audience_verdict if available
      if (item.terrain) {
        chipValues.push(["Terrain", item.terrain]);
      }
      if (item.audience_verdict !== undefined && item.audience_verdict !== null) {
        chipValues.push(["Audience Score", item.audience_verdict]);
      }
      
      // For K-Means, use feature_values
      if (Object.keys(featureValues).length > 0) {
        chipValues.push(
          ["Drop", featureValues.Drop],
          ["Heel stack", featureValues["Heel stack"]],
          ["Forefoot stack", featureValues["Forefoot stack"]],
          ["Weight", featureValues.Weight],
          ["Torsional rigidity", featureValues["Torsional rigidity"]]
        );
      }
      
      const chipValuesHtml = chipValues
        .filter(([, value]) => value !== null && value !== undefined)
        .map(([label, value]) => `<span class="chip">${escapeHtml(label)}: ${escapeHtml(formatMetricValue(value, label))}</span>`)
        .join("");

      // Create URL link - for supervised model, we need to get it from the catalog
      const urlLink = item.source_url 
        ? `<a href="${escapeHtml(item.source_url)}" target="_blank" rel="noopener noreferrer" class="url-link">View Review →</a>`
        : '';

      return `
        <article class="recommendation-card" data-shoe-id="${escapeHtml(item.shoe_id || '')}" data-index="${index}">
          <button class="replace-button" onclick="replaceShoe('${escapeHtml(item.shoe_id || '')}', ${index})" title="Replace this shoe">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="8" y1="8" x2="16" y2="16"></line>
              <line x1="16" y1="8" x2="8" y2="16"></line>
            </svg>
            <span>Replace</span>
          </button>
          <div class="recommendation-header">
            <div>
              <h4 class="recommendation-title">${escapeHtml(item.shoe_name || item.display_name || '')}</h4>
              <p class="recommendation-subtitle">${escapeHtml(item.brand)} · ${matchPercentage}% Match</p>
            </div>
            <span class="chip match-score" onclick="showStatistics('${escapeHtml(item.shoe_id || '')}')" title="View detailed statistics">${matchPercentage}%</span>
          </div>
          <div class="chip-row">${chipValuesHtml || '<span class="chip muted-card">No feature values</span>'}</div>
          ${urlLink}
        </article>
      `;
    })
    .join("");
}

function populateBrandOptions(brands, selectedBrand = null) {
  brandSelect.innerHTML = brands
    .map((brand) => {
      const selected = brand === selectedBrand ? "selected" : "";
      return `<option value="${escapeHtml(brand)}" ${selected}>${escapeHtml(brand)}</option>`;
    })
    .join("");

  brandSelect.disabled = brands.length === 0;
  
  if (!selectedBrand && brands.length > 0) {
    brandSelect.value = brands[0];
    state.selectedBrand = brands[0];
    populateShoeOptionsForBrand(brands[0]);
  }
}

function populateShoeOptionsForBrand(brand) {
  const brandShoes = state.shoes.filter((shoe) => shoe.brand === brand);
  
  shoeSelect.innerHTML = brandShoes
    .map((shoe) => {
      const selected = shoe.shoe_id === state.selectedShoeId ? "selected" : "";
      return `<option value="${escapeHtml(shoe.shoe_id)}" ${selected}>${escapeHtml(shoe.display_name)}</option>`;
    })
    .join("");

  shoeSelect.disabled = brandShoes.length === 0;
  
  if (brandShoes.length > 0 && !state.selectedShoeId) {
    shoeSelect.value = brandShoes[0].shoe_id;
    state.selectedShoeId = brandShoes[0].shoe_id;
  }
  
  matchButton.disabled = brandShoes.length === 0;
}

async function loadShoes() {
  const terrain = currentTerrainSelection();
  state.terrain = terrain;
  setStatus(`Loading ${terrain === "Both" ? "all" : terrain.toLowerCase()} shoes…`);

  brandSelect.disabled = true;
  shoeSelect.disabled = true;
  matchButton.disabled = true;
  brandSelect.innerHTML = `<option>Loading brands…</option>`;
  shoeSelect.innerHTML = `<option>Select a brand first</option>`;

  const response = await fetch(`/api/shoes${terrainQueryParam(terrain)}`);
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Failed to load shoes");
  }

  const data = await response.json();
  state.shoes = data.shoes || [];
  
  // Extract unique brands
  const brands = [...new Set(state.shoes.map((shoe) => shoe.brand))].sort();
  state.brands = brands;
  
  populateBrandOptions(brands, state.selectedBrand);
  setStatus(`Loaded ${data.count ?? state.shoes.length} shoes from ${brands.length} brands`);
}

async function runMatcher() {
  if (!shoeSelect.value) {
    setStatus("Choose a shoe first", "error");
    return;
  }

  // Reset rejected shoes for new search
  state.rejectedShoes = [];
  state.currentQuery = shoeSelect.value;

  const selectedTerrain = currentTerrainSelection();
  const payload = {
    shoe_id: shoeSelect.value,
    n_neighbors: 5, // Always show 5 shoes
    n_clusters: 4, // Use 4 clusters based on elbow method
    rejected: state.rejectedShoes, // Send rejected shoes list
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

brandSelect.addEventListener("change", () => {
  state.selectedBrand = brandSelect.value || null;
  state.selectedShoeId = null; // Reset shoe selection when brand changes
  populateShoeOptionsForBrand(state.selectedBrand);
});

shoeSelect.addEventListener("change", () => {
  state.selectedShoeId = shoeSelect.value || null;
});

terrainSelect.addEventListener("change", async () => {
  try {
    state.selectedBrand = null;
    state.selectedShoeId = null;
    await loadShoes();
  } catch (error) {
    console.error(error);
    setStatus(error.message || "Could not load shoes", "error");
  }
});

matchButton.addEventListener("click", runMatcher);

// How It Works Modal Functions
function openModal() {
  howItWorksOverlay.classList.remove("hidden");
  document.body.style.overflow = "hidden"; // Prevent background scrolling
}

function closeModal() {
  howItWorksOverlay.classList.add("hidden");
  document.body.style.overflow = ""; // Restore scrolling
}

// Modal Event Listeners
howItWorksBtn.addEventListener("click", openModal);
closeModalBtn.addEventListener("click", closeModal);

// Close modal when clicking backdrop
howItWorksOverlay.addEventListener("click", (event) => {
  if (event.target === howItWorksOverlay || event.target.classList.contains("modal-backdrop")) {
    closeModal();
  }
});

// Close modal with Escape key
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !howItWorksOverlay.classList.contains("hidden")) {
    closeModal();
  }
});

window.addEventListener("DOMContentLoaded", async () => {
  try {
    await loadShoes();
    if (brandSelect.value && shoeSelect.value) {
      renderMatchedShoe(null, { recommendations: [] });
    }
  } catch (error) {
    console.error(error);
    setStatus(error.message || "Failed to initialize", "error");
    recommendations.innerHTML = `<div class="empty-state error-state"><p>${escapeHtml(error.message || "Failed to load initial shoe list")}</p></div>`;
  }
});

async function replaceShoe(shoeId, index) {
  if (!shoeId || !state.currentQuery) {
    setStatus("Cannot replace shoe - no active search", "error");
    return;
  }

  // Add the shoe to rejected list
  state.rejectedShoes.push(shoeId);

  const selectedTerrain = currentTerrainSelection();
  const payload = {
    shoe_id: state.currentQuery,
    n_neighbors: 5,
    n_clusters: 4,
    rejected: state.rejectedShoes,
  };

  if (selectedTerrain !== "Both") {
    payload.terrain = selectedTerrain;
  }

  setLoading(true);
  setStatus("Finding replacement…");

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
      const detail = error?.detail || "Failed to get replacement";
      throw new Error(detail);
    }

    const result = await response.json();
    
    // Find the replacement shoe (first one not already displayed)
    const currentCards = document.querySelectorAll('.recommendation-card');
    const currentShoeIds = Array.from(currentCards).map(card => card.dataset.shoeId);
    const replacementShoe = result.recommendations.find(rec => !currentShoeIds.includes(rec.shoe_id));
    
    if (replacementShoe) {
      // Replace only the shoe at the specified index
      const featureValues = replacementShoe.feature_values || {};
      const matchPercentage = convertDistanceToMatchPercentage(replacementShoe.distance_to_query, replacementShoe.similarity_score);
      
      // Handle both supervised and K-Means outputs
      const chipValues = [];
      
      // For supervised model, use terrain and audience_verdict if available
      if (replacementShoe.terrain) {
        chipValues.push(["Terrain", replacementShoe.terrain]);
      }
      if (replacementShoe.audience_verdict !== undefined && replacementShoe.audience_verdict !== null) {
        chipValues.push(["Audience Score", replacementShoe.audience_verdict]);
      }
      
      // For K-Means, use feature_values
      if (Object.keys(featureValues).length > 0) {
        chipValues.push(
          ["Drop", featureValues.Drop],
          ["Heel stack", featureValues["Heel stack"]],
          ["Forefoot stack", featureValues["Forefoot stack"]],
          ["Weight", featureValues.Weight],
          ["Torsional rigidity", featureValues["Torsional rigidity"]]
        );
      }
      
      const chipValuesHtml = chipValues
        .filter(([, value]) => value !== null && value !== undefined)
        .map(([label, value]) => `<span class="chip">${escapeHtml(label)}: ${escapeHtml(formatMetricValue(value, label))}</span>`)
        .join("");

      // Create URL link
      const urlLink = replacementShoe.source_url 
        ? `<a href="${escapeHtml(replacementShoe.source_url)}" target="_blank" rel="noopener noreferrer" class="url-link">View Review →</a>`
        : '';

      // Create the replacement card HTML
      const replacementCard = document.createElement('article');
      replacementCard.className = 'recommendation-card';
      replacementCard.dataset.shoeId = replacementShoe.shoe_id;
      replacementCard.dataset.index = index;
      replacementCard.innerHTML = `
        <button class="replace-button" onclick="replaceShoe('${escapeHtml(replacementShoe.shoe_id || '')}', ${index})" title="Replace this shoe">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="8" y1="8" x2="16" y2="16"></line>
            <line x1="16" y1="8" x2="8" y2="16"></line>
          </svg>
          <span>Replace</span>
        </button>
        <div class="recommendation-header">
          <div>
            <h4 class="recommendation-title">${escapeHtml(replacementShoe.shoe_name || replacementShoe.display_name || '')}</h4>
            <p class="recommendation-subtitle">${escapeHtml(replacementShoe.brand)} · ${matchPercentage}% Match</p>
          </div>
          <span class="chip match-score" onclick="showStatistics('${escapeHtml(replacementShoe.shoe_id || '')}')" title="View detailed statistics">${matchPercentage}%</span>
        </div>
        <div class="chip-row">${chipValuesHtml || '<span class="chip muted-card">No feature values</span>'}</div>
        ${urlLink}
      `;
      
      // Replace the card at the specified index
      if (currentCards[index]) {
        currentCards[index].replaceWith(replacementCard);
      }
    }
    
    setStatus(`Found replacement`);
  } catch (error) {
    console.error(error);
    setStatus(error.message || "Failed to replace shoe", "error");
    
    // Remove the shoe from rejected list if the request failed
    const index = state.rejectedShoes.indexOf(shoeId);
    if (index > -1) {
      state.rejectedShoes.splice(index, 1);
    }
  } finally {
    setLoading(false);
  }
}

// Statistics Modal Functions
async function showStatistics(shoeId) {
  if (!shoeId) return;
  
  try {
    // Fetch detailed statistics from the API
    const response = await fetch(`/api/shoe/${shoeId}/statistics`);
    if (!response.ok) {
      throw new Error('Failed to fetch shoe statistics');
    }
    
    const data = await response.json();
    const labResults = data.lab_test_results || {};
    
    statisticsTitle.textContent = `${data.shoe_name} - Detailed Statistics`;
    
    // Build statistics HTML from lab results
    let statsHtml = '';
    
    // Group and display metrics
    const metrics = [
      { key: 'Drop', label: 'Heel-to-Toe Drop' },
      { key: 'Heel stack', label: 'Heel Stack Height' },
      { key: 'Forefoot stack', label: 'Forefoot Stack Height' },
      { key: 'Weight', label: 'Weight' },
      { key: 'Torsional rigidity', label: 'Torsional Rigidity' },
      { key: 'Energy return heel', label: 'Energy Return (Heel)' },
      { key: 'Energy return forefoot', label: 'Energy Return (Forefoot)' },
      { key: 'Midsole softness heel', label: 'Midsole Softness (Heel)' },
      { key: 'Midsole softness forefoot', label: 'Midsole Softness (Forefoot)' },
      { key: 'Flexibility', label: 'Flexibility' },
      { key: 'Breathability', label: 'Breathability' },
      { key: 'Durability', label: 'Durability' },
      { key: 'Comfort', label: 'Comfort' },
      { key: 'Stability', label: 'Stability' },
    ];
    
    // Basic info section
    statsHtml += `
      <div class="detail-item">
        <span class="detail-label">Brand</span>
        <span class="detail-value">${escapeHtml(data.brand)}</span>
      </div>
      <div class="detail-item">
        <span class="detail-label">Terrain</span>
        <span class="detail-value">${escapeHtml(labResults.Terrain || '—')}</span>
      </div>
      <div class="detail-item">
        <span class="detail-label">Audience Verdict</span>
        <span class="detail-value">${data.audience_verdict ? data.audience_verdict + '/100' : '—'}</span>
      </div>
    `;
    
    // Add separator
    statsHtml += '<div style="grid-column: 1 / -1; height: 1px; background: var(--border); margin: 12px 0;"></div>';
    
    // Lab test results
    metrics.forEach(metric => {
      const value = labResults[metric.key];
      if (value !== undefined && value !== null) {
        statsHtml += `
          <div class="detail-item">
            <span class="detail-label">${escapeHtml(metric.label)}</span>
            <span class="detail-value">${escapeHtml(formatMetricValue(value, metric.key))}</span>
          </div>
        `;
      }
    });
    
    // If no lab results available
    if (!statsHtml.includes('detail-value')) {
      statsHtml = '<p>No detailed statistics available for this shoe.</p>';
    }
    
    statisticsContent.innerHTML = statsHtml;
    statisticsOverlay.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
    
  } catch (error) {
    console.error('Error fetching statistics:', error);
    statisticsContent.innerHTML = '<p>Failed to load shoe statistics.</p>';
    statisticsOverlay.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
  }
}

function closeStatisticsModal() {
  statisticsOverlay.classList.add('hidden');
  document.body.style.overflow = '';
}

// Statistics Modal Event Listeners
closeStatisticsBtn.addEventListener('click', closeStatisticsModal);

// Close statistics modal when clicking backdrop
statisticsOverlay.addEventListener('click', (event) => {
  if (event.target === statisticsOverlay || event.target.classList.contains('modal-backdrop')) {
    closeStatisticsModal();
  }
});

// Close statistics modal with Escape key
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && !statisticsOverlay.classList.contains('hidden')) {
    closeStatisticsModal();
  }
});
