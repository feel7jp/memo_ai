"""
HTML-JavaScript Consistency Checker
Verifies that all JavaScript selectors match the actual HTML structure
"""

import re
from pathlib import Path
from collections import defaultdict

# Paths
html_file = Path("c:/git/memo_ai/public/index.html")
js_dir = Path("c:/git/memo_ai/public/js")

# Read HTML
html_content = html_file.read_text(encoding="utf-8")

# Extract IDs from HTML
html_ids = set(re.findall(r'id="([^"]+)"', html_content))

# Extract classes from HTML (individual classes)
html_classes = set()
for match in re.findall(r'class="([^"]+)"', html_content):
    html_classes.update(match.split())

print("=" * 60)
print("HTML STRUCTURE")
print("=" * 60)
print(f"\nFound {len(html_ids)} IDs in HTML:")
for id_name in sorted(html_ids):
    print(f"  - {id_name}")

print(f"\nFound {len(html_classes)} classes in HTML:")
for class_name in sorted(html_classes):
    print(f"  - {class_name}")

# Now scan JavaScript files
js_ids_used = defaultdict(list)
js_classes_used = defaultdict(list)

for js_file in js_dir.glob("*.js"):
    js_content = js_file.read_text(encoding="utf-8")

    # Find getElementById calls
    for match in re.finditer(r"getElementById\(['\"](\w+)['\"]\)", js_content):
        id_name = match.group(1)
        js_ids_used[id_name].append(js_file.name)

    # Find querySelector/querySelectorAll with class selectors
    for match in re.finditer(
        r"querySelector(?:All)?\(['\"]\.([a-zA-Z0-9_-]+)", js_content
    ):
        class_name = match.group(1)
        js_classes_used[class_name].append(js_file.name)

print("\n" + "=" * 60)
print("JAVASCRIPT REFERENCES")
print("=" * 60)
print(f"\nFound {len(js_ids_used)} unique IDs referenced in JavaScript:")
for id_name in sorted(js_ids_used.keys()):
    files = ", ".join(set(js_ids_used[id_name]))
    print(f"  - {id_name} (in {files})")

print(f"\nFound {len(js_classes_used)} unique classes referenced in JavaScript:")
for class_name in sorted(js_classes_used.keys()):
    files = ", ".join(set(js_classes_used[class_name]))
    print(f"  - {class_name} (in {files})")

# Check for mismatches
print("\n" + "=" * 60)
print("CONSISTENCY CHECK")
print("=" * 60)

# IDs in JS but not in HTML
missing_ids = set(js_ids_used.keys()) - html_ids
if missing_ids:
    print(f"\n⚠️  IDs used in JavaScript but NOT found in HTML ({len(missing_ids)}):")
    for id_name in sorted(missing_ids):
        files = ", ".join(set(js_ids_used[id_name]))
        print(f"  ❌ {id_name} (used in {files})")
else:
    print("\n✅ All JavaScript ID references exist in HTML")

# Classes in JS but not in HTML
missing_classes = set(js_classes_used.keys()) - html_classes
if missing_classes:
    print(
        f"\n⚠️  Classes used in JavaScript but NOT found in HTML ({len(missing_classes)}):"
    )
    for class_name in sorted(missing_classes):
        files = ", ".join(set(js_classes_used[class_name]))
        print(f"  ❌ {class_name} (used in {files})")
else:
    print("\n✅ All JavaScript class references exist in HTML")

# IDs in HTML but never used in JS (informational)
unused_ids = html_ids - set(js_ids_used.keys())
if unused_ids:
    print(f"\nℹ️  IDs in HTML but never referenced in JavaScript ({len(unused_ids)}):")
    for id_name in sorted(unused_ids):
        print(f"  - {id_name}")

print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
if missing_ids or missing_classes:
    print(
        f"\n⚠️  Found {len(missing_ids)} ID mismatches and {len(missing_classes)} class mismatches"
    )
    print("These need to be fixed!")
else:
    print("\n✅ No mismatches found! All selectors are consistent.")
