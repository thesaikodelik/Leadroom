---
name: Leadroom
description: A desktop lead workspace drawn as a survey field book; every contact detail carries the mark of how it was found.
colors:
  bookcloth-green: "#1F3A30"
  bookcloth-deep: "#172D25"
  cloth-text: "#D9E6DF"
  cloth-muted: "#9DB6AA"
  cloth-accent: "#F4F7F4"
  survey-ink: "#1F4FE0"
  survey-ink-deep: "#1941BC"
  survey-ink-wash: "#E8EEFD"
  survey-ink-line: "#AFC0F4"
  on-ink: "#FFFFFF"
  surveyors-red: "#C2362B"
  surveyors-red-deep: "#A42C23"
  surveyors-red-wash: "#FBEAE8"
  surveyors-red-line: "#EDB9B3"
  field-amber: "#8A5A0B"
  field-amber-strong: "#C98A1B"
  field-amber-wash: "#FCF3E1"
  field-amber-line: "#EACB8D"
  settled-green: "#2F6151"
  settled-green-wash: "#E3EFE9"
  evidence-1: "#B9CEC4"
  evidence-2: "#8DAF9F"
  evidence-3: "#5E8C7B"
  evidence-4: "#2F6151"
  evidence-5: "#1F3A30"
  survey-paper: "#F3F6F3"
  sheet: "#FFFFFF"
  sheet-tint: "#F8FAF8"
  sheet-well: "#EEF3EF"
  hairline: "#E0E9E4"
  survey-rule: "#CADBD3"
  survey-rule-strong: "#A9C0B5"
  ink-text: "#15231D"
  ink-text-2: "#3D4D46"
  pencil-muted: "#56685F"
  pencil-faint: "#63736B"
typography:
  display:
    fontFamily: "Public Sans Variable, Segoe UI, system-ui, sans-serif"
    fontSize: "32px"
    fontWeight: 600
    lineHeight: 1.12
    letterSpacing: "-0.02em"
  headline:
    fontFamily: "Public Sans Variable, Segoe UI, system-ui, sans-serif"
    fontSize: "24px"
    fontWeight: 600
    lineHeight: 1.3
  title:
    fontFamily: "Public Sans Variable, Segoe UI, system-ui, sans-serif"
    fontSize: "18px"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "-0.01em"
  lead:
    fontFamily: "Public Sans Variable, Segoe UI, system-ui, sans-serif"
    fontSize: "15.5px"
    fontWeight: 400
    lineHeight: 1.5
  body:
    fontFamily: "Public Sans Variable, Segoe UI, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
  caption:
    fontFamily: "Public Sans Variable, Segoe UI, system-ui, sans-serif"
    fontSize: "12.5px"
    fontWeight: 400
  label:
    fontFamily: "Barlow Condensed, Arial Narrow, Segoe UI, sans-serif"
    fontSize: "12.5px"
    fontWeight: 600
    letterSpacing: "0.07em"
  label-small:
    fontFamily: "Barlow Condensed, Arial Narrow, Segoe UI, sans-serif"
    fontSize: "12px"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "0.07em"
  figure-large:
    fontFamily: "Roboto Mono Variable, Consolas, monospace"
    fontSize: "22px"
    fontWeight: 500
    lineHeight: 1.15
    fontFeature: "tnum"
  figure:
    fontFamily: "Roboto Mono Variable, Consolas, monospace"
    fontSize: "14px"
    fontWeight: 500
    fontFeature: "tnum"
  figure-micro:
    fontFamily: "Roboto Mono Variable, Consolas, monospace"
    fontSize: "11px"
    fontWeight: 400
    fontFeature: "tnum"
rounded:
  sm: "4px"
  md: "6px"
  lg: "9px"
  pill: "99px"
spacing:
  "1": "4px"
  "2": "8px"
  "3": "12px"
  "4": "16px"
  "5": "24px"
  "6": "32px"
  "7": "40px"
  "8": "48px"
