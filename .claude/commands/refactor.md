# Refactor — Jailyard

Dedicated cleanup session. NO new features — only improve existing code quality.

Focus on $ARGUMENTS if provided, otherwise scan the full codebase.

## Checklist

### 1. Dead Code
- Commented-out blocks (>3 lines)
- Unused CSS classes (defined but never referenced in HTML/JS)
- Unreachable JavaScript code
- Unused variables

### 2. Error Handling
- Find every empty `catch(e) {}` block
- Add meaningful error handling: `console.error()` at minimum, user-visible fallback UI where appropriate
- Model after the pattern already in `season.html`'s outer catch

### 3. CSS Cleanup
- Standardize `--accent-2` → `--accent2` everywhere
- Remove duplicate CSS rules within the same file
- Consolidate overly specific selectors
- Ensure all `:root` blocks have the canonical variable set

### 4. JavaScript Modernization
- Replace `var` → `const`/`let`
- Replace `keyCode` → `key`
- Wrap any remaining top-level code in IIFEs
- Remove `console.log` debug statements

### 5. Consistency
- Nav markup: ensure all pages use the same nav HTML structure
- Footer markup: ensure consistent across pages
- Theme toggle: verify same implementation pattern on each page

### 6. Accessibility Quick Wins
- Add `prefers-reduced-motion` media query to each file
- Add `aria-label` to buttons without text labels
- Add `aria-hidden="true"` to purely decorative elements
- Add inline data:URI favicon to each `<head>`

## Rules
- Make small, committed steps (describe each change)
- Do NOT change any visible behavior
- Do NOT touch `dontuse*` files
- Do NOT add external files or dependencies
- Report what was cleaned and lines affected
