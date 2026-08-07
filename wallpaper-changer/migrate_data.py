#!/usr/bin/env python3
"""
Data Migration Utility

Migrates the old data.json format to the new unified format used by
the Earth View source plugin. Also supports importing from external
JSON sources (limhenry/earthview, etc.)

Old format:
    {"Country": "X", "Region": "Y", "Image URL": "...", "Google Maps URL": "...", "ID": 1003}

New format:
    {"country": "X", "region": "Y", "image": "https://...", "map": "https://...", "id": 1003}
"""

import json
import argparse
from pathlib import Path


def migrate_entry(entry: dict) -> dict:
    """Convert an old-format entry to new format."""
    # Already in new format
    if "image" in entry and "map" in entry:
        # Ensure URLs have protocol
        result = entry.copy()
        if result.get("image") and not result["image"].startswith("http"):
            result["image"] = "https://" + result["image"]
        if result.get("map") and not result["map"].startswith("http"):
            result["map"] = "https://" + result["map"]
        return result

    # Old format conversion
    image_url = entry.get("Image URL", "")
    if image_url and not image_url.startswith("http"):
        image_url = "https://" + image_url

    maps_url = entry.get("Google Maps URL", "")
    if maps_url and not maps_url.startswith("http"):
        maps_url = "https://" + maps_url

    return {
        "country": entry.get("Country", ""),
        "region": entry.get("Region", ""),
        "image": image_url,
        "map": maps_url,
        "id": entry.get("ID", 0),
    }


def migrate_file(input_path: Path, output_path: Path, merge: bool = False):
    """
    Migrate a data.json file from old format to new format.

    Args:
        input_path: Path to the old format JSON file
        output_path: Path to write the new format JSON file
        merge: If True and output exists, merge entries (deduplicate by ID)
    """
    # Load input
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Migrate all entries
    migrated = [migrate_entry(entry) for entry in data]

    # Merge with existing if requested
    if merge and output_path.exists():
        with open(output_path, 'r', encoding='utf-8') as f:
            existing = json.load(f)
        # Deduplicate by ID
        existing_ids = {e.get("id") for e in existing}
        for entry in migrated:
            if entry.get("id") not in existing_ids:
                existing.append(entry)
                existing_ids.add(entry.get("id"))
        migrated = existing

    # Remove entries with no image URL
    migrated = [e for e in migrated if e.get("image")]

    # Sort by ID
    migrated.sort(key=lambda x: x.get("id", 0))

    # Write output
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(migrated, f, indent=2, ensure_ascii=False)

    print(f"Migrated {len(migrated)} entries to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Migrate Earth View data.json to new format")
    parser.add_argument(
        '--input', '-i', type=str,
        default=str(Path(__file__).parent / "data.json"),
        help="Input JSON file (old format)")
    parser.add_argument(
        '--output', '-o', type=str,
        default=str(Path(__file__).parent / "data.json"),
        help="Output JSON file (new format)")
    parser.add_argument(
        '--merge', '-m', action='store_true',
        help="Merge with existing output file instead of overwriting")
    parser.add_argument(
        '--dry-run', '-n', action='store_true',
        help="Show what would be done without writing")

    args = parser.parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        return 1

    if args.dry_run:
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        migrated = [migrate_entry(entry) for entry in data[:5]]
        print(f"Would migrate {len(data)} entries.")
        print("Sample output (first 5):")
        print(json.dumps(migrated, indent=2))
        return 0

    migrate_file(input_path, output_path, args.merge)
    return 0


if __name__ == "__main__":
    exit(main())