components:
  button-primary:
    backgroundColor: "{colors.survey-ink}"
    textColor: "{colors.on-ink}"
    typography: "{typography.body}"
    rounded: "{rounded.md}"
    padding: "0 15px"
    height: "38px"
  button-primary-hover:
    backgroundColor: "{colors.survey-ink-deep}"
    textColor: "{colors.on-ink}"
  button-secondary:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink-text}"
    typography: "{typography.body}"
    rounded: "{rounded.md}"
    padding: "0 15px"
    height: "38px"
  button-secondary-hover:
    backgroundColor: "{colors.sheet-tint}"
  button-danger:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.surveyors-red}"
    rounded: "{rounded.md}"
    padding: "0 15px"
    height: "38px"
  button-danger-hover:
    backgroundColor: "{colors.surveyors-red-wash}"
    textColor: "{colors.surveyors-red}"
  icon-button:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.pencil-muted}"
    rounded: "{rounded.md}"
    size: "36px"
  input:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink-text}"
    typography: "{typography.body}"
    rounded: "{rounded.md}"
    padding: "0 11px"
    height: "38px"
  panel:
    backgroundColor: "{colors.sheet}"
    rounded: "{rounded.lg}"
    padding: "24px"
  rail-nav-item:
    backgroundColor: "{colors.bookcloth-green}"
    textColor: "{colors.cloth-text}"
    rounded: "{rounded.md}"
    padding: "0 10px"
    height: "38px"
  status-running:
    backgroundColor: "{colors.survey-ink-wash}"
    textColor: "{colors.survey-ink}"
    rounded: "{rounded.pill}"
    padding: "0 8px"
    height: "22px"
  status-failed:
    backgroundColor: "{colors.surveyors-red-wash}"
    textColor: "{colors.surveyors-red}"
    rounded: "{rounded.pill}"
    padding: "0 8px"
    height: "22px"
  table-head:
    backgroundColor: "{colors.sheet-tint}"
    textColor: "{colors.pencil-muted}"
    typography: "{typography.label}"
    padding: "0 14px"
    height: "40px"
---

# Design System: Leadroom

## Overview

**Creative North Star: "The Survey Field Book"**

Leadroom surveys a market instead of scraping a list. The interface is a surveyor's field book: a deep bookcloth rail down the left, cool survey paper for the working area, pale ruled lines dividing every record, and marks drawn in the book's own notation. A run reads as a traverse walked station by station; each contact detail carries a trig mark saying how it was found. The book is precise and quiet, never a dashboard of KPI cards over a generic table.

Density is that of a working ledger: rows of 52 to 62px, condensed caps for field names, tabular mono figures for every count, score and phone number. Colour is functional and scarce. Ink blue is the one hand that acts and selects; the green ramp is reserved for evidence; red appears only when something failed or is being destroyed. Structure comes from rules and hairlines more than from shadow.

The world ships as one design in four palettes (Field Book, Oxblood, Navy, Graphite), each in light and dark appearance. A palette changes only the cloth and the evidence ramp; the paper, the ink and the status colours stay the book's own. Dark appearance keeps the cloth rail and turns the paper to deep graphite-green.

**Key Characteristics:**
- Bookcloth rail with a faint woven texture; survey paper ground, cool and never cream.
- Ruled, not lifted: hairlines and survey rules carry the structure.
- Three type voices: Public Sans to read, Barlow Condensed caps to label, Roboto Mono to count.
- Book-native marks drawn from real data: trig points, the traverse, the five-cell score ramp.
- One action colour (ink blue); green only for evidence and completion; red only for failure.

## Colors

A cool, low-chroma green-grey book with a single saturated ink, a scarce surveyor's red, and one stepped green ramp for evidence.

