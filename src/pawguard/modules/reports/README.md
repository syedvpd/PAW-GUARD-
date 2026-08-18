# Reports Module

Cross-module report generation in PDF, CSV, and Excel formats.

---

## Architecture

```
reports/
  router.py          # 4 endpoints
  service.py         # ReportService (aggregation + file generation)
```

## Endpoints

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| POST | `/reports/generate` | `reports:create` | Generate a report |
| GET | `/reports/types` | `reports:read` | List available report types |
| GET | `/reports/formats` | `reports:read` | List available formats |
| GET | `/reports/download/{filename}` | `reports:read` | Download generated report |

## Report Types

- Rescue operations summary
- Adoption pipeline report
- Medical records report
- Inventory stock report
- Financial summary / P&L
- Volunteer hours report
- Donation history report

## Report Formats

- PDF (reportlab)
- CSV (Python csv module)
- Excel (openpyxl)

## Flow

```
POST /reports/generate {report_type, format, filters?}
  -> Aggregate data from relevant module(s)
  -> Generate file in requested format
  -> Upload to storage
  -> Return download URL
```
