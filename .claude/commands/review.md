# Code Review — Jailyard

Review recent changes for quality issues. Focus on $ARGUMENTS if provided, otherwise review all modified files.

## Checklist

### 1. Inline Architecture
- [ ] No external CSS or JS files added (everything stays inline)
- [ ] No npm packages, CDN imports, or framework imports introduced
- [ ] No build tools added (webpack, vite, etc.)

### 2. Theme Consistency
- [ ] All colors use CSS variables (`var(--name)`), no hardcoded hex values in new code
- [ ] Variable names match standard: `--accent2` NOT `--accent-2`
- [ ] Light mode `.light` class variant works (if new CSS added)
- [ ] Glassmorphic style maintained (backdrop-filter, subtle borders, gradients)

### 3. Data Integrity
- [ ] Changes to `league.teams` schema reflected in ALL rendering code
- [ ] Changes to `extras` object reflected in ALL consumers
- [ ] `dontuse`, `dontuse2`, `dontusedraft3` files are untouched
- [ ] Sleeper API endpoints still correct (if data code changed)

### 4. Canvas Charts
- [ ] `devicePixelRatio` handled (no blurry charts on Retina)
- [ ] Canvas resizes on window resize
- [ ] Chart data sourced from data objects, not hardcoded

### 5. JavaScript Quality
- [ ] New code wrapped in IIFE `(function(){ ... })()` to avoid global pollution
- [ ] No `var` (use `const`/`let`)
- [ ] Error handling on all `fetch()` calls (no empty catch blocks)
- [ ] No `console.log` left from debugging

### 6. Responsive & Accessibility
- [ ] Mobile layout tested (hamburger menu, no horizontal scroll)
- [ ] `aria-label` on interactive elements without visible text
- [ ] New animations respect `prefers-reduced-motion` if added

### 7. Navigation
- [ ] All pages cross-linked consistently (every page nav has all pages)
- [ ] New pages added to nav in ALL existing pages

## Output

Rate each issue: 🔴 MUST FIX / 🟡 SHOULD FIX / 🔵 NICE TO HAVE

Summarize: X issues found (Y critical, Z warnings).
