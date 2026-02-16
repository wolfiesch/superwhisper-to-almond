# sw2almond

Migrate your custom vocabulary from [SuperWhisper](https://superwhisper.com) to [Almond](https://almondvoice.com) on macOS.

Both apps are speech-to-text transcription tools for macOS. If you're switching from SuperWhisper to Almond, this tool transfers your custom vocabulary, spelling corrections, and text replacements so you don't have to re-enter them manually.

## What gets migrated

| SuperWhisper Feature | Almond Equivalent | Migrated? |
|---|---|---|
| Custom vocabulary terms | Dictionary entries | Yes |
| Spelling corrections (e.g., "Shure dog" → "Sherdog") | Dictionary entries with variants | Yes |
| Text expansion macros (e.g., "input my email" → your email) | Dictionary entries with variants | Optional (`--include-macros`) |
| Slash commands (e.g., "Slash Compact" → "/compact") | N/A | No (not applicable) |
| Recording modes | N/A | No (different architecture) |

## Requirements

- macOS
- Python 3.8+
- SuperWhisper installed (or its data directory available)
- Almond installed

## Installation

No dependencies needed — it's a single Python script using only the standard library.

```bash
# Clone or download
git clone https://github.com/yourusername/superwhisper-to-almond.git
cd superwhisper-to-almond

# Or just download the script
curl -O https://raw.githubusercontent.com/yourusername/superwhisper-to-almond/main/sw2almond.py
chmod +x sw2almond.py
```

## Usage

### Preview (dry run)

```bash
# See what would be migrated — no changes made
python3 sw2almond.py
```

### Apply migration

```bash
# Write changes to Almond's dictionary
python3 sw2almond.py --apply
```

A timestamped backup of your Almond dictionary is created automatically before any changes.

### Scan backup files

SuperWhisper creates backup files when settings change. If you've removed vocabulary terms over time, scanning backups recovers the most comprehensive set:

```bash
python3 sw2almond.py --scan-backups --apply
```

### Include text macros

By default, personal info macros (like email/address expansions) are skipped since they're typically not dictionary terms. Include them with:

```bash
python3 sw2almond.py --include-macros --apply
```

### Custom paths

If your data directories are in non-standard locations:

```bash
python3 sw2almond.py \
  --sw-path ~/Documents/superwhisper \
  --almond-path "~/Library/Application Support/Almond/dictionary.json" \
  --apply
```

### Export to file

Preview the merged dictionary without modifying Almond:

```bash
python3 sw2almond.py --scan-backups --export merged.json
```

### JSON output (for scripting)

```bash
python3 sw2almond.py --json
```

## How it works

### SuperWhisper data format

SuperWhisper stores settings at `~/Documents/superwhisper/settings/settings.json`:

```json
{
  "vocabulary": ["Claude", "Vercel", "Sherdog"],
  "replacements": [
    {"id": "uuid", "original": "Shure dog", "with": "Sherdog"}
  ]
}
```

### Almond data format

Almond stores its dictionary at `~/Library/Application Support/Almond/dictionary.json`:

```json
{
  "entries": {
    "sherdog": {
      "canonical": "Sherdog",
      "isAutoAdded": false,
      "variants": ["Shure dog"]
    }
  },
  "version": 1
}
```

### Migration logic

1. **Vocabulary terms** become dictionary entries where the lowercase term is the key and the original casing is preserved as `canonical`
2. **Spelling corrections** (replacements where the output is a simple correction) become entries with the misspoken form added as a `variant`
3. **Text macros** (replacements that expand to personal info, URLs, etc.) are optionally included
4. **Slash commands** are skipped (they don't map to dictionary concepts)
5. **Existing Almond entries** are preserved — new variants are merged, nothing is overwritten

## After migrating

Restart Almond to pick up the new vocabulary. Your dictionary entries will be active immediately.

## Reverting

The tool creates a timestamped backup before writing. To revert:

```bash
# Find your backup
ls "~/Library/Application Support/Almond/dictionary.json.backup."*

# Restore it
cp "~/Library/Application Support/Almond/dictionary.json.backup.TIMESTAMP" \
   "~/Library/Application Support/Almond/dictionary.json"
```

## License

MIT
