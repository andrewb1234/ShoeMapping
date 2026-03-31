const state = {
  shoes: [],
  brands: [],
  selectedShoeId: null,
  selectedBrand: null,
  terrain: "Both",
  rejectedShoes: [],
  currentQuery: null,
};

// DOM Elements
const terrainButtons = document.querySelectorAll('.terrain-btn');
const brandSelect = document.getElementById("brand-select");
const shoeSelect = document.getElementById("shoe-select");
const matchButton = document.getElementById("match-button");
const statusPill = document.getElementById("status-pill");
const matchedTitle = document.getElementById("matched-title");
const matchedSubtitle = document.getElementById("matched-subtitle");
const anchorStats = document.getElementById("anchor-stats");
const recommendations = document.getElementById("recommendations");

// Modal Elements
const howItWorksBtn = document.getElementById("how-it-works-btn");
const howItWorksOverlay = document.getElementById("how-it-works-overlay");
const closeModalBtn = document.getElementById("close-modal-btn");
const statisticsOverlay = document.getElementById("statistics-overlay");
const statisticsTitle = document.getElementById("statistics-title");
const statisticsContent = document.getElementById("statistics-content");
const closeStatisticsBtn = document.getElementById("close-statistics-btn");

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
  matchButton.textContent = isLoading ? "Matching…" : "Find Matches";
}

function formatMetricValue(value, key) {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  if (typeof value === "number") {
    let formattedValue = Number.isInteger(value) ? String(value) : value.toFixed(1);
    
    if (key === "Weight") {
      return formattedValue + "g";
    } else if (key === "Drop" || key === "Heel stack" || key === "Forefoot stack") {
      return formattedValue + "mm";
    } else if (key === "Torsional rigidity") {
      const rigidityLevel = value <= 2 ? "(Flexible)" : value <= 3 ? "(Moderate)" : "(Stiff)";
      return `${formattedValue}/5 ${rigidityLevel}`;
    }
    return formattedValue;
  }
  return String(value);
}

function getTerrainIcon(terrain) {
  if (terrain === "Road") {
    return '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="4" y1="12" x2="20" y2="12"></line></svg>';
  } else if (terrain === "Trail") {
    return '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 7h8l-1 9H4l-1-9h8"></path><path d="M8 12v-2l2-2 2 2v2"></path></svg>';
  }
  return '';
}

function renderMatchedShoe(shoe, result) {
  matchedTitle.textContent = shoe ? shoe.shoe_name : "Choose a shoe to begin";
  matchedSubtitle.textContent = shoe ? shoe.brand : "Select a shoe and click 'Find Matches'";

  if (!shoe) {
    anchorStats.innerHTML = `
      <div class="stat-gauge">
        <div class="gauge-circle" style="--gauge-percent: 0deg">
          <span class="gauge-value">—</span>
        </div>
        <span class="gauge-label">Matches Found</span>
      </div>
    `;
    return;
  }

  const matchCount = result.recommendations?.length || 0;
  const audienceScore = shoe.audience_verdict || 0;
  
  anchorStats.innerHTML = `
    <div class="stat-gauge">
      <div class="gauge-circle" style="--gauge-percent: ${Math.min(matchCount * 36, 360)}deg">
        <span class="gauge-value">${matchCount}</span>
      </div>
      <span class="gauge-label">Matches Found</span>
    </div>
    ${audienceScore ? `
    <div class="stat-gauge">
      <div class="gauge-circle" style="--gauge-percent: ${audienceScore * 3.6}deg">
        <span class="gauge-value">${audienceScore}</span>
      </div>
      <span class="gauge-label">Audience Score</span>
    </div>
    ` : ''}
  `;
}

function convertDistanceToMatchPercentage(distance, similarityScore) {
  if (similarityScore !== undefined && similarityScore !== null) {
    return Math.round(similarityScore);
  }
  
  const maxReasonableDistance = 10.0;
  const normalizedDistance = Math.min(distance / maxReasonableDistance, 1.0);
  const matchPercentage = Math.max(0, (1 - normalizedDistance) * 100);
  return Math.round(matchPercentage);
}

