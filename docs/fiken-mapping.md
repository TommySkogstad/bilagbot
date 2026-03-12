# Fiken-mapping (Sprint 2)

Forberedt for sprint 2 — kobling mellom BilagBot-kontoer og Fiken API v2.

## Kontoplan-mapping

| BilagBot-konto | Fiken-konto | Beskrivelse |
|----------------|-------------|-------------|
| 6300 | 6300 | Kontorrekvisita |
| 6800 | 6800 | Kontorkostnader / IT |
| 6900 | 6900 | Telefon / kommunikasjon |
| 7100 | 7100 | Reisekostnader |
| 7140 | 7140 | Representasjon |

## MVA-koder

| Kode | Sats | Beskrivelse |
|------|------|-------------|
| 1 | 25% | Standard MVA |
| 11 | 15% | Næringsmiddel |
| 6 | 0% | Fritatt |

## Fiken API-endepunkter (v2)

- `POST /companies/{companySlug}/purchases` — Bokfør kjøp
- `POST /companies/{companySlug}/purchases/{purchaseId}/attachments` — Last opp vedlegg
- `GET /companies/{companySlug}/accounts` — Hent kontoplan
