# BilagBot

AI-drevet bilagsscanner for **Ingeniør Tommy Skogstad ENK** (org.nr. 921 954 565).

BilagBot leser fakturaer (PDF/bilde), ekstraherer strukturert data med Claude CLI, og bokfører bilagene i Fiken.

## Stack

- **Python** ≥ 3.11 (pakkehåndterer: [uv](https://github.com/astral-sh/uv))
- **Claude CLI** (`claude -p`) for dokumentanalyse
- **SQLite** for lokal lagring (`~/.bilagbot/bilag.db`)
- **Fiken API v2** for bokføring
- **FastAPI** + **Uvicorn** for web-UI
- **Click** (CLI), **Rich** (terminal-UI), **Pydantic** (datamodeller)
- **Docker Compose** med Nginx + Cloudflare Tunnel

## Kom i gang

### Web-UI (anbefalt)

```bash
docker compose up -d
```

UI blir tilgjengelig på [bilag.tommytv.no](https://bilag.tommytv.no) (via Cloudflare Tunnel) eller lokalt på port 9500.

### CLI

```bash
uv sync --dev
uv run bilag scan <fil/mappe>     # Scan faktura
uv run bilag review               # Vis ventende bilag
uv run bilag approve <id>         # Godkjenn og lær leverandør
uv run bilag status               # Oversikt
uv run bilag fiken post           # Poster godkjente bilag til Fiken
```

## Utvikling

```bash
uv run pytest tests/ -v           # Kjør tester (112 tester)
uv run ruff check src/ tests/     # Linter
```

## Videre dokumentasjon

- [`CLAUDE.md`](./CLAUDE.md) — arkitektur, porter, konvensjoner og automatiske jobber
- [`docs/brand-guide.md`](./docs/brand-guide.md) — visuell identitet
- [`docs/fiken-mapping.md`](./docs/fiken-mapping.md) — kontoplan-mapping mot Fiken

## Lisens

MIT
