#!/usr/bin/env python3
"""
C4: 在 styles.css 中建立 --ink-*-rgb 变量体系，
    把硬编码 rgba(R,G,B,alpha) 替换为 rgba(var(--ink-xxx-rgb),alpha)。
"""
import re, sys

CSS_FILE = "/Users/zhuanzmima0000/SANGUO/web/src/styles.css"

with open(CSS_FILE) as f:
    css = f.read()

# --- Color families ---
# (var_suffix, canonical_rgb, rgb_tolerance, alpha_tolerance)
FAMILIES = [
    ("seal",        (138, 42, 32),   28, 0.20),  # --ink-seal #8a2a20
    ("line",        (60, 45, 25),    28, 0.20),  # --ink-line rgba(60,45,25)
    ("paper",       (232, 220, 184), 22, 0.18),  # --ink-paper #e8dcb8
    ("paper-soft",  (242, 232, 200), 22, 0.18),  # --ink-paper-soft #f2e8c8
    ("dark",        (26, 24, 18),    20, 0.15),  # --ink-bg #1a1812
    ("jade",        (62, 107, 94),   28, 0.20),  # --ink-jade #3e6b5e
    ("gold",        (185, 144, 77),  28, 0.20),  # --ink-gold #b9904d
    ("line-warm",   (111, 86, 48),   22, 0.18),  # new: warm brown border/wash
    ("paper-warm",  (218, 202, 160), 22, 0.18),  # new: warm paper wash
]

rgba_re = re.compile(r'rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([0-9.]+)\s*\)')

def match_family(r, g, b):
    for name, (cr, cg, cb), rtol, _ in FAMILIES:
        if abs(r-cr) <= rtol and abs(g-cg) <= rtol and abs(b-cb) <= rtol:
            return name
    return None

# --- Replacement ---
count = 0
def replace_rgba(m):
    global count
    full = m.group(0)
    # Skip if inside var(...)
    start = m.start()
    before = css[max(0, start-20):start]
    if 'var(' in before:
        return full

    r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
    a = m.group(4).strip()
    family = match_family(r, g, b)
    if family:
        count += 1
        return f"rgba(var(--ink-{family}-rgb),{a})"
    return full

new_css = rgba_re.sub(replace_rgba, css)

# --- Add --ink-*-rgb variables to V5 :root ---
# Insert after --ink-bg: #1a1812; etc.
rgb_vars = "\n".join(
    f"  --ink-{name}-rgb: {rgb[0]}, {rgb[1]}, {rgb[2]};"
    for name, rgb, _, _ in FAMILIES
)

# Find the line "--ink-bg: #1a1812;" and add rgb vars after it
anchor = "  --ink-bg: #1a1812;"
if anchor in new_css:
    new_css = new_css.replace(anchor, anchor + "\n" + rgb_vars, 1)
    print("✓ Added --ink-*-rgb variables to :root")
else:
    print("✗ Could not find anchor for --ink-*-rgb insertion")
    sys.exit(1)

# --- Write ---
with open(CSS_FILE, 'w') as f:
    f.write(new_css)

print(f"✓ Replaced {count} hardcoded rgba() values")

# --- Verify ---
# Count remaining hardcoded rgba (not using var)
remaining = len(rgba_re.findall(new_css)) - new_css.count('rgba(var(--ink-')
print(f"  Remaining hardcoded rgba(): {remaining}")
print(f"  Total rgba(var(--ink-*)): {new_css.count('rgba(var(--ink-')}")
