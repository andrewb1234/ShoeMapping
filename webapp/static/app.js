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
const matchesFound = document.getElementById("matches-found");
const audienceMetric = document.getElementById("audience-metric");
const audienceScore = document.getElementById("audience-score");
const anchorRadar = document.getElementById("anchor-radar");
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
  // Status popups removed - no longer showing status messages
  // statusPill.textContent = message.toUpperCase();
  // statusPill.classList.toggle("error-state", variant === "error");
}

function setLoading(isLoading) {
  matchButton.disabled = isLoading || shoeSelect.disabled;
  document.body.classList.toggle("loading", isLoading);
  matchButton.textContent = isLoading ? "ANALYZING…" : "Find Matches";
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
      const rigidityLevel = value <= 2 ? "FLEXIBLE" : value <= 3 ? "MODERATE" : "STIFF";
      return `${formattedValue}/5 ${rigidityLevel}`;
    }
    return formattedValue;
  }
  return String(value);
}

// Radar Chart Generation
function generateRadarChart(metrics, size = 200) {
  const centerX = size / 2;
  const centerY = size / 2;
  const radius = size / 2 - 30; // Increased padding
  const angles = 5; // Number of metrics
  const angleStep = (Math.PI * 2) / angles;
  
  // Define the metrics and their positions
  const metricNames = ['CUSHION', 'RESPONSIVE', 'WEIGHT', 'GRIP', 'DURABILITY'];
  const metricValues = [
    metrics.cushion || 0.5,
    metrics.responsiveness || 0.5,
    metrics.weight || 0.5,
    metrics.grip || 0.5,
    metrics.durability || 0.5
  ];
  
  let svg = `<svg viewBox="0 0 ${size} ${size}" xmlns="http://www.w3.org/2000/svg">`;
  
  // Draw grid circles
  for (let i = 1; i <= 5; i++) {
    const r = (radius / 5) * i;
    svg += `<circle cx="${centerX}" cy="${centerY}" r="${r}" fill="none" stroke="#cccccc" stroke-width="1"/>`;
  }
  
  // Draw axes
  for (let i = 0; i < angles; i++) {
    const angle = angleStep * i - Math.PI / 2;
    const x = centerX + Math.cos(angle) * radius;
    const y = centerY + Math.sin(angle) * radius;
    svg += `<line x1="${centerX}" y1="${centerY}" x2="${x}" y2="${y}" stroke="#cccccc" stroke-width="1"/>`;
  }
  
  // Draw data polygon
  let points = [];
  for (let i = 0; i < angles; i++) {
    const angle = angleStep * i - Math.PI / 2;
    const value = metricValues[i];
    const r = radius * value;
    const x = centerX + Math.cos(angle) * r;
    const y = centerY + Math.sin(angle) * r;
    points.push(`${x},${y}`);
  }
  
  svg += `<polygon points="${points.join(' ')}" fill="#2d5a3d" fill-opacity="0.3" stroke="#2d5a3d" stroke-width="2"/>`;
  
  // Draw labels with better positioning
  for (let i = 0; i < angles; i++) {
    const angle = angleStep * i - Math.PI / 2;
    const labelRadius = radius + 25; // Increased label radius
    const x = centerX + Math.cos(angle) * labelRadius;
    const y = centerY + Math.sin(angle) * labelRadius;
    
    // Adjust text anchor based on position
    let textAnchor = "middle";
    if (x < centerX - 10) textAnchor = "end";
    else if (x > centerX + 10) textAnchor = "start";
    
    svg += `<text x="${x}" y="${y}" text-anchor="${textAnchor}" dominant-baseline="middle" 
                  font-family="Roboto Mono" font-size="9" font-weight="700" fill="#666666">
              ${metricNames[i]}
            </text>`;
  }
  
  svg += `</svg>`;
  return svg;
}

function extractMetricsFromShoe(shoe) {
  // Extract or derive metrics from shoe data
  const labResults = shoe.lab_test_results || {};
  const featureValues = shoe.feature_values || {};
  
  return {
    cushion: Math.random() * 0.8 + 0.2, // Placeholder - would calculate from actual data
    responsiveness: Math.random() * 0.8 + 0.2,
    weight: Math.max(0, 1 - (parseFloat(featureValues.Weight || labResults.Weight || 300) / 500)),
    grip: shoe.terrain === 'Trail' ? 0.8 : 0.4,
    durability: Math.random() * 0.8 + 0.2
  };
}

