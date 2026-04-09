# Shoe Mapping: Strava-Powered Personalized Running Shoe Recommendations

## Overview

This product extends a running shoe recommendation website into a personalized engine that learns from a runner’s own activity history. The core idea is to use Strava data, CSV exports, or GPX uploads to build a runner profile and rank shoes based on the kinds of runs the person actually does.

The first version should focus on explainable recommendations, not deep biomechanics inference. The system should help users answer questions like: “Which shoe fits my easy runs?”, “Which shoe is best for hills?”, and “Which shoe should I replace next?”

## Product Goal

The product should make shoe recommendations feel personal, useful, and grounded in real training history.

Primary goals:
- Recommend shoes based on a runner’s actual workload and training patterns.
- Explain why a shoe is recommended in plain language.
- Help users manage shoe rotation and retirement.
- Keep the product usable even if Strava integration is limited.

## Core Principle

The best implementation is a **runner-context recommender**, not a biomechanics oracle.

That means:
- Use Strava data to infer training context.
- Use shoe metadata to understand what each shoe is good at.
- Combine the two with a transparent scoring system.
- Avoid pretending the app can precisely infer strike pattern or injury risk from one or two metrics.

## Data Inputs

The system can ingest data from three sources:

### 1. Strava API
Useful fields:
- Gear ID.
- Cadence.
- Pace / speed.
- Heart rate.
- Elevation gain.
- Distance.
- Moving time.
- Activity streams.

### 2. CSV Export
Useful for users who want a simple import flow without API authorization.

### 3. GPX Files
Useful for users who want a lightweight upload path and only basic activity history.

## Runner Profile

The app should aggregate activity history into a runner profile.

Possible profile dimensions:
- Weekly mileage.
- Pace distribution.
- Cadence distribution.
- Heart rate distribution.
- Terrain mix.
- Elevation exposure.
- Long-run frequency.
- Recovery run frequency.
- Trail vs road preference.
- Shoe rotation patterns.
- Mileage per shoe.

The profile should be updated incrementally as new activities are imported.

## What Strava Data Is Good For

Strava data is good for identifying **context**, not perfect form diagnosis.

Strong use cases:
- Matching shoes to easy, tempo, long, trail, or recovery runs.
- Estimating whether a runner is mostly road-based or trail-based.
- Measuring mileage and wear on each shoe.
- Identifying rotation habits.
- Spotting training load trends.

Weaker use cases:
- Inferring foot strike from cadence alone.
- Determining ideal drop from cadence alone.
- Predicting injury risk from a single metric.
- Making hard rules like “high cadence means low drop.”

## Recommendation Logic

The recommendation engine should rank shoes with a weighted scoring system.

Example scoring factors:
- Terrain fit.
- Run type fit.
- Cushioning fit.
- Stability fit.
- Weight fit.
- Rotation fit.
- Comfort history.
- Wear / retirement status.

Example interpretation:
- Light, responsive shoes should rank higher for tempo and race sessions.
- Cushioned, durable shoes should rank higher for easy and long runs.
- Trail shoes should rank higher for hilly or dirt-heavy profiles.
- Shoes the runner has historically used successfully should get a comfort boost.
- Shoes near retirement mileage should be downranked or flagged.

## Suggested Algorithm

```pseudo
for each activity:
    if activity is not a run:
        skip

    extract features:
        pace
        distance
        duration
        cadence
        heart_rate
        elevation_gain_per_km
        gear_id

    classify run context:
        easy / tempo / interval / long / recovery
        road / trail / hilly

aggregate all runs into runner profile

for each shoe:
    compute score:
        score += terrain_fit(shoe, runner_profile)
        score += intensity_fit(shoe, recent_run_context)
        score += cushioning_fit(shoe, training_load)
        score += stability_fit(shoe, terrain_and_elevation)
        score += comfort_history_fit(shoe, past_success)
        score += rotation_fit(shoe, current_rotation)
        score -= wear_penalty(shoe, mileage)

rank shoes by score
return top recommendations with explanations
```

