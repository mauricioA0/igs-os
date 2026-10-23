"""Repo-wide pytest setup.

Seeded demo dates are anchored to "today" (igs_common.seed.anchor). Tests pin the anchor to the
day the fixtures were written so their literal expectations (dates, health reasons) hold.
"""

import os

os.environ.setdefault("DEMO_ANCHOR", "2026-10-22")
