"""Extract every registered endpoint from openapi.json and produce CSV/MD inventories."""

import json, csv, sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
openapi_path = root / "openapi.json"
out_dir = root / "docs" / "qa"
out_dir.mkdir(parents=True, exist_ok=True)

with open(openapi_path) as f:
    spec = json.load(f)

rows = []
idx = 0
for path, methods in sorted(spec.get("paths", {}).items()):
    for method in ("get", "post", "put", "patch", "delete", "head", "options"):
        if method not in methods:
            continue
        idx += 1
        op = methods[method]
        tags = op.get("tags", [])
        module = tags[0] if tags else "unknown"
        rows.append(
            {
                "id": idx,
                "method": method.upper(),
                "path": path,
                "module": module,
                "operation_id": op.get("operationId", ""),
                "summary": op.get("summary", ""),
            }
        )

# Write CSV
csv_path = out_dir / "all-endpoints.csv"
with open(csv_path, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["id", "method", "path", "module", "operation_id", "summary"])
    w.writeheader()
    w.writerows(rows)

# Write JSON
json_path = out_dir / "all-endpoints.json"
with open(json_path, "w") as f:
    json.dump(rows, f, indent=2)

# Write Markdown
md_path = out_dir / "all-endpoints.md"
with open(md_path, "w") as f:
    f.write("# PAW-GUARD Full Endpoint Inventory\n\n")
    f.write(f"**Total Endpoints:** {len(rows)}\n\n")
    f.write("| # | Method | Path | Module | Operation ID |\n")
    f.write("|---|--------|------|--------|-------------|\n")
    for r in rows:
        f.write(
            f"| {r['id']} | {r['method']} | `{r['path']}` | {r['module']} | {r['operation_id']} |\n"
        )

# Module summary
from collections import Counter

module_counts = Counter(r["module"] for r in rows)
summary_path = out_dir / "module-summary.md"
with open(summary_path, "w") as f:
    f.write("# PAW-GUARD Module Summary\n\n")
    f.write("| Module | Endpoints |\n")
    f.write("|--------|----------|\n")
    for mod, cnt in sorted(module_counts.items()):
        f.write(f"| {mod} | {cnt} |\n")
    f.write(f"\n**Total:** {len(rows)} endpoints across {len(module_counts)} modules\n")

print(f"Discovered {len(rows)} endpoints across {len(module_counts)} modules")
for mod, cnt in sorted(module_counts.items()):
    print(f"  {mod}: {cnt}")
print(f"\nFiles written to {out_dir}")
