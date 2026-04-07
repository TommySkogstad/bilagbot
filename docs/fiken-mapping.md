# Fiken API v2 — Referanse for BilagBot

Kilde: https://api.fiken.no/api/v2/docs/swagger.yaml (v2.0.0)

## Autentisering

BilagBot bruker **personlig API-token** (Bearer token).
Token opprettes i Fiken: Rediger konto -> API -> Personlige API-nokler.
Koster 99 kr/mnd for API-tilgang.

```
Authorization: Bearer <api_token>
```

## Base URL

```
https://api.fiken.no/api/v2
```

TLS pakrevd. Maks 1 samtidige request. Maks 4 requests/sek.

## Datatyper

- **Dato**: `yyyy-MM-dd` (streng)
- **Belop**: Hele ore (int). 1000 kr = `100000`, 100.12 kr = `10012`
- **Konto**: 4 siffer eller 4 siffer + kolon + 5 siffer (reskontro). F.eks. `6300`, `1500:10001`

## Kontoplan-mapping

| BilagBot-konto | Fiken-konto | Beskrivelse |
|----------------|-------------|-------------|
| 6300 | 6300 | Kontorrekvisita |
| 6800 | 6800 | Kontorkostnader / IT |
| 6900 | 6900 | Telefon / kommunikasjon |
| 7100 | 7100 | Reisekostnader |
| 7140 | 7140 | Representasjon |

## MVA-koder (komplett Fiken-referanse)

### Koder gyldige for kjop (purchases) — brukes av BilagBot

| Kode | vatType | Sats | Beskrivelse | I BilagBot |
|------|---------|------|-------------|------------|
| 0 | NONE | 0% | Ingen MVA-behandling (kjop) | Ja |
| 7 | NONE | 0% | Ingen MVA-behandling (salg, men aksepteres) | Ja |
| 1 | HIGH | 25% | Kjop med hoy sats | Ja |
| 3 | HIGH | 25% | Salg med hoy sats | Ja |
| 11 | MEDIUM | 15% | Kjop med middels sats (mat) | Ja |
| 31 | MEDIUM | 15% | Salg med middels sats | Ja |
| 12 | RAW_FISH | 11.11% | Kjop med rafisk-sats | Ja |
| 13 | LOW | 12% | Kjop med lav sats | Ja |
| 33 | LOW | 12% | Salg med lav sats | Ja |
| 14 | HIGH_DIRECT | 25% | Kun kjopsmva, hoy sats | Ja |
| 21 | HIGH_BASIS | 25% | Kun grunnlag kjopsmva, hoy sats | Nei |
| 15 | MEDIUM_DIRECT | 15% | Kun kjopsmva, middels sats | Nei |
| 22 | MEDIUM_BASIS | 15% | Kun grunnlag kjopsmva, middels sats | Nei |
| 23 | NONE_IMPORT_BASIS | 0% | Kun grunnlag kjopsmva, ingen sats | Nei |
| 86 | HIGH_FOREIGN_SERVICE_DEDUCTIBLE | 25% | Tjenester kjopt fra utlandet (med fradrag) | Nei |
| 87 | HIGH_FOREIGN_SERVICE_NONDEDUCTIBLE | 25% | Tjenester kjopt fra utlandet (uten fradrag) | Nei |
| 88 | LOW_FOREIGN_SERVICE_DEDUCTIBLE | 12% | Lav tjeneste utlandet (med fradrag) | Nei |
| 89 | LOW_FOREIGN_SERVICE_NONDEDUCTIBLE | 12% | Lav tjeneste utlandet (uten fradrag) | Nei |
| 91 | HIGH_PURCHASE_OF_EMISSIONSTRADING_OR_GOLD_DEDUCTIBLE | 25% | Klimakvoter/gull (med fradrag) | Nei |
| 92 | HIGH_PURCHASE_OF_EMISSIONSTRADING_OR_GOLD_NONDEDUCTIBLE | 25% | Klimakvoter/gull (uten fradrag) | Nei |

