from __future__ import annotations

import time

from nexus_testing.delivery.models import ConfirmationRecord


def build_confirmation(
    *,
    status: str,
    note: str,
    confirmed_by: str,
) -> ConfirmationRecord:
    return ConfirmationRecord(
        status=status,
        note=note.strip(),
        confirmed_by=confirmed_by.strip(),
        confirmed_at=time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
    )

