---
paths:
  - "src/evalgate/viewer/**"
  - "src/evalgate/report/templates/**"
---

# Frontend (viewer and HTML report)

- Colours, spacing and fonts come only from the tokens in `src/evalgate/viewer/static/tokens.css`; no literal colours elsewhere.
- Jinja2 autoescape stays on; never mark user or report content `|safe`.
- Every page has four states: loading, empty, error and success.
- Status is shown by icon and text, never colour alone; visible focus ring; works at 375 px.
- Contrast pairs must stay ≥ 4.5:1 in light and dark (`scripts/check_contrast.py`).
- JavaScript is progressive enhancement only; every filter works without it.
