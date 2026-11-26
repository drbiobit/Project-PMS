# 📋 Future Plan — PMS

Ideas and improvements for **PMS — Portable Media Search**, ranked roughly by
impact. Nothing here is built yet; this is the backlog.

## 🎯 UI / UX (highest value for daily use)

1. **Search-as-you-type** — debounce the query so results update live as you
   type (drop the "Search" button). Highest-value change for daily use.
2. **Filters** — filter the gallery by media type (image / video / audio)
   and/or date range.
3. **Light / dark theme toggle** — the app is dark-only; a light mode is a
   common request.
4. **Sort options** — relevance, date, filename, file size.
5. **Bulk actions** — multi-select → download-as-zip or delete.
6. **Toast notifications** — visible feedback for save / reset / reindex
   (instead of silent success).
7. **Keyboard shortcuts** — `/` focus search, `g`/`s` switch tabs, `Esc`
   close lightbox, `←`/`→` browse.
8. **Richer tiles** — show video duration, image resolution, and audio length
   on hover.
9. **Collection stats** — total items, storage used, breakdown by media type.
10. **Empty states** — friendly "no results" and "no media yet" screens.

## 🔐 Auth & access

- **Change password** from the settings UI (currently set at install time).
- **Multiple users** — per-user credentials (single user today).
- **Optional auth** — a "disable login" mode for single-user local use.
- **Session timeout** — auto-logout after inactivity.

## ⚡ Indexing & performance

- **Progress bar in the gallery** — surface the background `index.log`
  progress live on the settings page (poll `/status`).
- **Watch mode** — auto-index new files dropped into the media folder
  (file-system watcher).
- **Concurrency** — parallel embedding for independent batches (careful with
  the single llama-server; may need multiple server instances).
- **Resume / checkpoint** — make reindexing resumable after a crash.
- **Vector export** — export/import the SQLite index as a backup.

## 🔌 Models & endpoints

- **Model picker** — choose the GGUF quantization (Q5_K_XL, Q8_0, BF16) from
  the UI.
- **Ollama / vLLM presets** — one-click compose templates for popular local
  OpenAI-compatible servers (the endpoint is already pluggable).
- **Model download in UI** — a button to fetch the GGUF files from the
  settings page (wraps `scripts/download_models.sh`).

## 📱 Platform & packaging

- **Desktop app** — wrap the gallery in Electron / Tauri for a native app.
- **Mobile app** — a companion app that talks to the server over the LAN.
- **Windows image** — a native Windows build (Docker Desktop today).
- **Auto-update** — check for new image tags and prompt to upgrade.

## 📚 Docs & onboarding

- **Screenshots / demo video** — in the README and docs site.
- **Interactive tour** — a first-run walkthrough of the gallery.
- **Localization** — i18n for the UI strings.

## 🛡️ Reliability & ops

- **Health dashboard** — server status, model load, disk usage, index size.
- **Structured logs** — JSON logs for the server and indexer.
- **Backup / restore** — one-click backup of the DB + config.
- **Rate limiting** — protect the search endpoint from abuse.

---

_Pick the top item (search-as-you-type + filters) to start; it's the biggest
day-to-day win._