## UX Direction

The product should feel practical and low-friction.

Recommended UX flow:
1. User lands on site.
2. User either imports Strava, uploads CSV/GPX, or enters data manually.
3. The app creates a runner profile.
4. The app shows a shortlist of recommended shoes.
5. Each recommendation includes a short explanation.
6. The app offers shoe rotation and retirement suggestions.

The app should still be useful without Strava, because many users will not want to authorize third-party access immediately.

## Product Modes

The app should support three operating modes.

### Manual Mode
User enters shoe names, rough mileage, and preferences manually.

Best for:
- Quick onboarding.
- Privacy-conscious users.
- Early MVP validation.

### Import Mode
User uploads CSV or GPX data.

Best for:
- Users who want personalization without API permissions.
- A fallback if API access is limited.
- Fast MVP adoption.

### Strava Sync Mode
User connects Strava and the app periodically refreshes data.

Best for:
- Power users.
- Accurate shoe mileage tracking.
- Automated profile updates.

## Caching Strategy

The app should not depend on live Strava calls for every recommendation.

Recommended approach:
- Store imported activities locally.
- Store derived summaries separately.
- Cache runner profile snapshots.
- Sync only deltas when new data arrives.
- Recompute recommendations from the local cache.

This makes the app faster, cheaper, and more resilient if Strava is unavailable or rate-limited.

## Data Architecture

Suggested layers:
- `Raw Activity Layer`: imported runs and gear IDs.
- `Feature Layer`: pace, cadence, elevation, effort, terrain labels.
- `Profile Layer`: runner tendencies and shoe rotation behavior.
- `Recommendation Layer`: scored shoes and explanations.

This separation makes it easier to:
- Recompute logic later.
- Add new signals.
- Audit recommendation quality.
- Support future machine learning.

## Strava Considerations

If the product relies on Strava for public users, it should be treated as an integration that may require approval and review. The app should request only the minimum permissions needed and clearly explain what data is collected and why.

Because Strava’s rules can be strict, the safest product strategy is:
- Build a working non-Strava version first.
- Add optional Strava sync.
- Make CSV and GPX imports first-class onboarding paths.
- Avoid depending on Strava as the only data source.

## Product Positioning

This should be positioned as:
- A shoe recommendation engine.
- A shoe rotation advisor.
- A mileage and retirement tracker.
- A run-context matcher.

It should not be positioned as:
- A medical or injury prediction tool.
- A definitive biomechanics analyzer.
- A hard-rule foot strike classifier.

## MVP Scope

A good first release should include:
- Manual shoe entry.
- CSV and GPX import.
- Basic runner profile generation.
- Shoe scoring and ranking.
- Explanations for each recommendation.
- Shoe mileage retirement alerts.

A second phase can add:
- Strava sync.
- Better run classification.
- Comfort-history weighting.
- More advanced route and terrain inference.
- Personalized re-ranking by run type.

## Example Recommendation Output

Example:

- “This shoe ranks highly for your easy and long runs because it matches your higher mileage, moderate pace range, and frequent elevation exposure.”
- “This shoe is a strong race-day option because it is lighter and better aligned with your faster sessions.”
- “This shoe is nearing retirement based on estimated mileage and recent usage frequency.”

## Risks

Main product risks:
- Overpromising on biomechanics.
- Making the UX too dependent on Strava.
- Collecting more data than needed.
- Recommending shoes without enough explanation.
- Creating a model that is too opaque to trust.

The best mitigation is to keep the system explainable and let users see why a shoe was recommended.

## Recommended Build Order

1. Define shoe metadata schema.
2. Build CSV / GPX import.
3. Create runner profile aggregation.
4. Add transparent shoe scoring.
5. Show explanations in the UI.
6. Add shoe rotation and retirement logic.
7. Add optional Strava sync.
8. Improve recommendations with feedback loops.

## Design Philosophy

The product should feel like a smart running coach for shoes, not a black box. The more it explains itself, the more trustworthy it becomes.

A good rule: every recommendation should answer “why this shoe, why now?”


