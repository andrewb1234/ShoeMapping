# ShoeMapping: Project Evaluation & Product Direction

**Date:** April 10, 2026
**Scope:** Tech debt, UI/UX, competitive landscape, product direction

---

## 1. Executive Summary

ShoeMapping is a running shoe recommendation platform with a strong technical foundation: an ITML-based similarity engine trained on lab-test data from RunRepeat, served through two runtimes — a public anonymous explorer on Vercel and a personalization API on Render. The ML pipeline (ITML + K-Means hybrid) outperforms baseline K-Means by 75-83% on key metrics and produces genuinely useful shoe-to-shoe recommendations.

**Current state:**
- Public explorer is live and functional at `shoe-mapping.vercel.app`
- Personalization API is deployed on Render but not yet wired to the public site
- The core recommendation engine is solid; the product surface is half-built
- Test coverage is thin (4 tests), and the codebase has accumulated tech debt from rapid prototyping

**Verdict:** The technical core is stronger than the product surface. The priority should be finishing the personalization loop, cleaning up debt, and narrowing the product positioning before adding new features.

---

## 2. Tech Debt Assessment

### 2.1 Critical Debt (Fix Now)

#### Dead / Orphaned Files at Root Level
17 Python files sit at the repository root with mixed concerns:
- `check_gemini_models.py`, `elbow_plot.py`, `example_usage.py`, `test_kmeans_integration.py` — one-off scripts that should live in a `scripts/` directory or be deleted
- `database.py`, `data_preprocessor.py` — legacy data access that predates the current `personalization/` and `webapp/` structure
- `shoe_clustering.py`, `supervised_shoe_matcher.py`, `hybrid_kmeans_pipeline.py`, `hybrid_matching_service.py`, `supervised_matching_service.py` — ML pipeline files that should be under an `ml/` package
- `synthetic_dataset_generator.py`, `evaluate_supervised_model.py` — training pipeline scripts

**Impact:** New contributors cannot tell what's active vs. legacy. The flat root is confusing.

**Recommendation:** Move ML pipeline into `ml/`, one-off scripts into `scripts/`, and delete truly dead files.

#### Duplicate Template / JS Paths
- `index.html` exists as a legacy tactical-UI template alongside `explore.html` and `home.html`
- `app-old.js` and `app-athletic.js` sit in `static/` but appear unused
- `index-athletic.html` is likely a leftover

**Recommendation:** Audit which templates are actually served by routes. Delete unused ones.

