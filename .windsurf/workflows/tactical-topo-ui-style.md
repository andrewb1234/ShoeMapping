---
description: Tactical Topo UI Style Guide
---

# Tactical Topo UI Style Guide

A distinctive dark-themed UI style with military/tactical aesthetics, characterized by sharp corners, grid patterns, and a bold color palette.

## Core Design Principles

1. **High Contrast**: Dark outer background with light canvas containers for maximum readability
2. **Sharp Geometry**: No rounded corners - everything uses sharp 90-degree angles
3. **Grid-Based Layout**: Visible grid patterns create a technical/blueprint aesthetic
4. **Bold Typography**: Heavy, condensed fonts with tight letter-spacing
5. **Military Color Palette**: Olive green accent with tactical neutrals

## Color System

```css
:root {
  /* Core Colors */
  --bg-topo: #1a1a1a;          /* Dark outer background */
  --bg-canvas: #f5f3f0;         /* Light main container */
  --bg-canvas-warm: #f2efe9;    /* Slightly warmer variant */
  
  /* Text Hierarchy */
  --text-primary: #000000;      /* Main text */
  --text-secondary: #333333;    /* Secondary text */
  --text-muted: #666666;        /* Muted text */
  
  /* Accent Colors */
  --accent-tactical: #2d5a3d;   /* Primary olive green */
  --accent-tactical-dim: #1e3d29; /* Darker olive */
  
  /* Grid System */
  --grid-line: #000000;         /* Black grid lines */
  --grid-line-dim: #cccccc;     /* Dimmed grid lines */
}
```

## Typography

### Font Stack
- **Display**: 'Oswald', 'Teko', sans-serif (bold, condensed)
- **Mono**: 'Roboto Mono', 'Space Mono', monospace
- **Body**: 'Inter', sans-serif

### Typography Patterns
- **Headers**: Font-weight 900, tight letter-spacing (-0.02em to -0.04em)
- **Labels/Buttons**: Uppercase, letter-spacing 0.05em to 0.1em
- **Mono Elements**: Font-weight 700, consistent spacing

## Layout Patterns

### Grid Structure
- 80px grid with subtle 0.1 opacity black lines
- All containers align to grid
- 2px borders create the grid structure

### Container Hierarchy
```css
.page-shell {
  max-width: 1400px;
  margin: 40px auto;
  position: relative;
  z-index: 1;
}

.canvas-container {
  background: var(--bg-canvas);
  position: relative;
  overflow: hidden;
}
```

### Border System
- **Primary borders**: 2px solid var(--grid-line)
- **Internal dividers**: 2px solid var(--grid-line)
- **Subtle borders**: 1px solid var(--grid-line-dim)

## Component Patterns

### Headers
```css
.header-section {
  display: grid;
  grid-template-columns: 1fr auto;
  border-bottom: 2px solid var(--grid-line);
  padding: 24px 32px;
}
```

### Buttons
```css
/* Primary Button */
.cta-primary {
  background: var(--accent-tactical);
  color: var(--bg-topo);
  border: 2px solid var(--accent-tactical);
  font-family: var(--font-display);
  text-transform: uppercase;
  letter-spacing: -0.01em;
}

/* Secondary Button */
.cta-secondary {
  background: transparent;
  color: var(--text-primary);
  border: 2px solid var(--grid-line);
}
```

### Form Elements
```css
.field input,
.field select,
.field textarea {
  background: transparent;
  border: 2px solid var(--grid-line);
  border-radius: 0;
  font-family: var(--font-mono);
}

.field input:focus,
.field select:focus,
.field textarea:focus {
  border-color: var(--accent-tactical);
  background: rgba(157, 255, 0, 0.05);
}
```

### Cards and Panels
```css
.panel-card {
  background: var(--bg-canvas);
  border: none;
  padding: 32px;
}

/* Grid of cards */
.card-grid {
  display: grid;
  gap: 0;
  border-top: 2px solid var(--grid-line);
  border-left: 2px solid var(--grid-line);
}

.card-grid .card {
  border-right: 2px solid var(--grid-line);
  border-bottom: 2px solid var(--grid-line);
}
```

## Background Patterns

### Topographic Grid
```css
body::before {
  content: "";
  position: fixed;
  background-image: 
    repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(255, 255, 255, 0.03) 2px, rgba(255, 255, 255, 0.03) 4px),
    repeating-linear-gradient(90deg, transparent, transparent 2px, rgba(255, 255, 255, 0.03) 2px, rgba(255, 255, 255, 0.03) 4px),
    repeating-linear-gradient(45deg, transparent, transparent 40px, rgba(157, 255, 0, 0.02) 40px, rgba(157, 255, 0, 0.02) 80px),
    repeating-linear-gradient(-45deg, transparent, transparent 40px, rgba(157, 255, 0, 0.02) 40px, rgba(157, 255, 0, 0.02) 80px);
  pointer-events: none;
  z-index: 0;
}
```

## Interactive States

### Hover Effects
```css
.button:hover {
  background: var(--accent-tactical-dim);
}

.card:hover {
  background: var(--bg-canvas-warm);
  z-index: 10;
}
```

### Active States
```css
.segmented-button.active,
.tab-button.active {
  background: var(--accent-tactical);
  color: var(--bg-topo);
}
```

## Responsive Behavior

### Breakpoints
- **Desktop**: Full grid layout
- **Tablet** (max-width: 1120px): Single column, maintain borders
- **Mobile** (max-width: 720px): Stack elements, adjust header

### Mobile Adjustments
```css
@media (max-width: 720px) {
  .site-shell {
    margin: 20px auto;
  }
  
  .site-header {
    grid-template-columns: 1fr;
  }
  
  .top-nav {
    border-left: none;
    border-top: 2px solid var(--grid-line);
  }
}
```

## Special Components

### Stepper Component
```css
.stepper {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0;
  border: 2px solid var(--grid-line);
}

.stepper li {
  border-right: 2px solid var(--grid-line);
}

.stepper li:last-child {
  border-right: none;
}
```

### Message Banners
```css
.message-banner {
  background: var(--bg-canvas-warm);
  border: 2px solid var(--grid-line);
  font-family: var(--font-mono);
  font-weight: 700;
  letter-spacing: 0.05em;
}

.message-banner.info {
  border-color: var(--metric-weight);
}
```

## Implementation Checklist

When applying this style:

1. [ ] Set up CSS variables in `:root`
2. [ ] Apply topographic background to body
3. [ ] Create grid overlay on main container
4. [ ] Use sharp corners (border-radius: 0)
5. [ ] Apply 2px borders throughout
6. [ ] Use Oswald for headers, Roboto Mono for labels
7. [ ] Implement hover states with tactical green
8. [ ] Ensure responsive behavior maintains grid structure
9. [ ] Test contrast ratios for accessibility

## Common Pitfalls

- **Don't use rounded corners** - The style is defined by sharp angles
- **Don't use shadows** - Flat design is essential
- **Don't mix border widths** - Consistently use 2px for primary borders
- **Don't forget the grid** - Elements should align to the visual grid
- **Don't use bright colors** - Stick to the muted tactical palette

## Accessibility Notes

- High contrast between dark background and light containers
- Text meets WCAG AA contrast requirements
- Focus states use tactical green with sufficient contrast
- Maintain 2px minimum border width for keyboard navigation visibility
