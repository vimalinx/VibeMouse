from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from vibemouse.core.backends import BackendStatus


DEFAULT_STATUS_TARGETS = ("default",)


class _BackendStatusReader(Protocol):
    def availability(self, *, output_target: str = "default") -> BackendStatus: ...


def collect_backend_statuses(
    transcriber: _BackendStatusReader,
    *,
    targets: Iterable[str] = DEFAULT_STATUS_TARGETS,
) -> dict[str, BackendStatus]:
    return {
        target: transcriber.availability(output_target=target)
        for target in targets
    }


__all__ = ["BackendStatus", "DEFAULT_STATUS_TARGETS", "collect_backend_statuses"]
