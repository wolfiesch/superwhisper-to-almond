#!/usr/bin/env python3
"""
sw2almond — SuperWhisper to Almond Vocabulary Migration Tool

Migrates custom vocabulary and text replacements from SuperWhisper
to Almond's dictionary format on macOS.

SuperWhisper stores:
  - vocabulary: string[] (terms the speech model should recognize)
  - replacements: {id, original, with}[] (voice shortcuts / corrections)

Almond stores:
  - dictionary.json: {entries: {key: {canonical, isAutoAdded, variants[]}}, version: 1}

Usage:
  sw2almond                     # Auto-detect paths, dry-run by default
  sw2almond --apply             # Actually write to Almond dictionary
  sw2almond --scan-backups      # Include vocabulary from all backup files
  sw2almond --include-macros    # Also migrate text expansion macros
  sw2almond --sw-path PATH      # Custom SuperWhisper data path
  sw2almond --almond-path PATH  # Custom Almond dictionary path
  sw2almond --export FILE       # Export merged dictionary to file instead of Almond
"""

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime


# Default paths on macOS
DEFAULT_SW_PATH = os.path.expanduser("~/Documents/superwhisper")
DEFAULT_ALMOND_DICT = os.path.expanduser(
    "~/Library/Application Support/Almond/dictionary.json"
)


def find_superwhisper_path():
    """Auto-detect SuperWhisper data directory."""
    candidates = [
        DEFAULT_SW_PATH,
        os.path.expanduser("~/Documents/superwhisper-recordings"),
        os.path.expanduser("~/Documents/SuperWhisper"),
    ]
    for path in candidates:
        settings = os.path.join(path, "settings", "settings.json")
        if os.path.exists(settings):
            return path
    return None


def find_almond_dict_path():
    """Auto-detect Almond dictionary path."""
    candidates = [
        DEFAULT_ALMOND_DICT,
        os.path.expanduser(
            "~/Library/Application Support/Almond/dictionary.json"
        ),
        os.path.expanduser(
            "~/Library/Containers/caleb.almond/Data/Library/"
            "Application Support/Almond/dictionary.json"
        ),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    # Return default even if it doesn't exist yet (Almond may create it)
    return DEFAULT_ALMOND_DICT


def load_json(path):
    """Load a JSON file, returning None on failure."""
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError, PermissionError) as e:
        print(f"  Warning: Could not read {path}: {e}", file=sys.stderr)
        return None


def load_superwhisper_settings(sw_path, scan_backups=False):
    """Load SuperWhisper vocabulary and replacements.

    If scan_backups is True, also scans all backup files to build
    the most comprehensive vocabulary set possible.
    """
    vocabulary = set()
    replacements = {}  # keyed by (original, with) to deduplicate

    settings_dir = os.path.join(sw_path, "settings")

    # Load current settings
    current = load_json(os.path.join(settings_dir, "settings.json"))
    if current:
        for term in current.get("vocabulary", []):
            vocabulary.add(term)
        for r in current.get("replacements", []):
            key = (r.get("original", ""), r.get("with", ""))
            if key[0] and key[1]:
                replacements[key] = r

    # Optionally scan backup files for additional vocabulary
    if scan_backups:
        backup_pattern = os.path.join(settings_dir, "settings.backup.*.json")
        for backup_path in sorted(glob.glob(backup_pattern)):
            data = load_json(backup_path)
            if data:
                for term in data.get("vocabulary", []):
                    vocabulary.add(term)
                for r in data.get("replacements", []):
                    key = (r.get("original", ""), r.get("with", ""))
                    if key[0] and key[1]:
                        replacements.setdefault(key, r)

    return sorted(vocabulary), list(replacements.values())


def classify_replacement(replacement):
    """Classify a SuperWhisper replacement into categories.

    Returns one of:
      'spelling'  - Spelling correction (maps to Almond variant)
      'macro'     - Text expansion / personal info macro
      'command'   - Slash command or app command
    """
    original = replacement.get("original", "").lower()
    with_text = replacement.get("with", "")

    # Slash commands
    if with_text.startswith("/"):
        return "command"

    # Personal info macros (phrases that expand to data)
    macro_triggers = [
        "input my", "my email", "my address", "my phone",
        "my zip", "my name", "deployment on",
    ]
    if any(trigger in original for trigger in macro_triggers):
        return "macro"

    # URL expansions
    if "://" in with_text or with_text.startswith("http"):
        return "macro"

    # Everything else is a spelling correction
    return "spelling"


