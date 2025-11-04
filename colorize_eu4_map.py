#!/usr/bin/env python3
"""Colorize EU4 SVG provinces based on a territory-to-color mapping."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

try:
    from lxml import etree as ET  # type: ignore
    HAS_LXML = True
except ModuleNotFoundError:  # pragma: no cover - fallback when lxml is unavailable
    import xml.etree.ElementTree as ET  # type: ignore
    HAS_LXML = False

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
for prefix, uri in ("", SVG_NS), ("xlink", XLINK_NS):
    try:
        ET.register_namespace(prefix, uri)
    except (AttributeError, ValueError):
        # xml.etree in Python <3.8 lacks register_namespace; ignore in that case
        pass

TITLE_PATTERN = re.compile(r"^(?P<name>.+?)\s*\(#\d+\)\s*$")
TARGET_TAGS = {"path", "polygon", "polyline"}


class ConfigEntry:
    """Represents a single province coloring rule."""

    __slots__ = ("normalized", "label", "territory", "color")

    def __init__(self, normalized: str, label: str, territory: str, color: str) -> None:
        self.normalized = normalized
        self.label = label
        self.territory = territory
        self.color = color


def normalize_name(name: str) -> str:
    return " ".join(name.split()).strip().lower()


def extract_province_name(title: str) -> str:
    title = title.strip()
    match = TITLE_PATTERN.match(title)
    if match:
        return match.group("name").strip()
    return title


def load_config(config_path: Path) -> Tuple[Dict[str, ConfigEntry], List[str], List[Tuple[str, str, str]]]:
    data = json.loads(config_path.read_text(encoding="utf-8"))
    lookup: Dict[str, ConfigEntry] = {}
    order: List[str] = []
    overrides: List[Tuple[str, str, str]] = []
    for territory, payload in data.items():
        color = payload.get("color")
        provinces: Sequence[str] = payload.get("provinces", [])
        if not color:
            raise ValueError(f"Territory '{territory}' is missing the 'color' field")
        for province in provinces:
            norm = normalize_name(province)
            if not norm:
                continue
            if norm not in lookup:
                order.append(norm)
            else:
                previous = lookup[norm]
                overrides.append((province, territory, previous.territory))
            lookup[norm] = ConfigEntry(norm, province, territory, color)
    return lookup, order, overrides


def local_name(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def iter_province_elements(root: ET.Element) -> Iterable[Tuple[ET.Element, str]]:
    for elem in root.iter():
        if local_name(elem.tag) not in TARGET_TAGS:
            continue
        title_elem = next((child for child in list(elem) if local_name(child.tag) == "title"), None)
        if title_elem is None or title_elem.text is None:
            continue
        yield elem, extract_province_name(title_elem.text)


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Path to the source SVG map")
    parser.add_argument("--config", required=True, type=Path, help="Path to the territory color JSON file")
    parser.add_argument("--output", required=True, type=Path, help="Destination for the recolored SVG")
    return parser.parse_args(argv)


def colorize(svg_path: Path, config_path: Path, output_path: Path) -> None:
    color_lookup, ordered_names, overrides = load_config(config_path)

    if not svg_path.exists():
        raise FileNotFoundError(f"SVG not found: {svg_path}")

    parser = ET.XMLParser(remove_blank_text=False) if HAS_LXML else None
    tree = ET.parse(str(svg_path), parser=parser) if parser else ET.parse(str(svg_path))
    root = tree.getroot()

    matched: Dict[str, ConfigEntry] = {}
    colored_segments = 0

    for elem, province_name in iter_province_elements(root):
        norm = normalize_name(province_name)
        entry = color_lookup.get(norm)
        if not entry:
            continue
        existing_style = elem.get("style")
        new_style = f'fill:{entry.color}'
        if existing_style:
            elem.set("style", f"{existing_style}; {new_style}")
        else:
            elem.set("style", new_style)
        matched.setdefault(norm, ConfigEntry(norm, province_name, entry.territory, entry.color))
        colored_segments += 1

    missing = [color_lookup[name] for name in ordered_names if name not in matched]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(str(output_path), encoding="utf-8", xml_declaration=False)

    print(f"Configured provinces: {len(ordered_names)}")
    print(f"Unique provinces colored: {len(matched)}")
    print(f"SVG elements recolored: {colored_segments}")
    print(f"Output written to: {output_path}")
    if overrides:
        print("\nNote: duplicate province entries detected (later entries override earlier ones):")
        for province, new_territory, old_territory in overrides:
            print(f"  - {province}: {old_territory} -> {new_territory}")
    if missing:
        print("\nUnmapped provinces (in config but not found in SVG):")
        for entry in missing:
            print(f"  - {entry.label} (territory: {entry.territory})")
    else:
        print("\nAll configured provinces were found in the SVG.")


def main(argv: Sequence[str]) -> int:
    args = parse_args(argv)
    try:
        colorize(args.input, args.config, args.output)
    except Exception as exc:  # pylint: disable=broad-except
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
