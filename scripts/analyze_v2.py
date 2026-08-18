#!/usr/bin/env python3
"""Analyze V2 (160-210) — for each selector/property, check if V4/V5 override it."""
import re
from collections import defaultdict

CSS_FILE = "/Users/zhuanzmima0000/SANGUO/web/src/styles.css"
with open(CSS_FILE) as f:
    css = f.read()

# --- CSS parser (handles the simplified V2 block) ---
def parse_css_block(text):
    """Parse CSS into {selector: [prop: val, ...]}"""
    rules = {}
    i = 0
    while i < len(text):
        # Skip whitespace
        while i < len(text) and text[i] in ' \t\n\r':
            i += 1
        if i >= len(text) or text[i] == '}':
            i += 1
            continue
        # Skip comments
        if text[i:i+2] == '/*':
            end = text.find('*/', i)
            if end == -1:
                break
            i = end + 2
            continue

        # Read selector (up to {)
        sel_start = i
        while i < len(text) and text[i] != '{':
            i += 1
        if i >= len(text):
            break
        selector = text[sel_start:i].strip()
        i += 1  # skip {

        # Read properties (up to })
        prop_start = i
        depth = 1
        while i < len(text) and depth > 0:
            if text[i] == '{': depth += 1
            elif text[i] == '}': depth -= 1
            i += 1
        props_text = text[prop_start:i-1].strip()

        # Parse properties
        props = []
        for part in props_text.split(';'):
            part = part.strip()
            if ':' in part:
                idx = part.index(':')
                k = part[:idx].strip().lstrip('-')
                v = part[idx+1:].strip()
                props.append((k, v))

        if selector:
            if selector in rules:
                rules[selector].extend(props)
            else:
                rules[selector] = list(props)

    return rules

# --- Extract version blocks ---
# Find by comment markers
v2_match = re.search(r'/\* 主操作界面水墨轻量版.*?\*/\n(.*?)(?=\n/\* 主操作界面第三版)', css, re.DOTALL)
v4_match = re.search(r'/\* 主操作界面第四版.*?\*/\n(.*?)(?=\n/\* ═+)', css, re.DOTALL)
v5_match = re.search(r'/\* ═+.*?V5.*?╕+.*?\*/\n(.*)', css, re.DOTALL)

if not v2_match:
    print("ERROR: Could not find V2 block")
    exit(1)

v2 = parse_css_block(v2_match.group(1))
v4 = parse_css_block(v4_match.group(1)) if v4_match else {}
v5 = parse_css_block(v5_match.group(1)) if v5_match else {}

print(f"Parsed: V2={len(v2)} selectors, V4={len(v4)} selectors, V5={len(v5)} selectors")

# --- Analyze ---
# For each V2 selector+property, check if V4 or V5 overrides
unique_props = []    # Properties NOT overridden by V4/V5
overridden_props = []  # Properties overridden by V4 or V5

for selector, v2_props in v2.items():
    v4_props_dict = {k: v for k, v in v4.get(selector, [])}
    v5_props_dict = {k: v for k, v in v5.get(selector, [])}

    for prop, val in v2_props:
        if prop in v5_props_dict:
            overridden_props.append((selector, prop, "V5"))
        elif prop in v4_props_dict:
            overridden_props.append((selector, prop, "V4"))
        else:
            unique_props.append((selector, prop, val))

print(f"\n=== SUMMARY ===")
print(f"Overridden by V4/V5: {len(overridden_props)} properties")
print(f"Unique (NOT overridden): {len(unique_props)} properties")

# --- Group unique by selector ---
unique_by_selector = defaultdict(list)
for sel, prop, val in unique_props:
    unique_by_selector[sel].append((prop, val))

print(f"\n=== Unique properties by selector ===")
for sel, props in sorted(unique_by_selector.items()):
    print(f"\n  {sel}")
    for prop, val in props:
        # Truncate long values
        display_val = val[:80] + "..." if len(val) > 80 else val
        print(f"    {prop}: {display_val}")

# --- Count overridden by source ---
v4_overrides = sum(1 for _, _, src in overridden_props if src == "V4")
v5_overrides = sum(1 for _, _, src in overridden_props if src == "V5")
print(f"\n=== Override sources ===")
print(f"  V4 overrides: {v4_overrides}")
print(f"  V5 overrides: {v5_overrides}")
