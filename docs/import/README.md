# Importing an operator's data

Day one at a new operator, the data lives in spreadsheets: clients, coaches, the season's trips,
rosters and who has paid. The importer loads that into IGS OS without a migration project:
upload the workbook, read the dry-run report, fix what it flags, apply.

## Templates

`templates/igs-os-import.xlsx` has one sheet per kind of data plus a README sheet; the CSVs are
the same sheets one per file. Bold headers are required; each header has a comment with what it
means and the allowed values. Regenerate after changing the specs:

```bash
uv run igs-import templates docs/import/templates
```

| Sheet | What it holds | Rows match by |
|---|---|---|
| `accounts` | Clients: universities, clubs, schools, family groups | `name` |
| `stakeholders` | Adults at each client (coach, AD, finance…) | `account_name` + `email` (or `name`) |
| `providers` | Hotels, buses, venues, referees, guides, rival clubs | `name` + `kind` + `city` |
| `trips` | One row per tour; `code` is how the next two sheets refer to it | `code` |
| `travelers` | Roster per trip: players, staff, parents | `trip_code` + `full_name` |
| `payments` | Enrollment fees, installments, balance per trip | `trip_code` + `payment_ref` |

Their own spreadsheets work too. Sheet names and headers are matched in English or Spanish
("Clientes", "Viajes", "Plantel", "Pagos"; "Código", "Fecha de inicio", "Monto"…). With
`--llm-mapping`, headers nothing matches go to an AI mapper (below).

## Running it

```bash
# Report only (the default): what would be created or updated, row by row.
uv run igs-import --tenant igs --dry-run clientes.xlsx
# Write it.
uv run igs-import --tenant igs --apply clientes.xlsx
# A CSV whose file name doesn't say what it is; slash dates written day/month.
uv run igs-import --tenant igs --entity trips --date-order dmy export.csv
```

The command exits 0 when the file is clean, 1 when it has errors (nothing written), and 2 when
the file can't be read. `--json` prints the full report.

From the API (admins only: an owner, or an API key with the `igs:admin` scope, minted with
`mint_api_key.py --scope igs:admin`):

```bash
curl -X POST "$API/v1/imports?filename=clientes.xlsx" \
  -H "Authorization: Bearer $IGS_ADMIN_KEY" --data-binary @clientes.xlsx           # dry run
curl -X POST "$API/v1/imports?filename=clientes.xlsx&dry_run=false" \
  -H "Authorization: Bearer $IGS_ADMIN_KEY" --data-binary @clientes.xlsx           # apply
```

The body is the raw file (up to 5 MB). The response is the same report as the CLI's.

## Rules

- **Dry run first.** Nothing is written unless asked, and the report lists every create and
  every changed field (`before → after`).
- **All or nothing.** With any error in the file, nothing is written.
- **Re-running is safe.** Rows match existing data by natural key, case-insensitively. Running
  the same file twice reports every row as unchanged.
- **Empty cells never erase.** Only non-empty cells are compared and written.
- **Nothing is deleted.** A client missing from the file stays in IGS OS.
- **Nothing is guessed.** `03/04/2027` is an error until you say `--date-order dmy|mdy`.
  Amounts are whole US dollars (`US$ 2,280`, `2.280` and `2280.00` all read as 2280).
  Unknown values in a choice column are errors, with the allowed values in the message.
- **References resolve within the file too.** A trip can point at a client created in the
  same workbook, and payments and travelers can point at a trip created in it.
- **Audited.** Each apply writes an `import.apply` audit entry with the file name and counts.

## Payments

Payments are kept in the trip's pricing snapshot (`pricing.payments[payment_ref]`), and
`pricing.paid_usd` is recalculated as the sum of the rows with a `paid_at`. Once a trip's
payments are imported, that ledger is what Account 360 and the health rules read. An empty
`paid_at` never marks a payment as unpaid.

## Minors

Rosters include minors, so the importer keeps the minimum the operation needs:

- Minors keep a birth year only. Columns such as date of birth, passport, DNI or medical
  information are reported as "not stored" and ignored.
- Minors never get their own email or phone (the database enforces it). The importer drops
  them with a warning; contact goes to the coach, staff and parents.
- The AI mapper never sees cell values, only headers and each column's shape ("date-like",
  "email-like", "short text").

## AI column mapper

It's off unless two things hold:
- the deployment sets `IGS_IMPORT_LLM_MAPPING=true` (the API answers 409 otherwise);
- the request asks for it (`llm_mapping=true`, or `--llm-mapping` in the CLI).

It only handles headers the aliases don't match. Its suggestions are discarded when they:
- name a field that doesn't exist or is already mapped;
- refer to a header that isn't in the file;
- come below 0.6 confidence.

It maps column names only. Values are never produced by a model, and the report marks every
AI-mapped column with its confidence so ops can check it.