def build_almond_entries(vocabulary, replacements, include_macros=False):
    """Convert SuperWhisper data to Almond dictionary entries.

    Returns a dict of {lowercase_key: {canonical, isAutoAdded, variants}}.
    """
    entries = {}

    # Convert vocabulary terms
    for term in vocabulary:
        key = term.lower().strip()
        if not key:
            continue
        if key not in entries:
            entries[key] = {
                "canonical": term,
                "isAutoAdded": False,
                "variants": [],
            }

    # Convert replacements
    for r in replacements:
        category = classify_replacement(r)
        original = r.get("original", "").strip()
        with_text = r.get("with", "").strip()

        if category == "command":
            # Slash commands don't map to dictionary
            continue

        if category == "macro" and not include_macros:
            # Skip macros unless explicitly included
            continue

        # For spelling corrections: canonical = the corrected form,
        # variant = the spoken/misspoken form
        key = with_text.lower()
        if not key:
            continue

        if key in entries:
            # Add the original as a variant if not already there
            if original and original not in entries[key]["variants"]:
                entries[key]["variants"].append(original)
        else:
            entries[key] = {
                "canonical": with_text,
                "isAutoAdded": False,
                "variants": [original] if original else [],
            }

    return entries


def load_almond_dictionary(almond_path):
    """Load existing Almond dictionary, returning empty structure if missing."""
    if os.path.exists(almond_path):
        data = load_json(almond_path)
        if data and "entries" in data:
            return data
    return {"entries": {}, "version": 1}


def merge_dictionaries(existing, new_entries):
    """Merge new entries into existing Almond dictionary.

    Preserves existing entries. For conflicts, merges variants.
    Returns (merged_dict, stats).
    """
    merged = dict(existing.get("entries", {}))
    stats = {"added": 0, "merged_variants": 0, "skipped": 0}

    for key, entry in new_entries.items():
        if key in merged:
            # Entry exists — merge variants only
            existing_variants = set(merged[key].get("variants", []))
            new_variants = set(entry.get("variants", []))
            added_variants = new_variants - existing_variants
            if added_variants:
                merged[key]["variants"] = sorted(
                    existing_variants | new_variants
                )
                stats["merged_variants"] += len(added_variants)
            else:
                stats["skipped"] += 1
        else:
            merged[key] = entry
            stats["added"] += 1

    return {"entries": merged, "version": 1}, stats


def backup_file(path):
    """Create a timestamped backup of a file."""
    if not os.path.exists(path):
        return None
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{path}.backup.{timestamp}"
    shutil.copy2(path, backup_path)
    return backup_path


