<p align="center">
  <h1 align="center">sw2almond</h1>
  <p align="center">
    <strong>Migrate your speech-to-text vocabulary from SuperWhisper to Almond.</strong><br>
    Single file. Zero dependencies. Dry-run by default.
  </p>
</p>

<p align="center">
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/license-MIT-green" alt="License"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.8+-blue" alt="Python 3.8+"></a>
  <a href="#"><img src="https://img.shields.io/badge/platform-macOS-lightgrey" alt="macOS"></a>
  <a href="#"><img src="https://img.shields.io/badge/dependencies-0-orange" alt="Zero dependencies"></a>
</p>

---

Switching from [SuperWhisper](https://superwhisper.com) to [Almond](https://almondvoice.com)? This tool transfers your custom vocabulary, spelling corrections, and text replacements so you don't re-enter them manually.

```
============================================================
  SuperWhisper -> Almond Migration Summary
============================================================

  SuperWhisper vocabulary terms: 31
  SuperWhisper replacements:     12
    - Spelling corrections: 5
    - Text macros:          4
    - Slash commands:        3 (skipped)

  New Almond entries to add:     28
  Variants merged into existing: 2
  Already in Almond (skipped):   3

  Mode: DRY RUN (no changes made)
  Run with --apply to write changes

============================================================
```

## Install

```bash
curl -O https://raw.githubusercontent.com/wolfiesch/superwhisper-to-almond/main/sw2almond.py
chmod +x sw2almond.py
```

Or clone:

```bash
git clone https://github.com/wolfiesch/superwhisper-to-almond.git
```

## Quick Start

```bash
# 1. Preview what will be migrated (safe — no changes)
python3 sw2almond.py

# 2. Quit Almond, then apply
python3 sw2almond.py --apply

# 3. Restart Almond — vocabulary is live
```

> **Important:** Quit Almond before running `--apply`. Almond holds vocabulary in memory and will overwrite your changes if it's running. The tool checks for this and will warn you.

## What Gets Migrated

| SuperWhisper Feature | Almond Equivalent | Migrated? |
|---|---|---|
| **Custom vocabulary** (recognition hints) | Dictionary entries | Yes |
| **Spelling corrections** ("Shure dog" → "Sherdog") | Entries with variants | Yes |
| **Text macros** ("input my email" → your email) | Entries with variants | Optional (`--include-macros`) |
| **Slash commands** ("Slash Compact" → `/compact`) | — | No (not applicable) |

## Features

| Category | Details |
|----------|---------|
| **Safety** | Dry-run by default, timestamped backups, Almond-running detection |
| **Recovery** | `--scan-backups` recovers vocabulary from all SuperWhisper backup files |
| **Merge** | Non-destructive — existing Almond entries preserved, variants merged |
| **Portability** | Single file, zero dependencies, Python 3.8+ stdlib only |
| **Output** | `--json` for scripting, `--export` to write to custom file |

## Usage

### Recover vocabulary from backups

SuperWhisper creates backup files when settings change. Scan them all to build the most comprehensive vocabulary set:

```bash
python3 sw2almond.py --scan-backups --apply
```

### Include text macros

Personal info expansions (email, address, URLs) are skipped by default:

```bash
python3 sw2almond.py --include-macros --apply
```

### Custom paths

```bash
python3 sw2almond.py \
  --sw-path ~/Documents/superwhisper \
  --almond-path "~/Library/Application Support/Almond/dictionary.json" \
  --apply
```

### Export without modifying Almond

```bash
python3 sw2almond.py --scan-backups --export merged.json
```

### JSON output for scripting

```bash
python3 sw2almond.py --json | jq '.migration'
```

## How It Works

```
SuperWhisper                          Almond
┌─────────────────────┐    classify    ┌─────────────────────────┐
│ vocabulary: [        │──────────────▶│ entries: {              │
│   "Claude",          │               │   "claude": {           │
│   "Sherdog"          │               │     canonical: "Claude", │
│ ]                    │               │     variants: []        │
│                      │               │   },                    │
│ replacements: [      │    merge      │   "sherdog": {          │
│   {original: "Shure  │──────────────▶│     canonical: "Sherdog",│
│    dog",             │               │     variants:           │
│    with: "Sherdog"}  │               │       ["Shure dog"]     │
│ ]                    │               │   }                     │
└─────────────────────┘               └─────────────────────────┘
```

1. **Vocabulary terms** → dictionary entries (lowercase key, original casing as `canonical`)
2. **Spelling corrections** → entries with the misspoken form as a `variant`
3. **Text macros** → optionally included (skipped by default)
4. **Slash commands** → skipped (no dictionary equivalent)
5. **Existing entries** → preserved (new variants merged, nothing overwritten)

## Reverting

Every `--apply` creates a timestamped backup:

```bash
# List backups
ls ~/Library/Application\ Support/Almond/dictionary.json.backup.*

# Restore
cp "~/Library/Application Support/Almond/dictionary.json.backup.20260216_053939" \
   "~/Library/Application Support/Almond/dictionary.json"
```

## License

[MIT](LICENSE)
