#!/usr/bin/env python3
"""
Generate minimal V2 block: keep only properties NOT overridden by V4.
V5 is after V4, so V5-override check is handled by keeping V2's unique props as fallback.
"""
import re
from collections import defaultdict, OrderedDict

CSS_FILE = "/Users/zhuanzmima0000/SANGUO/web/src/styles.css"
with open(CSS_FILE) as f:
    css = f.read()

def parse_css_block(text):
    """Parse CSS into OrderedDict{selector: [(prop, val), ...]}"""
    rules = OrderedDict()
    i = 0
    while i < len(text):
        while i < len(text) and text[i] in ' \t\n\r':
            i += 1
        if i >= len(text) or text[i] == '}':
            i += 1
            continue
        if text[i:i+2] == '/*':
            end = text.find('*/', i)
            if end == -1: break
            i = end + 2
            continue
        # Read selector
        sel_start = i
        while i < len(text) and text[i] != '{':
            i += 1
        if i >= len(text): break
        selector = text[sel_start:i].strip()
        i += 1
        # Read properties
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
        if selector:
            if selector in rules:
                rules[selector].extend(props)
            else:
                rules[selector] = list(props)
    return rules

# Extract blocks
v2_match = re.search(r'/\* 主操作界面水墨轻量版.*?\*/\n(.*?)(?=\n/\* 主操作界面第三版)', css, re.DOTALL)
v4_match = re.search(r'/\* 主操作界面第四版.*?\*/\n(.*?)(?=\n/\* ═+)', css, re.DOTALL)

v2 = parse_css_block(v2_match.group(1))
v4 = parse_css_block(v4_match.group(1)) if v4_match else {}

# Build V4 property lookup: {selector: set(prop_names)}
v4_prop_names = {}
for sel, props in v4.items():
    v4_prop_names[sel] = set(k for k, v in props)

# For each V2 selector, keep only properties NOT in V4
minimal_v2_lines = []
kept_count = 0
dropped_count = 0

for selector, v2_props in v2.items():
    v4_props = v4_prop_names.get(selector, set())
    unique_props = [(k, v) for k, v in v2_props if k not in v4_props]
    if unique_props:
        props_str = ";".join(f"{k}:{v}" for k, v in unique_props)
        minimal_v2_lines.append(f"{selector}{{{props_str}}}")
        kept_count += len(unique_props)
    dropped_count += len(v2_props) - len(unique_props)

# Handle @media blocks specially
# The parser might have captured @media as a selector with nested content
# Let's check if there are @media "selectors" and handle them
media_lines = []
for line in minimal_v2_lines:
    if line.startswith('@media'):
        media_lines.append(line)

regular_lines = [l for l in minimal_v2_lines if not l.startswith('@media')]

# Generate output
output_lines = ["/* 主操作界面水墨轻量版（精简：仅保留 V4 未覆盖的属性） */"]
output_lines.extend(regular_lines)
if media_lines:
    output_lines.extend(media_lines)

output = "\n".join(output_lines)

# Stats
total_v2_props = sum(len(props) for props in v2.values())
print(f"V2 total properties: {total_v2_props}")
print(f"Kept (unique to V2): {kept_count}")
print(f"Dropped (overridden by V4): {total_v2_props - kept_count}")
print(f"Regular rules: {len(regular_lines)}")
print(f"@media rules: {len(media_lines)}")
print(f"\n=== Generated minimal V2 ({len(output)} chars) ===")
print(output[:2000])
if len(output) > 2000:
    print(f"\n... ({len(output) - 2000} more chars)")

# Write to file for review
with open("/tmp/v2_minimal.css", "w") as f:
    f.write(output)
print(f"\nWritten to /tmp/v2_minimal.css")
