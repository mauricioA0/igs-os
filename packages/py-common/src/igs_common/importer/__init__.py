"""Load an operator's existing data (spreadsheets) into IGS OS: validate, dry-run diff, upsert.

    report = await import_file(data, "clientes.xlsx", tenant_id=t, sessions=session_scope)

See docs/import/README.md for the sheets, columns and rules.
"""

from igs_common.importer.parse import ImportFileError, read_file
from igs_common.importer.report import ImportReport
from igs_common.importer.schema import SPECS, Entity
from igs_common.importer.service import import_file

__all__ = ["SPECS", "Entity", "ImportFileError", "ImportReport", "import_file", "read_file"]