def print_summary(vocabulary, replacements, new_entries, stats, existing_keys,
                   dry_run=True):
    """Print a human-readable migration summary."""
    print()
    print("=" * 60)
    print("  SuperWhisper -> Almond Migration Summary")
    print("=" * 60)
    print()

    # Source data
    print(f"  SuperWhisper vocabulary terms: {len(vocabulary)}")
    print(f"  SuperWhisper replacements:     {len(replacements)}")

    # Classify replacements
    categories = {"spelling": [], "macro": [], "command": []}
    for r in replacements:
        cat = classify_replacement(r)
        categories[cat].append(r)

    if categories["spelling"]:
        print(f"    - Spelling corrections: {len(categories['spelling'])}")
    if categories["macro"]:
        print(f"    - Text macros:          {len(categories['macro'])}")
    if categories["command"]:
        print(f"    - Slash commands:        {len(categories['command'])} (skipped)")
    print()

    # Migration results
    print(f"  New Almond entries to add:     {stats['added']}")
    print(f"  Variants merged into existing: {stats['merged_variants']}")
    print(f"  Already in Almond (skipped):   {stats['skipped']}")
    print()

    # Show only entries that would actually be added (not skipped)
    if stats["added"] > 0:
        print("  New entries:")
        for key, entry in sorted(new_entries.items(),
                                  key=lambda kv: kv[1]["canonical"].lower()):
            if key in existing_keys:
                continue  # Already in Almond, skip display
            canonical = entry["canonical"]
            variants = entry.get("variants", [])
            variant_str = f" (variants: {', '.join(variants)})" if variants else ""
            print(f"    + {canonical}{variant_str}")
        print()

    if dry_run:
        print("  Mode: DRY RUN (no changes made)")
        print("  Run with --apply to write changes")
    else:
        print("  Mode: APPLIED")

    print()
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Migrate SuperWhisper vocabulary to Almond",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                        Preview migration (dry run)
  %(prog)s --scan-backups         Include vocabulary from all backups
  %(prog)s --apply                Write changes to Almond dictionary
  %(prog)s --export merged.json   Export to file instead of Almond
  %(prog)s --include-macros       Also migrate text expansion macros
        """,
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write changes (default is dry-run)",
    )
    parser.add_argument(
        "--scan-backups",
        action="store_true",
        help="Scan SuperWhisper backup files for additional vocabulary",
    )
    parser.add_argument(
        "--include-macros",
        action="store_true",
        help="Include text expansion macros (personal info, URLs, etc.)",
    )
    parser.add_argument(
        "--sw-path",
        default=None,
        help="Path to SuperWhisper data directory",
    )
    parser.add_argument(
        "--almond-path",
        default=None,
        help="Path to Almond dictionary.json",
    )
    parser.add_argument(
        "--export",
        default=None,
        metavar="FILE",
        help="Export merged dictionary to file instead of writing to Almond",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON (for scripting)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Apply even if Almond is running (not recommended)",
    )

    args = parser.parse_args()

    # Find SuperWhisper
    sw_path = args.sw_path or find_superwhisper_path()
    if not sw_path:
        print(
            "Error: Could not find SuperWhisper data directory.",
            file=sys.stderr,
        )
        print(
            "  Try: --sw-path ~/Documents/superwhisper",
            file=sys.stderr,
        )
        sys.exit(1)

    settings_file = os.path.join(sw_path, "settings", "settings.json")
    if not os.path.exists(settings_file):
        print(
            f"Error: SuperWhisper settings not found at {settings_file}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Check if Almond is running (critical: Almond overwrites dictionary.json)
    if args.apply and not args.export:
        try:
            result = subprocess.run(
                ["pgrep", "-f", "Almond.app"],
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                print(
                    "\n  WARNING: Almond is currently running!",
                    file=sys.stderr,
                )
                print(
                    "  Almond may overwrite dictionary.json with its in-memory state,",
                    file=sys.stderr,
                )
                print(
                    "  which would discard the migrated entries.",
                    file=sys.stderr,
                )
                print(
                    "\n  Please quit Almond first, then re-run this command.",
                    file=sys.stderr,
                )
                print(
                    "  (Use --force to apply anyway, at your own risk.)\n",
                    file=sys.stderr,
                )
                if not args.force:
                    sys.exit(1)
        except FileNotFoundError:
            pass  # pgrep not available, skip check

    if not args.json:
        print(f"  SuperWhisper data: {sw_path}")

    # Find Almond
    almond_path = args.almond_path or find_almond_dict_path()
    if not args.json:
        print(f"  Almond dictionary: {almond_path}")

    # Load SuperWhisper data
    vocabulary, replacements = load_superwhisper_settings(
        sw_path, scan_backups=args.scan_backups
    )

    if not vocabulary and not replacements:
        print("\n  No vocabulary or replacements found in SuperWhisper.")
        sys.exit(0)

    # Build Almond entries from SuperWhisper data
    new_entries = build_almond_entries(
        vocabulary, replacements, include_macros=args.include_macros
    )

    # Load existing Almond dictionary and merge
    almond_dict = load_almond_dictionary(almond_path)
    merged, stats = merge_dictionaries(almond_dict, new_entries)

    # Track existing keys for display purposes
    existing_keys = set(almond_dict.get("entries", {}).keys())

    # Output
    if args.json:
        result = {
            "source": {
                "vocabulary_count": len(vocabulary),
                "replacement_count": len(replacements),
                "vocabulary": vocabulary,
            },
            "migration": stats,
            "merged_dictionary": merged,
        }
        print(json.dumps(result, indent=2))
    else:
        print_summary(vocabulary, replacements, new_entries, stats,
                       existing_keys, dry_run=not args.apply)

    # Write if --apply or --export
    if args.export:
        with open(args.export, "w") as f:
            json.dump(merged, f, indent=2, ensure_ascii=False)
        print(f"  Exported to: {args.export}")

    elif args.apply:
        if stats["added"] == 0 and stats["merged_variants"] == 0:
            print("  Nothing to change — Almond dictionary is already up to date.")
            return

        # Backup existing dictionary
        if os.path.exists(almond_path):
            backup = backup_file(almond_path)
            print(f"  Backup created: {backup}")

        # Write merged dictionary
        os.makedirs(os.path.dirname(almond_path), exist_ok=True)
        with open(almond_path, "w") as f:
            json.dump(merged, f, indent=2, ensure_ascii=False)
        print(f"  Dictionary written to: {almond_path}")
        print()
        print("  Restart Almond to pick up the new vocabulary.")


if __name__ == "__main__":
    main()
