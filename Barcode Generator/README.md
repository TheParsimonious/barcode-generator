# Barcode Generator

This project has two parts:

- `barcode_generator.py`: the desktop Python app
- `docs/`: the static phone-friendly web app for GitHub Pages

## GitHub Pages setup

This repo is configured to deploy the `docs/` folder with GitHub Actions.

Important:

- Keep the files in `docs/`
- Do not use a Jekyll theme workflow
- If your GitHub repo already has an older Pages or Jekyll workflow, delete that old workflow file and keep `.github/workflows/deploy-pages.yml`

## Files used by GitHub Pages

- `docs/index.html`
- `docs/styles.css`
- `docs/app.js`
- `docs/barcode_presets.json`
- `docs/.nojekyll`