#### `render.yaml` Blueprint vs. Reality Mismatch
The blueprint defines a `worker` service on a `starter` plan, but memories confirm the worker was never provisioned (free plan doesn't support workers; using `INLINE_JOB_EXECUTION=true`). The blueprint will fail if someone tries to deploy from it naively.

**Recommendation:** Either remove the worker from `render.yaml` and document INLINE mode as the default, or add a comment explaining it's for future use.

#### `personalize.js` — 1,220 Lines of Monolithic Vanilla JS
The personalization UI is a single 1,220-line JS file with:
- State machine (`landing`, `import`, `mapping`, `dashboard`) implemented via `display: none` toggling
- DOM references assigned in `DOMContentLoaded` with null-check guards everywhere
- Legacy functions marked `// Legacy` but not removed
- Visualization renderers (heatmap, mileage, pace, calendar) inlined alongside business logic

**Impact:** Any feature addition in the personalization flow requires reading 1,200+ lines. Bug surface is large.

**Recommendation:** Break into modules (state management, API calls, rendering, visualizations) using ES modules or at minimum separate files.

### 2.2 Moderate Debt (Fix Soon)

#### Thin Test Coverage
- 4 automated tests total
- No unit tests for the scoring algorithm (`personalization/scoring.py`), which contains the most business-critical logic
- No tests for CSV header inference edge cases (this is fragile code)
- No integration test for the explore UI flow
- No tests for visualization endpoints

**Recommendation:** Add tests for scoring logic, CSV parsing edge cases, and the full import→profile→recommendation pipeline.

#### CSS Bloat — 2,647 Lines in a Single File
`styles.css` contains:
- Two separate design systems (old `page-shell` / `canvas-container` + new `site-body` / `site-shell`)
- Legacy variable aliases (`--bg`, `--panel`, `--ink`, etc.) mapped to new names
- Visualization styles, modal styles, table styles, and grid utilities all in one file
- No CSS purging or tree-shaking

**Recommendation:** Split into `base.css`, `explore.css`, `personalize.css`, `visualizations.css`. Remove legacy variables and unused selectors.

#### Three Requirements Files with Unclear Boundaries
- `requirements.txt` — Vercel runtime
- `requirements-personalization.txt` — Render runtime
- `requirements-full.txt` — everything

No pinned versions. No lockfile. Builds are non-reproducible.

**Recommendation:** Pin versions in all three files. Consider using `uv` or `pip-compile` for a lockfile.

#### Scoring Algorithm Scores Every Shoe in the Catalog per Request
`compute_recommendations_for_context()` iterates over ALL catalog shoes for every recommendation request. With 641 shoes, this means 641 × (multiple DB queries per shoe for similarity lookups). This is O(n) per request with a high constant factor.

**Recommendation:** Cache the scored results per (user, profile_version, context) tuple (already partially implemented via `PersonalizedRecommendation` table, but the similarity lookups are still expensive). Pre-filter candidates by terrain and role before scoring.

### 2.3 Low-Priority Debt (Track)

- `utcnow()` is defined in both `personalization/models.py` and `personalization/utils.py`
- `main.py` at root is a Vercel entrypoint that just imports from `webapp.main` — duplication
- No type checking (`mypy`) or linting in CI
- `.python-version` file exists but no CI enforces it
- `possible_pipeline.md` at root appears to be an old brainstorm document

---

## 3. UI/UX Assessment

### 3.1 Public Explorer (`/explore`)

**Strengths:**
- Clean tactical-topo visual design — distinctive and professional
- Good information density per recommendation card (role, terrain, cushion, drop, similarity %)
- Terrain filter and brand/shoe selector flow is intuitive
- "Swap this match" reject-and-replace mechanic is clever

**Weaknesses:**
- **No shoe images.** Every card is text-only. In a category where aesthetics matter enormously (runners care what shoes look like), this is the single biggest gap.
- **No search.** Users must pick brand → then model from a dropdown. If a user knows the shoe name ("Pegasus 41"), they can't type it. This is high friction.
- **No URL-based state.** Selecting a shoe doesn't update the URL. Users can't share or bookmark a recommendation. No deep linking.
- **Lab details modal** shows raw key-value pairs (`"Midsole softness (HA)": 32.5`) with no units or context for what's good. A non-expert user cannot interpret these.
- **"Catalog neighbor" label** is jargon. Users don't think in terms of "catalog neighbors."
- **Mobile responsiveness** is basic — the grid collapses, but the filter row becomes stacked vertically and loses discoverability.

### 3.2 Home Page (`/`)

**Strengths:**
- Clear two-path split (Explore vs. Personalize)
- Good use of feature cards to explain each path

**Weaknesses:**
- The "Personalization API pending" disabled button is confusing for real users. If the API isn't available, the page should explain the product is in beta or show a waitlist CTA instead of exposing infrastructure state.
- Backtick in the banner message: "this deployment does not have \`PERSONALIZATION_BASE_URL\` configured" — this is a developer message leaked into user-facing copy.

### 3.3 Personalization Flow

**Strengths:**
- State-based wizard (landing → import → mapping → dashboard) is a good structural idea
- Drag-and-drop CSV upload, shoe mapping to catalog, and dashboard with visualizations
- Recommendation cards include explanations, positive drivers, and penalties — genuinely transparent

**Weaknesses:**
- **The flow is incomplete in production.** Vercel has no link to the Render-hosted personalization API. Users can't actually reach it.
- **No onboarding guidance.** Landing state says "Get Started" but doesn't explain what data the user needs or what they'll get.
- **Mapping UX is cumbersome.** After CSV import, users must manually map each detected shoe to a catalog entry via a full dropdown of 641 shoes. No fuzzy search, no auto-matching suggestions.
- **Dashboard is information-dense but not actionable.** Lots of data tiles ("Imported runs: 47", "Weekly mileage: 38 km") but no clear "here's what to do next" guidance.
- **No way to edit or delete imported data.** Once a CSV is imported, there's no undo.

### 3.4 Recommended UI Priorities

1. **Add shoe images** — even placeholder brand logos would help; RunRepeat URLs might provide image hotlinks, or use brand logo + generic shoe silhouettes
2. **Add a typeahead search bar** — let users type a shoe name directly instead of brand → model dropdown
3. **URL-based state** — make recommendations shareable (`/explore?shoe=Nike::Nike+Pegasus+41`)
4. **Humanize lab details** — show radar chart or bar chart instead of raw numbers; add "better than X% of shoes" context
5. **Fix leaked developer messages** — replace `PERSONALIZATION_BASE_URL` error text with user-facing copy
6. **Auto-match imported shoes** — use fuzzy string matching to pre-populate the mapping step

---

## 4. Competitive Landscape

### 4.1 Direct Competitors

| Product | What They Do | Differentiator | Weakness |
|---------|-------------|----------------|----------|
| **RunRepeat** | Lab-test reviews, score aggregation, shoe finder quiz | Massive dataset (1,000+ shoes cut in half), expert reviews | No personalization, no activity history, no rotation tracking |
| **Fleet Feet fit id®** | In-store 3D foot scanning + shoe matching | 5M+ foot scans, physical retail + online | Requires in-store visit; locked to Fleet Feet inventory |
| **Road Runner Sports ShoeFind** | Online quiz-based shoe finder | Size/fit recommendations | Generic quiz, no ongoing relationship |
| **Alastair Running** | Expert-curated top-3 shoe picks | Personal testing, minimalist recommendations | One person's opinion, not personalized to the reader |
| **ShoeCycle / SHOOZ** | Mileage tracking apps | Apple Watch integration, retirement alerts | No recommendations; just tracking |
| **RunMate Pro** | Minimalist GPS + shoe tracker | No subscription, no social | No recommendation engine |
| **Strava (built-in)** | Gear/shoe mileage tracking | Integrated with activity tracking | No recommendations; just cumulative miles; clunky gear management UX |

### 4.2 Market Signals

**From web research (April 2026):**

- **Footwear market growing $103.6B between 2025-2029.** Brands are investing heavily in AI personalization — Nike (AR foot scanning), Adidas (generative design), ON (robotic manufacturing). The industry direction is clear: personalization wins.
- **Strava's 2025 Year in Sport report** highlights shoe tracking as a key engagement feature. 44% of marathoners wore super shoes. Runners care deeply about shoe choice and track gear religiously.
- **Reddit r/RunningShoeGeeks** (280K+ members) has a daily recommendation thread where runners ask each other what to buy. The #1 frustration: "I don't know what shoe to get next given what I already own." This is exactly ShoeMapping's value prop.
- **No one owns the "rotation advisor" space.** Strava tracks mileage but doesn't recommend. RunRepeat reviews but doesn't know your history. Fleet Feet scans feet but doesn't follow up. The gap between "know your feet" and "know your running" is wide open.
- **AI shopping assistants are becoming table stakes.** Firework reports that AI-driven personalization reduces decision fatigue and return rates. The question isn't whether to personalize — it's how.

### 4.3 ShoeMapping's Competitive Position

**Unique strengths:**
1. Lab-test data + ITML similarity engine — not just reviews or quizzes but actual physical measurement-based matching
2. Activity-history-aware recommendations — no competitor combines shoe science with runner context
3. Transparent scoring — "here's why" explanations that no quiz-based tool provides
4. Multi-input flexibility — CSV, GPX, manual, Strava (scaffolded)

**Key vulnerability:**
- No shoe images, no brand partnerships, no user community — the product feels like a technical demo, not a consumer product
- RunRepeat could add personalization trivially if they wanted (they have the data and the traffic)
- The free Render/Vercel stack limits scale and reliability

---

## 5. Product Direction Recommendations

### 5.1 Problem Statement (Discovery Framework)

```
I am:       A recreational runner with 3-5 pairs of shoes and a Strava account
Trying to:  Know which shoe to wear for each type of run and when to replace one
But:        No tool connects my running history to shoe recommendations
Because:    Shoe finders are one-time quizzes that don't know my rotation or training
Which makes me feel: Overwhelmed by choices and uncertain I'm using the right shoe
```

**Validated by:** Reddit r/RunningShoeGeeks daily threads, Strava gear tracking engagement data, Fleet Feet's investment in fit technology.

### 5.2 Jobs to Be Done

| Job Type | Job | Priority |
|----------|-----|----------|
| **Functional** | Find the right shoe for my next purchase based on what I already own | HIGH |
| **Functional** | Know when to retire a shoe before it causes injury | HIGH |
| **Functional** | Understand which shoe works best for which type of run | MEDIUM |
| **Emotional** | Feel confident I'm not wasting money on the wrong shoe | HIGH |
| **Social** | Share my rotation and get validation from other runners | LOW (future) |

### 5.3 Opportunity Solution Tree

```
Desired Outcome: Increase weekly active users from 0 to 500 within 3 months
    |
    +-- Opportunity 1: Runners can't easily import their data
    |     +-- Solution A: One-click Strava OAuth import (HIGH impact, MEDIUM effort)
    |     +-- Solution B: Drag-and-drop CSV with auto-column detection (DONE)
    |     +-- Solution C: Manual "build your rotation" wizard with catalog search (MEDIUM impact, LOW effort)
    |
    +-- Opportunity 2: Recommendations feel impersonal without shoe images and context
    |     +-- Solution A: Add shoe images from RunRepeat or brand CDNs (HIGH impact, LOW effort)
    |     +-- Solution B: Typeahead search instead of dropdown (HIGH impact, LOW effort)
    |     +-- Solution C: Radar chart comparison view (MEDIUM impact, MEDIUM effort)
    |
    +-- Opportunity 3: No reason to come back after first visit
    |     +-- Solution A: Email digest "Your rotation this week" (HIGH impact, MEDIUM effort)
    |     +-- Solution B: "Shoe is approaching retirement" push notification (HIGH impact, MEDIUM effort)
    |     +-- Solution C: Monthly training summary with shoe-performance insights (MEDIUM impact, HIGH effort)
    |
    +-- Opportunity 4: No social proof or distribution channel
    |     +-- Solution A: Shareable rotation cards for social media (HIGH impact, LOW effort)
    |     +-- Solution B: "Compare your rotation" between two users (MEDIUM impact, HIGH effort)
    |     +-- Solution C: Embed widget for running blogs (LOW impact, MEDIUM effort)
```

### 5.4 Recommended Product Roadmap

#### Phase 1: "Make It Real" (Weeks 1-3)
- **Wire Vercel ↔ Render** — set `PERSONALIZATION_BASE_URL` so the public site links to personalization
- **Add shoe images** to catalog (crawl from RunRepeat or use brand logos as fallback)
- **Add typeahead search** to the explore page
- **Fix user-facing copy** — remove developer messages, improve empty states
- **Add URL-based state** for shareable recommendations
- **Auto-match imported shoes** using fuzzy string matching

#### Phase 2: "Make It Sticky" (Weeks 4-6)
- **Complete Strava OAuth** — flip `ENABLE_STRAVA_UI=true` and test the full flow
- **Build a "My Rotation" shareable card** — a visual summary users can screenshot/share
- **Add retirement alerts** — email or in-app notification when a shoe approaches target mileage
- **Humanize the lab details** — radar charts, percentile comparisons, plain-language summaries
- **Improve the mapping step** — fuzzy search with confidence scores instead of full dropdown

#### Phase 3: "Make It Grow" (Weeks 7-12)
- **Weekly email digest** — "Your shoes this week" with mileage updates and recommendations
- **Affiliate links** — link recommendations to retailer pages (monetization path)
- **Content marketing** — "Best shoes for easy runs in 2026" generated from the actual recommendation data
- **API for running blogs** — let others embed ShoeMapping recommendations
- **Run classification** — auto-label easy/tempo/long/trail from pace/HR/elevation data

### 5.5 What NOT to Build

- **Biomechanics analysis** — the product doc correctly identifies this as out of scope. Don't infer injury risk or foot strike from Strava data.
- **Social features** (leaderboards, community) — premature without an active user base. Focus on utility first.
- **Mobile app** — the web app can work via mobile browser. A native app is premature overhead.
- **Real-time Strava sync** — batch daily sync is sufficient. Real-time webhooks add complexity for minimal user value at this stage.
- **Brand partnerships** — don't let business development distract from product-market fit.

---

## 6. Key Metrics to Track

| Metric | Current | 30-Day Target | 90-Day Target |
|--------|---------|--------------|--------------|
| Weekly active users | ~0 | 50 | 500 |
| CSV/GPX imports completed | unknown | 20 | 200 |
| Strava connections | 0 | 10 | 100 |
| Recommendations viewed per session | unknown | 3+ | 5+ |
| Return visits (7-day) | 0% | 15% | 30% |
| Shareable links generated | 0 | 10 | 100 |

---

## 7. Summary of Priorities

| Priority | Category | Action |
|----------|----------|--------|
| **P0** | Infra | Wire Vercel ↔ Render so personalization is reachable |
| **P0** | UI | Add shoe images to catalog and recommendation cards |
| **P0** | UI | Replace brand→model dropdowns with typeahead search |
| **P0** | UX | Fix developer-facing messages leaked to users |
| **P1** | Tech Debt | Move root-level ML scripts into `ml/` package |
| **P1** | Tech Debt | Delete unused templates and JS files |
| **P1** | Testing | Add unit tests for scoring algorithm and CSV parsing |
| **P1** | UI | Add URL-based state for shareable recommendations |
| **P1** | Product | Auto-match imported shoes with fuzzy matching |
| **P2** | Product | Complete Strava OAuth flow |
| **P2** | Product | Build shareable rotation cards |
| **P2** | UI | Humanize lab details with radar charts |
| **P2** | Tech Debt | Split `styles.css` and `personalize.js` into modules |
| **P2** | Tech Debt | Pin dependency versions |
| **P3** | Product | Email digests and retirement alerts |
| **P3** | Product | Affiliate links for monetization |
| **P3** | Tech Debt | Add mypy/lint CI pipeline |

---

## 8. Final Assessment

ShoeMapping has a genuinely differentiated recommendation engine — the ITML + lab-data approach produces better results than any quiz-based shoe finder on the market. The product vision (runner-context recommender, not biomechanics oracle) is sound and well-calibrated.

The gap is between the technical capability and the product experience. The engine works; the surface needs polish. The competitive window is open — RunRepeat has the data but not the personalization, Strava has the users but not the recommendations, Fleet Feet has the scanning but not the ongoing relationship. ShoeMapping could own the "rotation advisor" niche if it ships a complete, shareable, image-rich experience before a bigger player notices the gap.

**The single most impactful action right now:** Wire the personalization API to the public site and add shoe images. Everything else follows from having a complete product that users can actually try.
