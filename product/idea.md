# Running Data Visualizations: Product Differentiation Guide

## Core Product Philosophy
Your app **beats ChatGPT chats** by delivering **persistent, proactive dashboards** that evolve with 200+ runs of longitudinal data. Chats require daily re-description; you spot patterns like "cadence dropped 5% in daily trainer" or "pace drifting uphill in shoe X" without prompting.

> **Key hook**: Normalize by effort (HR/perceived exertion) since race shoes shine on PR days but aren't sustainable. Your CSV already has gear, cadence, HR, elevation for 80–90% value.

---

## Prioritized Visualizations (5–7 charts max for MVP)

| Visualization                  | Why it differentiates                                                                 | Data insight                                                                 | Product value                                                                 |
|--------------------------------|----------------------------------------------------------------------------------------|------------------------------------------------------------------------------|--------------------------------------------------------------------------------|
| **Shoe Efficiency Heatmap**    | Compares normalized pace (HR-adjusted) across shoes; spots "hidden gems"              | Pace vs. HR/cadence per gear; color by efficiency                            | "Your trainer X is 10s/km faster at easy HR than trainer Y — rotate more"     |
| **Monthly Mileage Trend**      | Line chart of distance/pace over time, split by shoe                                  | Aggregated by month; overlay cadence/HR drift                                | "Mileage peaking — time for rotation alert"                                   |
| **Pace Distribution Box Plot** | By shoe and run type (easy/long/trail)                                                | Pace quartiles per gear; outliers highlight fatigue                          | "Trail shoe Z consistent on hills, but road pace varies"                      |
| **Shoe Mileage Tracker**       | Bar chart or odometer-style per shoe, with retirement zones                          | Cumulative distance per gear_id                                               | Proactive "Replace in 20km" notifications                                     |
| **Cadence vs. Elevation Scatter** | Scatter with trend lines; color by shoe                                           | Cadence drop on climbs reveals terrain fit                                   | "Shoe A holds cadence better uphill"                                          |
| **HR Efficiency Over Time**    | Line of pace-at-fixed-HR (zone 3) per shoe                                           | Rolling average; flags degradation                                            | "Efficiency dropping in daily shoe — inspect form/wear"                       |
| **Rotation Calendar**          | Heat calendar of shoe usage by week/day                                               | Density by gear; gaps show overuse                                           | "3 weeks straight on trainer — diversify to cut injury risk ~39%"             |

---

## Implementation Priority (CSV-only MVP)

```text
1. Shoe Efficiency Heatmap (group by gear + HR bins)
2. Monthly Mileage Trend (date aggregation)
3. Shoe Mileage Tracker (cumulative sum per gear_id)
4. Pace Box Plot (quartiles by gear + run type)
5. Rotation Calendar (calendar heatmap by gear)
Data Requirements (activities.csv confirmed)
✅ Activity Gear (ASICS Hyperspeed 4, Brooks Cascadia17 Trail, etc.)
✅ Average Speed, Average Cadence, Average HR, Elevation Gain
✅ Distance, Moving Time, Activity Date
✅ Training Load, Relative Effort (for normalization)
❌ .fit files needed only for intra-run degradation (lap splits, 1s GPS streams)
Example Insights (from your data)
- ASICS Hyperspeed 4: Best road efficiency, low mileage = race-day star
- Brooks Cascadia17 Trail: Consistent on elevation, high trail mileage
- Need rotation alert: Same trainer 3+ weeks straight