### Primary
- **Survey Ink** (#1F4FE0): every action, link, selection and current state. Primary buttons, the active tab underline, selected table rows (as Survey Ink Wash), the current traverse station and its ring, switches when on, focus rings. Hover deepens to Survey Ink Deep (#1941BC).
- **Bookcloth Green** (#1F3A30): the rail, the mobile top bar, and the top step of the evidence ramp. Text on the cloth is Cloth Text (#D9E6DF), secondary text Cloth Muted (#9DB6AA), and the send-budget fill Cloth Accent (#F4F7F4).

### Secondary
- **Evidence Ramp** (Evidence 1 to 5, #B9CEC4 to #1F3A30): a numbered five-step green ramp used only for evidence strength and lead score (the score's cell count and fill), the trig marks (Evidence 3 for page text, Evidence 4 for structured), completed traverse stations and the run's progress line. Each palette ships its own ramp in its cloth hue.
- **Settled Green** (#2F6151, wash #E3EFE9): completed, sent and approved states; the healthy API dot.

### Tertiary
- **Surveyor's Red** (#C2362B, wash #FBEAE8, line #EDB9B3): errors, failed runs, rejections, destructive buttons. Never decorative, never for emphasis.
- **Field Amber** (#8A5A0B text, #C98A1B strong, wash #FCF3E1, line #EACB8D): warnings and queued or ready states only (sites that could not be read, compliance notices).

### Neutral
- **Survey Paper** (#F3F6F3): the page ground.
- **Sheet** (#FFFFFF), **Sheet Tint** (#F8FAF8), **Sheet Well** (#EEF3EF): cards and tables; table heads, footers and hovered rows; wells, tag chips, segmented-control tracks.
- **Hairline** (#E0E9E4): row dividers and card borders. **Survey Rule** (#CADBD3): input and button borders, tab baseline, table-head underline, the pending traverse dashes. **Survey Rule Strong** (#A9C0B5): hover borders and unreached station outlines.
- **Ink Text** (#15231D), **Ink Text 2** (#3D4D46), **Pencil Muted** (#56685F), **Pencil Faint** (#63736B): primary text, secondary text, labels and captions, placeholders and domains.

Dark appearance re-maps every neutral and state token (paper #111A16, sheet #17221D, text #E4ECE7, ink #86A2FF with #0C1430 on it, red #FF8A7E, amber #F2C063) and inverts the evidence ramp so step 5 is the lightest. The values live in `frontend/src/styles/tokens.css` and in the sidecar.

### Named Rules
**The One Ink Rule.** Survey Ink is the only colour that means "act here" or "this is selected". Green never marks an action; red never marks anything but failure or destruction; amber never marks anything but a warning.

**The Cool Paper Rule.** The ground is cool green-grey survey paper. It is never cream, beige or warm white, in any palette.

**The Same Book, Another Cloth Rule.** A palette may change only the cloth and the evidence ramp. Paper, ink, status colours and type stay fixed, so every palette is the same design.

## Typography

**Display Font:** Public Sans Variable (with Segoe UI, system-ui)
**Body Font:** Public Sans Variable (with Segoe UI, system-ui)
**Label Font:** Barlow Condensed 500/600 (with Arial Narrow)
**Mono Font:** Roboto Mono Variable (with Consolas)

**Character:** A plain civic sans for reading, the condensed caps of a printed survey form for field names, and a typewriter-like mono for every figure the book records.

### Hierarchy
- **Display** (600, 32px, 1.12, -0.02em): the page title (h1), one per page.
- **Headline** (600, 24px): drawer titles.
- **Title** (600, 18px, 1.3): section headings (h2), the evidence panel's business name.
- **Lead** (400, 15.5px, 1.5): page subtitles, max 66ch. h3 uses this size at 600.
- **Body** (400, 14px, 1.5): everything else; table cells, buttons (600), form labels (600).
- **Caption** (400, 12.5px): metadata lines, notices, pagination, chips.
- **Label** (Barlow Condensed 600, 12.5px, 0.07em, uppercase): table column heads, legends, traverse station names, evidence field names, detail-section heads. A 12px variant names the rail tagline and small settings labels; 11px only on the narrowest traverse.
- **Figures** (Roboto Mono 500, tabular): station values 22px (17px when narrow), the reading count 26px, the score block 30px; table scores 14px; domains, URLs, counts in tabs and nav, the version line at 11px.

The brand name in the rail sets at 17px semibold Public Sans.

### Named Rules
**The Three Voices Rule.** Public Sans reads, Barlow Condensed caps label, Roboto Mono counts. A number the book recorded (count, score, phone, domain, version) is always mono and tabular; a field or column name is always condensed caps; nothing else uses either.

**The Label Names, Never Announces Rule.** Condensed caps name a field, a column or a station. They never sit above a page or section heading as a kicker.

## Layout

A fixed 220px cloth rail and a fluid working area. Content padding is `clamp(20px, 3.4vw, 44px)` with 72px at the foot; the route frame caps at 1440px, settings-type pages at 1060px. A sticky 56px workspace bar (breadcrumbs left, API health right) sits on translucent paper with a light blur.

Screens respond to the room the content actually gets: `.content` is a size container named `page`, and screen rules query it (1080px: the evidence panel drops under the table; 720px: page headers stack, traverse tightens; 640px: each lead row becomes a ruled entry with labelled fields; 520px: traverse notes hide). Below an 800px window the rail becomes an off-canvas drawer under a cloth top bar.

Spacing steps are 4, 8, 12, 16, 24, 32, 40, 48px. Panels pad 24px; table cells 9px by 14px; the run page keeps tight chrome (20px above tabs, 12px below) so the lead table stays high. The run page is a two-column leads workspace when a lead is selected: table plus a 300 to 340px sticky evidence panel.

## Elevation & Depth

Mostly flat and ruled. Sheets sit on the paper with a hairline border and an almost invisible resting shadow; lift is reserved for things that float over the book. The cloth rail is set apart by colour and a 1px inset shade, not a shadow.

### Shadow Vocabulary
- **Resting sheet** (`--shadow-1`: `0 1px 2px rgba(21,35,29,0.06)`): cards, tables, buttons, the selected segment.
- **Floating panel** (`--shadow-2`: `0 6px 18px -6px rgba(21,35,29,0.16), 0 1px 3px rgba(21,35,29,0.06)`): the evidence panel, map notices and popups.
- **Drawer** (`--shadow-3`: `0 18px 44px -12px rgba(21,35,29,0.28), 0 2px 6px rgba(21,35,29,0.08)`): side drawers and the mobile rail.
- **Selection halo** (`0 0 0 3px` Survey Ink Wash): focused inputs and selected cards; the current station uses a 2px ink ring plus a 6px wash.

### Named Rules
**The Ruled, Not Lifted Rule.** Structure is drawn with Hairline and Survey Rule lines. A shadow larger than the resting sheet means the element floats above the page; nothing that sits in the flow gets one.

## Shapes

Gently squared corners: 4px for chips, segments, checkmarks and tags; 6px for buttons, inputs, nav items and notices; 9px for cards, tables, the traverse card and the map. Full pills (99px) only for status pills, count badges, switches and progress tracks. Circles for station marks and status dots. Dashed lines are part of the notation: the unwalked part of the traverse, the rule between evidence fields, empty states, and the AI-only trig outline. The recurring silhouette is the trig triangle.

## Components

### Buttons
Firm and plain, like a form's stamped boxes.
- **Shape:** gently squared (6px), 38px high, 15px side padding, 600 weight, 16px icon with 8px gap.
- **Primary:** Survey Ink fill, white text; hover Survey Ink Deep. One per header.
- **Secondary:** Sheet with Survey Rule border and resting shadow; hover Sheet Tint with stronger rule. Pressed nudges down 1px.
- **Danger:** Sheet with red line and red text; hover red wash.
- **Icon button:** 36px, transparent, Pencil Muted; hover Sheet Well; destructive icons hover red.
- **Disabled:** 50% opacity, no motion.

### Chips and status
- **Status pill:** 22px pill, 11px semibold, a 6px dot in the current colour; running dots pulse. Colour follows state (ink running, green done, amber queued, red failed, muted stopped).
- **Count badge:** ink-wash pill with mono 11px figure. **Tags:** 4px Sheet Well chips, 12.5px.

### Cards / Containers
- **Corner Style:** 9px.
- **Background:** Sheet on Survey Paper.
- **Shadow Strategy:** resting sheet only.
- **Border:** 1px Hairline.
- **Internal Padding:** 24px; footers and summary strips in Sheet Tint behind a hairline.

### Inputs / Fields
- **Style:** 38px, Sheet, 1px Survey Rule, 6px; textarea 92px minimum. Placeholder Pencil Faint. Leading icons at 11px inset.
- **Focus:** border turns Survey Ink with a 3px Survey Ink Wash halo.
- **Disabled:** Sheet Tint, faint text. Errors are a 12.5px red line under the field.
- **Switch:** 38 by 22px pill, Sheet Well off, Survey Ink on.

### Navigation
- **Rail:** cloth with woven texture. Items 38px, 6px, Cloth Text 500; hover a 5% white wash; active white 600 text on a raised cloth plate (8% white, 1px inner line). Mono counts right-aligned. Groups divided by a cloth line. The daily send budget and the mono version line sit at the rail's foot.
- **Tabs:** 42px, muted 600 text, mono count badge; active tab gets a 2px ink underline on the Survey Rule baseline.
- **Segmented control:** Sheet Well track, 30px segments; the pressed one lifts onto Sheet with resting shadow and an ink count.
- **Narrow windows:** cloth top bar with menu button; the rail slides in as a 280px drawer over a scrim.

### Trig Mark (signature)
A 15 by 13px survey triangle beside each email and phone, encoding how that detail was found: solid Evidence 4 for a link, structured data or map record; lower third filled in the lighter Evidence 2 for page text; dashed Pencil Faint outline for AI-only reads. A small dot sits at the centre. A legend in the table foot always explains the three marks.

### Traverse (signature)
The run's stages as stations on a line: Discovered, Selected, Read, Leads, Drafts. Done stations are solid Evidence 4 triangles, the current one is ink with a ringed halo and ink label, pending ones are outlined; walked line is Evidence 4, unwalked line is Survey Rule dashes. Labels in condensed caps, values in 22px mono. A compact 16px variant sits in the runs list.

### Score Ramp (signature)
Five 7 by 12px cells (10 by 14px in the evidence panel) beside a mono score out of 10; filled cells take the ramp step for the score, empty cells are Hairline.

### Evidence Panel
A sticky sheet with floating shadow beside the table: business name (Title), site link in ink, score strip on Sheet Tint, then each field as condensed-caps name, trig mark plus value, and a muted source line with a mono ink link, separated by dashed rules. Slides in over 240ms.

## Do's and Don'ts

### Do:
- **Do** use Survey Ink (#1F4FE0) for every action, link, selection and current state, and for nothing else.
- **Do** set every recorded number (counts, scores, phones, domains, versions) in Roboto Mono with tabular figures.
- **Do** name columns, fields and stations in Barlow Condensed 12.5px caps tracked 0.07em.
- **Do** draw structure with Hairline (#E0E9E4) and Survey Rule (#CADBD3) lines before reaching for shadow.
- **Do** derive every trig mark, traverse station and score cell from real data, and keep the three-mark legend in the foot of every table that shows them.
- **Do** keep motion between 140 and 260ms with the ease-out curve, and stop indefinite motion under reduced motion.
- **Do** change only cloth and evidence ramp when adding a palette, in both light and dark.

### Don't:
- **Don't** use warm, cream or beige grounds; the paper is cool survey paper (#F3F6F3).
- **Don't** use red for emphasis or decoration; Surveyor's Red is for failure and destruction only.
- **Don't** use the evidence greens for buttons, links or selection.
- **Don't** let a trig mark stand for a count of sources; it records the method a detail was found by.
- **Don't** place a condensed-caps kicker or eyebrow above a page or section heading.
- **Don't** replace the traverse with KPI stat cards, or the lead table with a generic card grid.
- **Don't** give in-flow cards anything heavier than the resting shadow.