### Koder KUN gyldige for salg (IKKE for kjop)

| Kode | vatType | Beskrivelse |
|------|---------|-------------|
| 5 | EXEMPT | Fritatt for MVA (avgiftsfritt) |
| 6 | OUTSIDE | Utenfor avgiftsomradet |
| 51 | EXEMPT_REVERSE | Omvendt avgiftsplikt |
| 52 | EXEMPT_IMPORT_EXPORT | Utforsel av varer/tjenester |

> **ADVARSEL**: Kode 6 (OUTSIDE) er i dag mappet i BilagBot sin `fiken.py`, men er KUN gyldig for salg.
> Hvis en faktura scannes med `suggested_vat_code: "6"` og postes som kjop, vil Fiken trolig avvise den.
> Vurder a mappe kode 6 til NONE (kode 0) for kjop, eller fjerne den fra kjops-mappingen.

## API-endepunkter brukt av BilagBot

### Firma
| Metode | Endepunkt | Bruk |
|--------|-----------|------|
| GET | `/companies/{slug}` | Validering av tilkobling |

### Kontoplan
| Metode | Endepunkt | Bruk |
|--------|-----------|------|
| GET | `/companies/{slug}/accounts` | Synkroniser kontoplan |

### Kontakter (leverandorer)
| Metode | Endepunkt | Bruk |
|--------|-----------|------|
| GET | `/companies/{slug}/contacts?organizationNumber=X` | Sok etter leverandor |
| POST | `/companies/{slug}/contacts` | Opprett ny leverandor |

Kontakt-payload ved opprettelse:
```json
{
  "name": "Telenor Norge AS",
  "organizationNumber": "988312495",
  "customer": false,
  "supplier": true
}
```

### Kjop (purchases)
| Metode | Endepunkt | Bruk |
|--------|-----------|------|
| POST | `/companies/{slug}/purchases` | Bokfor kjop |
| POST | `/companies/{slug}/purchases/{id}/attachments` | Last opp vedlegg |

Kjops-payload:
```json
{
  "date": "2025-01-15",
  "kind": "cash_purchase",
  "dueDate": "2025-02-15",
  "identifier": "INV-2025-00123",
  "kid": "1234567890123",
  "supplier": {"contactId": 12345},
  "lines": [{
    "description": "Mobilabonnement bedrift",
    "account": "6900",
    "vatType": "HIGH",
    "grossAmount": 59900
  }]
}
```

### Vedlegg
Upload som `multipart/form-data` med felt `file`.
Stottede formater: PDF, JPEG, PNG.

## Respons-konvensjoner

- **200**: Vellykket GET
- **201**: Vellykket POST — `Location`-header inneholder URL til opprettet ressurs
- **400**: Valideringsfeil (manglende felt, feil format)
- **401/403**: Autentiseringsfeil
- **404**: Ikke funnet
- **415**: Feil mediatype (kun `application/json` aksepteres)
- **429**: Rate limit — maks 1 samtidige request, maks 4/sek

## Paginering

Standard: `page=0`, `pageSize=25`, maks 100.
Respons-headere: `Fiken-Api-Page`, `Fiken-Api-Page-Size`, `Fiken-Api-Page-Count`, `Fiken-Api-Result-Count`.

## Potensielle utvidelser

Endepunkter BilagBot ikke bruker enna, men som kan vare nyttige:

| Endepunkt | Bruk |
|-----------|------|
| `GET /purchases` | Hente eksisterende kjop (duplikatsjekk) |
| `GET /purchases/{id}/payments` | Sjekke betalingsstatus |
| `POST /purchases/{id}/payments` | Registrere betaling |
| `POST /inbox` | Laste opp bilag til innboks (alternativ til direkte bokforing) |
| `GET /bankAccounts` | Hente bankkontoer for betalingsregistrering |
| `GET /contacts/{id}` | Hente full kontaktinfo |
