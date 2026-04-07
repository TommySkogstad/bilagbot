# BilagBot

AI-drevet bilagsscanner for Ingenior Tommy Skogstad ENK (org.nr. 921 954 565).

## Stack

- **Python** >=3.11, pakkehanterer: uv
- **Claude CLI** (`claude -p`) for dokumentanalyse (PDF/bilde -> strukturert JSON)
- **SQLite** for lokal lagring (~/.bilagbot/bilag.db)
- **Fiken API v2** for bokforing
- **FastAPI** + **Uvicorn** for web-UI
- **Click** for CLI, **Rich** for terminal-UI, **Pydantic** for datamodeller
- **Docker Compose** med Nginx + Cloudflare Tunnel (ID: `5de0ef57-a5be-409b-92f6-3f45f035f96b`)

## Porter

| Tjeneste | Port |
|----------|------|
| Nginx (dev) | 9500 |
| FastAPI backend | 8086 |
| Cloudflare Tunnel | bilag.tommytv.no |

## Arkitektur

```
web.py        — FastAPI web-app (upload, review, approve, fiken post)
scanner.py    — Claude CLI-kall, filvalidering, JSON-parsing
classifier.py — Leverandorgjenkjenning og laring (UNKNOWN/KNOWN/AUTO)
database.py   — SQLite (scan_log, known_suppliers, fiken_accounts)
fiken.py      — Fiken API v2 (kontakter, kjop, vedlegg)
cli.py        — Click-kommandoer (scan, review, approve, reject, status, fiken)
review.py     — Rich terminal-UI
models.py     — Pydantic-modeller (InvoiceData, LineItem, MatchLevel, ScanStatus)
config.py     — Miljovariabel-konfigurasjon
exceptions.py — Feilhierarki
static/       — HTML/CSS frontend (brand guide-styling)
```

## Deploy

- **Enkel deploy** (ikke blue-green): `docker compose up -d`
- Integrert i `misc-scripts/deploy-daily`

## Automatiske jobber

Inkludert i folgende misc-scripts-jobber:

- `issue-triage`
- `ci-fix-daily`
- `deploy-daily`
- `dependabot-weekly`
- `security-weekly`
- `docs-review-weekly`
- `issues-weekly`
- `tech-debt-weekly`

## Kommandoer

```bash
# CLI
bilag scan <fil/mappe>          # Scan faktura med Claude CLI
bilag review                    # Vis ventende bilag
bilag approve <id> [-a konto]   # Godkjenn og lar leverandor
bilag reject <id>               # Avvis
bilag status                    # Oversikt
bilag suppliers list/edit       # Leverandoradministrasjon
bilag fiken validate/post/sync  # Fiken-integrasjon

# Web (Docker)
docker compose up -d            # Start web-UI + tunnel
docker compose logs -f backend  # Se backend-logger
```

## Konvensjoner

- Kjor tester: `uv run pytest tests/ -v`
- Linter: `uv run ruff check src/ tests/`
- Alle feilmeldinger og CLI-output pa norsk
- Commit-meldinger pa engelsk
- Ingen `anthropic` SDK — bruker Claude CLI via subprocess

## Visuell identitet

Bilagbot folger Tommy Skogstad sin brand guide (https://tommytv.no/tommy_skogstad_brand_guide.html).
Se `docs/brand-guide.md` for komplett referanse. Kort oppsummert:

- **Farger**: Navy #0d1b2a (primar), Warm White #f4f5f2 (bakgrunn), blatone-skala
- **Fonter**: DM Sans (primar), DM Mono (metadata/labels)
- **Prinsipp**: Kun navy og kalde blatoner — ingen fremmede aksentfarger