function renderRecommendations(items) {
  if (!items.length) {
    recommendations.className = "recommendations-grid empty-state";
    recommendations.innerHTML = `
      <div class="empty-state">
        <p>No recommendations were returned.</p>
      </div>
    `;
    return;
  }

  recommendations.className = "recommendations-grid";
  recommendations.innerHTML = items
    .map((item, index) => {
      const featureValues = item.feature_values || {};
      const matchPercentage = convertDistanceToMatchPercentage(item.distance_to_query, item.similarity_score);
      const terrain = item.terrain || featureValues.Terrain;
      const audienceScore = item.audience_verdict;
      
      return `
        <article class="performance-card" data-shoe-id="${escapeHtml(item.shoe_id || '')}" data-index="${index}">
          <div class="card-image">
            <span>Shoe Image</span>
            <div class="match-badge" onclick="showStatistics('${escapeHtml(item.shoe_id || '')}')" title="View detailed statistics">
              ${matchPercentage}%
            </div>
          </div>
          <div class="card-content">
            <h4 class="card-title">${escapeHtml(item.shoe_name || item.display_name || '')}</h4>
            <p class="card-subtitle">${escapeHtml(item.brand)}</p>
            
            <div class="card-tags">
              ${terrain ? `
                <span class="tag ${terrain === 'Road' ? 'terrain-road' : 'terrain-trail'}">
                  ${getTerrainIcon(terrain)} ${terrain}
                </span>
              ` : ''}
              ${audienceScore ? `
                <span class="tag">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="10"></circle>
                    <path d="M12 6v6l4 2"></path>
                  </svg>
                  Score: ${audienceScore}
                </span>
              ` : ''}
            </div>
            
            ${item.source_url ? `
              <a href="${escapeHtml(item.source_url)}" target="_blank" rel="noopener noreferrer" class="review-link">
                View Full Review →
              </a>
            ` : ''}
          </div>
          
          <button class="replace-btn" onclick="replaceShoe('${escapeHtml(item.shoe_id || '')}', ${index})" title="Replace this shoe">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="8" y1="8" x2="16" y2="16"></line>
              <line x1="16" y1="8" x2="8" y2="16"></line>
            </svg>
          </button>
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
  const terrain = state.terrain;
  setStatus(`Loading ${terrain === "Both" ? "all" : terrain.toLowerCase()} shoes…`);

  brandSelect.disabled = true;
  shoeSelect.disabled = true;
  matchButton.disabled = true;
  brandSelect.innerHTML = `<option>Loading brands…</option>`;
  shoeSelect.innerHTML = `<option>Select a brand first</option>`;

  const response = await fetch(`/api/shoes${terrain === "Both" ? "" : `?terrain=${terrain}`}`);
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Failed to load shoes");
  }

  const data = await response.json();
  state.shoes = data.shoes || [];
  
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

  state.rejectedShoes = [];
  state.currentQuery = shoeSelect.value;

  const payload = {
    shoe_id: shoeSelect.value,
    n_neighbors: 5,
    n_clusters: 4,
    rejected: state.rejectedShoes,
  };

  if (state.terrain !== "Both") {
    payload.terrain = state.terrain;
  }

  setLoading(true);
  setStatus("Finding similar shoes…");
  recommendations.innerHTML = `
    <div class="empty-state">
      <p>Analyzing shoe characteristics…</p>
    </div>
  `;

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
      terrain: state.terrain === "Both" ? result.terrain : state.terrain,
      audience_verdict: result.matched_shoe?.audience_verdict ?? null,
    };

    renderMatchedShoe(matched, result);
    renderRecommendations(result.recommendations || []);
    setStatus(`Found ${result.recommendations?.length || 0} matches`);
  } catch (error) {
    console.error(error);
    setStatus(error.message || "Something went wrong", "error");
    recommendations.className = "recommendations-grid empty-state error-state";
    recommendations.innerHTML = `
      <div class="empty-state">
        <p>${escapeHtml(error.message || "Unexpected error")}</p>
      </div>
    `;
  } finally {
    setLoading(false);
  }
}

async function replaceShoe(shoeId, index) {
  if (!shoeId || !state.currentQuery) {
    setStatus("Cannot replace shoe - no active search", "error");
    return;
  }

  state.rejectedShoes.push(shoeId);

  const payload = {
    shoe_id: state.currentQuery,
    n_neighbors: 5,
    n_clusters: 4,
    rejected: state.rejectedShoes,
  };

  if (state.terrain !== "Both") {
    payload.terrain = state.terrain;
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
    
    const currentCards = document.querySelectorAll('.performance-card');
    const currentShoeIds = Array.from(currentCards).map(card => card.dataset.shoeId);
    const replacementShoe = result.recommendations.find(rec => !currentShoeIds.includes(rec.shoe_id));
    
    if (replacementShoe) {
      const matchPercentage = convertDistanceToMatchPercentage(replacementShoe.distance_to_query, replacementShoe.similarity_score);
      const terrain = replacementShoe.terrain;
      const audienceScore = replacementShoe.audience_verdict;
      
      const replacementCard = document.createElement('article');
      replacementCard.className = 'performance-card';
      replacementCard.dataset.shoeId = replacementShoe.shoe_id;
      replacementCard.dataset.index = index;
      replacementCard.innerHTML = `
        <div class="card-image">
          <span>Shoe Image</span>
          <div class="match-badge" onclick="showStatistics('${escapeHtml(replacementShoe.shoe_id || '')}')" title="View detailed statistics">
            ${matchPercentage}%
          </div>
        </div>
        <div class="card-content">
          <h4 class="card-title">${escapeHtml(replacementShoe.shoe_name || replacementShoe.display_name || '')}</h4>
          <p class="card-subtitle">${escapeHtml(replacementShoe.brand)}</p>
          
          <div class="card-tags">
            ${terrain ? `
              <span class="tag ${terrain === 'Road' ? 'terrain-road' : 'terrain-trail'}">
                ${getTerrainIcon(terrain)} ${terrain}
              </span>
            ` : ''}
            ${audienceScore ? `
              <span class="tag">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <circle cx="12" cy="12" r="10"></circle>
                  <path d="M12 6v6l4 2"></path>
                </svg>
                Score: ${audienceScore}
              </span>
            ` : ''}
          </div>
          
          ${replacementShoe.source_url ? `
            <a href="${escapeHtml(replacementShoe.source_url)}" target="_blank" rel="noopener noreferrer" class="review-link">
              View Full Review →
            </a>
          ` : ''}
        </div>
        
        <button class="replace-btn" onclick="replaceShoe('${escapeHtml(replacementShoe.shoe_id || '')}', ${index})" title="Replace this shoe">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="8" y1="8" x2="16" y2="16"></line>
            <line x1="16" y1="8" x2="8" y2="16"></line>
          </svg>
        </button>
      `;
      
      if (currentCards[index]) {
        currentCards[index].replaceWith(replacementCard);
      }
    }
    
    setStatus(`Found replacement`);
  } catch (error) {
    console.error(error);
    setStatus(error.message || "Failed to replace shoe", "error");
    
    const index = state.rejectedShoes.indexOf(shoeId);
    if (index > -1) {
      state.rejectedShoes.splice(index, 1);
    }
  } finally {
    setLoading(false);
  }
}

async function showStatistics(shoeId) {
  if (!shoeId) return;
  
  try {
    const response = await fetch(`/api/shoe/${shoeId}/statistics`);
    if (!response.ok) {
      throw new Error('Failed to fetch shoe statistics');
    }
    
    const data = await response.json();
    const labResults = data.lab_test_results || {};
    
    statisticsTitle.textContent = `${data.shoe_name} - Detailed Statistics`;
    
    let statsHtml = '';
    
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
    
    statsHtml += '<div style="grid-column: 1 / -1; height: 1px; background: var(--border-color); margin: 12px 0;"></div>';
    
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

// Event Listeners
brandSelect.addEventListener("change", () => {
  state.selectedBrand = brandSelect.value || null;
  state.selectedShoeId = null;
  populateShoeOptionsForBrand(state.selectedBrand);
});

shoeSelect.addEventListener("change", () => {
  state.selectedShoeId = shoeSelect.value || null;
});

terrainButtons.forEach(btn => {
  btn.addEventListener('click', () => {
    terrainButtons.forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    state.terrain = btn.dataset.terrain;
    state.selectedBrand = null;
    state.selectedShoeId = null;
    loadShoes();
  });
});

matchButton.addEventListener("click", runMatcher);

// Modal Event Listeners
howItWorksBtn.addEventListener('click', () => {
  howItWorksOverlay.classList.remove('hidden');
  document.body.style.overflow = 'hidden';
});

closeModalBtn.addEventListener('click', () => {
  howItWorksOverlay.classList.add('hidden');
  document.body.style.overflow = '';
});

howItWorksOverlay.addEventListener('click', (event) => {
  if (event.target === howItWorksOverlay || event.target.classList.contains('modal-backdrop')) {
    howItWorksOverlay.classList.add('hidden');
    document.body.style.overflow = '';
  }
});

closeStatisticsBtn.addEventListener('click', closeStatisticsModal);

statisticsOverlay.addEventListener('click', (event) => {
  if (event.target === statisticsOverlay || event.target.classList.contains('modal-backdrop')) {
    closeStatisticsModal();
  }
});

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') {
    if (!howItWorksOverlay.classList.contains('hidden')) {
      howItWorksOverlay.classList.add('hidden');
      document.body.style.overflow = '';
    }
    if (!statisticsOverlay.classList.contains('hidden')) {
      closeStatisticsModal();
    }
  }
});

// Initialize
window.addEventListener("DOMContentLoaded", async () => {
  try {
    await loadShoes();
    if (brandSelect.value && shoeSelect.value) {
      renderMatchedShoe(null, { recommendations: [] });
    }
  } catch (error) {
    console.error(error);
    setStatus(error.message || "Failed to initialize", "error");
    recommendations.innerHTML = `
      <div class="empty-state error-state">
        <p>${escapeHtml(error.message || "Failed to load initial shoe list")}</p>
      </div>
    `;
  }
});
