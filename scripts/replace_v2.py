#!/usr/bin/env python3
"""Replace V2 block (lines 160-210) with minimal version: only V4-unique properties."""
import re
from collections import OrderedDict

CSS_FILE = "/Users/zhuanzmima0000/SANGUO/web/src/styles.css"
with open(CSS_FILE) as f:
    css = f.read()

def parse_css_block(text):
    rules = OrderedDict()
    i = 0
    while i < len(text):
        while i < len(text) and text[i] in ' \t\n\r': i += 1
        if i >= len(text) or text[i] == '}':
            i += 1; continue
        if text[i:i+2] == '/*':
            end = text.find('*/', i)
            if end == -1: break
            i = end + 2; continue
        sel_start = i
        while i < len(text) and text[i] != '{': i += 1
        if i >= len(text): break
        selector = text[sel_start:i].strip()
        i += 1
        prop_start = i
        depth = 1
        while i < len(text) and depth > 0:
            if text[i] == '{': depth += 1
            elif text[i] == '}': depth -= 1
            i += 1
        props_text = text[prop_start:i-1].strip()
        props = []
        for part in props_text.split(';'):
            part = part.strip()
            if ':' in part:
                idx = part.index(':')
                k = part[:idx].strip()
                v = part[idx+1:].strip()
                props.append((k, v))
        if selector and not selector.startswith('@media'):
            if selector in rules:
                rules[selector].extend(props)
            else:
                rules[selector] = list(props)
    return rules

# Extract V2 and V4
v2_match = re.search(r'(/\* 主操作界面水墨轻量版.*?\*/\n)(.*?)(?=\n/\* 主操作界面第三版)', css, re.DOTALL)
v4_match = re.search(r'/\* 主操作界面第四版.*?\*/\n(.*?)(?=\n/\* ═+)', css, re.DOTALL)

v2_text = v2_match.group(2)
v4 = parse_css_block(v4_match.group(1)) if v4_match else {}

# V4 property names by selector
v4_prop_names = {sel: set(k for k, v in props) for sel, props in v4.items()}

# --- Rebuild V2 with only unique properties ---
# Process line-by-line to handle @media correctly
# Strategy: for non-media lines, remove overridden properties
# For @media lines, keep as-is

# Split V2 text into logical segments:
# - Comment lines (keep)
# - @media blocks (keep as-is)
# - Regular rule lines (remove overridden props)

output_lines = []
for line in v2_text.split('\n'):
    line_stripped = line.strip()
    if not line_stripped:
        continue
    # Skip comment lines
    if line_stripped.startswith('/*') or line_stripped.startswith('*'):
        continue
    # Keep @media blocks entirely
    if '@media' in line_stripped:
        output_lines.append(line_stripped)
        continue

    # Process regular rules - this line may contain multiple rules
    # Split by finding rule boundaries
    # Each rule: selector{props}
    # But lines may be minified with multiple rules
    # Parse using the same logic
    i = 0
    while i < len(line_stripped):
        # Skip whitespace
        while i < len(line_stripped) and line_stripped[i] in ' \t': i += 1
        if i >= len(line_stripped): break

        # Read selector
        sel_start = i
        while i < len(line_stripped) and line_stripped[i] != '{':
            i += 1
        if i >= len(line_stripped): break
        selector = line_stripped[sel_start:i].strip()
        i += 1  # skip {

        # Read props (up to })
        prop_start = i
        depth = 1
        while i < len(line_stripped) and depth > 0:
            if line_stripped[i] == '{': depth += 1
            elif line_stripped[i] == '}': depth -= 1
            i += 1
        props_text = line_stripped[prop_start:i-1].strip()

        # Parse and filter properties
        v4_props = v4_prop_names.get(selector, set())
        kept_props = []
        for part in props_text.split(';'):
            part = part.strip()
            if ':' in part:
                idx = part.index(':')
                k = part[:idx].strip()
                v = part[idx+1:].strip()
                if k not in v4_props:
                    kept_props.append(f"{k}:{v}")

        if kept_props:
            rule = selector + "{" + ";".join(kept_props) + "}"
            output_lines.append(rule)

# Build new V2 block
new_v2 = "/* 主操作界面水墨轻量版（精简：仅保留 V4 未覆盖的属性） */\n"
new_v2 += "\n".join(output_lines)
new_v2 += "\n"

# Replace in CSS
old_v2_full = v2_match.group(0)  # includes comment + content
new_css = css.replace(old_v2_full, new_v2.rstrip('\n'))

# Verify
old_len = len(old_v2_full)
new_len = len(new_v2)
print(f"Old V2 block: {old_len} chars")
print(f"New V2 block: {new_len} chars")
print(f"Savings: {old_len - new_len} chars ({100*(old_len-new_len)//old_len}%)")
print(f"Old V2 lines: {old_v2_full.count(chr(10))}")
print(f"New V2 lines: {new_v2.count(chr(10))}")

# Write dry-run
with open("/tmp/v2_replaced.css", 'w') as f:
    f.write(new_css)
print(f"\n✓ Dry-run written to /tmp/v2_replaced.css (not applied yet)")
print(f"  Review with: diff {CSS_FILE} /tmp/v2_replaced.css | head -50")
