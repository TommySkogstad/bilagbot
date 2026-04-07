# Visuell identitetsguide — Tommy Skogstad

Kilde: https://tommytv.no/tommy_skogstad_brand_guide.html (v1.1, mars 2026)

## Firmainfo

- **Navn**: Ingenior Tommy Skogstad ENK
- **Org.nr**: 921 954 565
- **Sted**: Tonsberg, Norge
- **Tagline**: data · elektro · ledelse · produktutvikling

## Fargepalett

| Navn | Hex | CSS-variabel | Rolle |
|------|-----|-------------|-------|
| Navy | `#0d1b2a` | `--navy` | Primar — tekst, logomark, headere |
| Warm White | `#f4f5f2` | `--white` | Bakgrunn |
| Blue 1 | `#1b2d42` | `--blue1` | Mork mellomtone |
| Blue 2 | `#2e4260` | `--blue2` | Mellomtone, brodtekst-aksent |
| Blue 3 | `#4a6080` | `--blue3` | Metadata, labels, section-headers |
| Blue 4 | `#7a96b0` | `--blue4` | Sekundar tekst, subtitler |
| Blue 5 | `#b8cad8` | `--blue5` | Lys aksent |
| Blue 6 | `#e4eaf0` | `--blue6` | Lys bakgrunn, borders, separatorer |

**Designprinsipp**: Intensjonelt morkeblatt. Paletten er bygget pa navy og kalde blatoner — fra dypt midnattsbla til lys stalbla. Ingen fremmede aksentfarger. Hierarki skapes gjennom tonalitet og typografi.

## Typografi

### Primar: DM Sans (Google Fonts)

- Vekter: 300 (light), 400 (regular), 500 (medium)
- Bruk: Overskrifter, brodtekst, navn

| Storrelse | Vekt | Bruk |
|-----------|------|------|
| 28px | 400 | Hovedoverskrift (letter-spacing: -0.02em) |
| 22px | 400 | Seksjonsoverskrift |
| 16px | 400 | Brodtekst |
| 13px | 400 | Sma detaljer, kontaktinfo |

### Sekundar: DM Mono (Google Fonts)

- Vekter: 300, 400, 500
- Bruk: Labels, metadata, teknisk info, org.nr., subtitler

| Storrelse | Bruk |
|-----------|------|
| 10px | Section labels (uppercase, letter-spacing: 0.14-0.2em) |
| 9px | Metadata, captions, fotnoter |
| 8-8.5px | Logo-subtekst, visittkorttitler |

## Logo

### Logomark

SVG-basert kretskort-inspirert monogram (T+S) i rektangulart ramme med IC-pinner.
Fire varianter:

| Variant | Bakgrunn | Farge | Fil |
|---------|----------|-------|-----|
| Lys | #f4f5f2 | #0d1b2a | /logo-mark-dark.svg |
| Mork | #0d1b2a | #f4f5f2 | /logo-mark-light.svg |
| Blagra | #e4eaf0 | #0d1b2a | /logo-alt-blue6.svg |
| Mellombla | #2e4260 | #f4f5f2 | /logo-alt-blue2.svg |

### Full logo

Logomark + tekst ved siden av:
- **Navn**: Tommy Skogstad (DM Sans 18px, regular)
- **Separator**: 1px linje (12% opacity)
- **Tittel**: INGENIOR (DM Mono 8px, uppercase, letter-spacing 0.16em)
- **Tagline**: data · elektro · ledelse · produktutvikling (DM Mono 8px)

Nedlastbare: /logo-full-dark.svg, /logo-full-light.svg (pa tommytv.no)

## Brukseksempler

### Visittkort
- Logo (40px) + navn (DM Sans 13px) + tittel (DM Mono 8px uppercase) + kontaktinfo (DM Mono 8px)

### E-postsignatur
- Venstre border (2px, Blue 6) + logo (28px) + navn (DM Sans 13px medium) + tittel + kontaktinfo

### Nettside header
- Navy bakgrunn + logo (28px, light variant) + navigasjon (DM Mono 8.5px, Blue 3)

## CSS-variabler (kopi-klar)

```css
:root {
  --navy:   #0d1b2a;
  --blue1:  #1b2d42;
  --blue2:  #2e4260;
  --blue3:  #4a6080;
  --blue4:  #7a96b0;
  --blue5:  #b8cad8;
  --blue6:  #e4eaf0;
  --white:  #f4f5f2;
  --font-sans: 'DM Sans', sans-serif;
  --font-mono: 'DM Mono', monospace;
}
```

## Google Fonts import

```html
<link href="https://fonts.googleapis.com/css2?family=DM+Mono:ital,wght@0,300;0,400;0,500;1,300&family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;1,9..40,300&display=swap" rel="stylesheet">
```
