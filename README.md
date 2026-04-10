# FANSOR SPEDITION Website

Static bilingual website for FANSOR SPEDITION, a Suceava-based road freight transport company.

## Structure

- `ro/` Romanian pages
- `en/` English pages
- `styles.css` shared styles
- `script.js` shared navigation, language switcher, contact placeholders, and form demo logic
- `assets/` shared visuals and brand assets

Romanian is the default language. The root `index.html` redirects to `ro/index.html`, which also makes the project work cleanly on GitHub Pages.

## Local preview

Open the project with Live Server or run a simple static server:

```bash
python -m http.server 4173
```

Then visit:

- `http://127.0.0.1:4173/`
- `http://127.0.0.1:4173/ro/index.html`
- `http://127.0.0.1:4173/en/index.html`

## GitHub Pages

This repo is prepared for project-site hosting from the repository root.

Expected public URL:

`https://david8986.github.io/Project-site/`

Notes:

- the root entry redirects to the Romanian homepage
- all page links are relative, so the site also works from a subfolder
- the language switcher preserves the current filename between `ro/` and `en/`

## Contact placeholders

Replace the placeholder phone, email, address, and business-hours values in `script.js` after the client confirms the final public contact pack.