function renderMatchedShoe(shoe, result) {
  matchedTitle.textContent = shoe ? shoe.shoe_name.toUpperCase() : "SELECT SHOE";
  matchedSubtitle.textContent = shoe ? shoe.brand.toUpperCase() : "CHOOSE A MODEL TO BEGIN ANALYSIS";

  if (!shoe) {
    matchesFound.textContent = "—";
    audienceMetric.style.display = "none";
    // Remove radar chart and replace with simple card
    anchorRadar.innerHTML = `
      <div style="display: flex; align-items: center; justify-content: center; height: 160px; background: var(--bg-canvas-warm); border: 2px solid var(--grid-line); color: var(--text-muted); font-family: var(--font-mono); font-size: 0.9rem; font-weight: 600;">
        SELECT A SHOE TO VIEW ANALYSIS
      </div>
    `;
    return;
  }

  const matchCount = result.recommendations?.length || 0;
  matchesFound.textContent = matchCount;
  
  if (shoe.audience_verdict) {
    audienceScore.textContent = shoe.audience_verdict;
    audienceMetric.style.display = "block";
  } else {
    audienceMetric.style.display = "none";
  }
  
  // Replace radar chart with simple card showing key metrics
  const featureValues = shoe.feature_values || {};
  anchorRadar.innerHTML = `
    <div style="background: var(--bg-canvas-warm); border: 2px solid var(--grid-line); padding: 24px; height: 160px; display: flex; flex-direction: column; justify-content: space-between;">
      <div>
        <div style="font-family: var(--font-mono); font-size: 0.8rem; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; color: var(--text-muted); margin-bottom: 12px;">
          PERFORMANCE PROFILE
        </div>
        <div style="display: flex; gap: 16px; flex-wrap: wrap;">
          ${featureValues.Drop ? `
            <div style="font-family: var(--font-mono); font-size: 0.9rem; font-weight: 600; color: var(--text-primary);">
              DROP: ${formatMetricValue(featureValues.Drop, 'Drop')}
            </div>
          ` : ''}
          ${featureValues.Weight ? `
            <div style="font-family: var(--font-mono); font-size: 0.9rem; font-weight: 600; color: var(--text-primary);">
              WEIGHT: ${formatMetricValue(featureValues.Weight, 'Weight')}
            </div>
          ` : ''}
          ${shoe.terrain ? `
            <div style="font-family: var(--font-mono); font-size: 0.9rem; font-weight: 600; color: var(--text-primary);">
              TERRAIN: ${shoe.terrain.toUpperCase()}
            </div>
          ` : ''}
        </div>
      </div>
      ${shoe.source_url ? `
        <a href="${escapeHtml(shoe.source_url)}" target="_blank" rel="noopener noreferrer" class="review-link" style="margin-top: auto;">
          VIEW FULL REPORT →
        </a>
      ` : ''}
    </div>
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
        <p>NO MATCHES FOUND</p>
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
      
      // Generate radar chart for this shoe
      const metrics = extractMetricsFromShoe(item);
      
      return `
        <article class="recommendation-card" data-shoe-id="${escapeHtml(item.shoe_id || '')}" data-index="${index}">
          <div class="match-readout" onclick="showStatistics('${escapeHtml(item.shoe_id || '')}')" title="View detailed statistics">
            ${matchPercentage}%
          </div>
          
          <h4 class="card-title">${escapeHtml(item.shoe_name || item.display_name || '').toUpperCase()}</h4>
          <p class="card-subtitle">${escapeHtml(item.brand).toUpperCase()}</p>
          
          <div class="card-data-tags">
            ${terrain ? `
              <span class="data-tag">[ TERRAIN: ${terrain.toUpperCase()} ]</span>
            ` : ''}
            ${audienceScore ? `
              <span class="data-tag">[ SCORE: ${audienceScore}/100 ]</span>
            ` : ''}
            ${featureValues.Drop ? `
              <span class="data-tag">[ DROP: ${formatMetricValue(featureValues.Drop, 'Drop')} ]</span>
            ` : ''}
            ${featureValues.Weight ? `
              <span class="data-tag">[ WT: ${formatMetricValue(featureValues.Weight, 'Weight')} ]</span>
            ` : ''}
          </div>
          
          ${item.source_url ? `
            <a href="${escapeHtml(item.source_url)}" target="_blank" rel="noopener noreferrer" class="review-link">
              VIEW FULL REPORT →
            </a>
          ` : ''}
          
          <button class="replace-btn" onclick="replaceShoe('${escapeHtml(item.shoe_id || '')}', ${index})" title="Replace this shoe">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
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
      return `<option value="${escapeHtml(brand)}" ${selected}>${escapeHtml(brand).toUpperCase()}</option>`;
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
      return `<option value="${escapeHtml(shoe.shoe_id)}" ${selected}>${escapeHtml(shoe.display_name).toUpperCase()}</option>`;
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
  setStatus("Analyzing shoe characteristics…");
  recommendations.innerHTML = `
    <div class="empty-state">
      <p>PROCESSING ANALYSIS…</p>
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
    setStatus(`Analysis complete: ${result.recommendations?.length || 0} matches found`);
  } catch (error) {
    console.error(error);
    setStatus(error.message || "Analysis failed", "error");
    recommendations.className = "recommendations-grid empty-state error-state";
    recommendations.innerHTML = `
      <div class="empty-state">
        <p>${escapeHtml(error.message || "System error")}</p>
      </div>
    `;
  } finally {
    setLoading(false);
  }
}

async function replaceShoe(shoeId, index) {
  if (!shoeId || !state.currentQuery) {
    setStatus("Cannot replace shoe - no active analysis", "error");
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
    
    const currentCards = document.querySelectorAll('.recommendation-card');
    const currentShoeIds = Array.from(currentCards).map(card => card.dataset.shoeId);
    const replacementShoe = result.recommendations.find(rec => !currentShoeIds.includes(rec.shoe_id));
    
    if (replacementShoe) {
      const matchPercentage = convertDistanceToMatchPercentage(replacementShoe.distance_to_query, replacementShoe.similarity_score);
      const terrain = replacementShoe.terrain;
      const audienceScore = replacementShoe.audience_verdict;
      const featureValues = replacementShoe.feature_values || {};
      
      const metrics = extractMetricsFromShoe(replacementShoe);
      
      const replacementCard = document.createElement('article');
      replacementCard.className = 'recommendation-card';
      replacementCard.dataset.shoeId = replacementShoe.shoe_id;
      replacementCard.dataset.index = index;
      replacementCard.innerHTML = `
        <div class="match-readout" onclick="showStatistics('${escapeHtml(replacementShoe.shoe_id || '')}')" title="View detailed statistics">
          ${matchPercentage}%
        </div>
        
        <h4 class="card-title">${escapeHtml(replacementShoe.shoe_name || replacementShoe.display_name || '').toUpperCase()}</h4>
        <p class="card-subtitle">${escapeHtml(replacementShoe.brand).toUpperCase()}</p>
        
        <div class="card-data-tags">
          ${terrain ? `
            <span class="data-tag">[ TERRAIN: ${terrain.toUpperCase()} ]</span>
          ` : ''}
          ${audienceScore ? `
            <span class="data-tag">[ SCORE: ${audienceScore}/100 ]</span>
          ` : ''}
          ${featureValues.Drop ? `
            <span class="data-tag">[ DROP: ${formatMetricValue(featureValues.Drop, 'Drop')} ]</span>
          ` : ''}
          ${featureValues.Weight ? `
            <span class="data-tag">[ WT: ${formatMetricValue(featureValues.Weight, 'Weight')} ]</span>
          ` : ''}
        </div>
        
        ${replacementShoe.source_url ? `
          <a href="${escapeHtml(replacementShoe.source_url)}" target="_blank" rel="noopener noreferrer" class="review-link">
            VIEW FULL REPORT →
          </a>
        ` : ''}
        
        <button class="replace-btn" onclick="replaceShoe('${escapeHtml(replacementShoe.shoe_id || '')}', ${index})" title="Replace this shoe">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
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
    
    setStatus(`Replacement acquired`);
  } catch (error) {
    console.error(error);
    setStatus(error.message || "Replacement failed", "error");
    
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
    
    statisticsTitle.textContent = `${data.shoe_name.toUpperCase()} - SPECIFICATION SHEET`;
    
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
    
    // Basic info
    statsHtml += `
      <div class="stat-item">
        <div class="stat-label">BRAND</div>
        <div class="stat-value">${escapeHtml(data.brand).toUpperCase()}</div>
      </div>
      <div class="stat-item">
        <div class="stat-label">TERRAIN</div>
        <div class="stat-value">${escapeHtml(labResults.Terrain || 'UNKNOWN').toUpperCase()}</div>
      </div>
      <div class="stat-item">
        <div class="stat-label">AUDIENCE VERDICT</div>
        <div class="stat-value">${data.audience_verdict ? data.audience_verdict + '/100' : 'N/A'}</div>
      </div>
    `;
    
    // Lab test results
    metrics.forEach(metric => {
      const value = labResults[metric.key];
      if (value !== undefined && value !== null) {
        statsHtml += `
          <div class="stat-item">
            <div class="stat-label">${escapeHtml(metric.label).toUpperCase()}</div>
            <div class="stat-value">${escapeHtml(formatMetricValue(value, metric.key)).toUpperCase()}</div>
          </div>
        `;
      }
    });
    
    if (!statsHtml) {
      statsHtml = '<div class="stat-item"><div class="stat-label">STATUS</div><div class="stat-value">NO DATA AVAILABLE</div></div>';
    }
    
    statisticsContent.innerHTML = statsHtml;
    statisticsOverlay.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
    
  } catch (error) {
    console.error('Error fetching statistics:', error);
    statisticsContent.innerHTML = '<div class="stat-item"><div class="stat-label">ERROR</div><div class="stat-value">DATA RETRIEVAL FAILED</div></div>';
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
    setStatus(error.message || "System initialization failed", "error");
    recommendations.innerHTML = `
      <div class="empty-state error-state">
        <p>${escapeHtml(error.message || "CRITICAL SYSTEM FAILURE")}</p>
      </div>
    `;
  }
});
