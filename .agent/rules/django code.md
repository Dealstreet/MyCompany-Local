---
trigger: always_on
---

### Django Template Coding Guidelines

1.  **Whitespace in Comparison Operators:**
    When using comparison operators (`==`, `!=`, `<`, `>` etc.) inside Django template tags (`{% %}`), **always include spaces** before and after the operator.
    * ✅ **Correct:** `{% if var == 'value' %}`
    * ❌ **Incorrect:** `{% if var=='value' %}`

2.  **Conditional Styling via CSS Classes:**
    For complex conditional styling within HTML tags, **prioritize toggling CSS classes** conditionally over using inline `style` attributes. This prevents auto-formatters (like Prettier) from breaking or removing necessary spaces in the template code.
    * *Preferred approach:* `<div class="sidebar {% if is_home %}home-mode{% endif %}">`

3.  **Avoid Hardcoded Styles:**
    Refrain from using hardcoded inline styles. Always separate styling into dedicated CSS classes/blocks to maintain code cleanliness and ensure compatibility with formatters.