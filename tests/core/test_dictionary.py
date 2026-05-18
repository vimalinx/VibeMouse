from __future__ import annotations

import unittest

from vibemouse.config import DictionaryEntry
from vibemouse.core.dictionary import DictionaryService


def _build_entries() -> tuple[DictionaryEntry, ...]:
    return (
        DictionaryEntry(
            term="Codex",
            phrases=("codex", "code x"),
            weight=8,
            scope="both",
            enabled=True,
        ),
        DictionaryEntry(
            term="Terminal",
            phrases=("terminal",),
            weight=6,
            scope="default",
            enabled=True,
        ),
        DictionaryEntry(
            term="Claude Code",
            phrases=("claude code", "claude"),
            weight=7,
            scope="default",
            enabled=True,
        ),
        DictionaryEntry(
            term="Disabled Term",
            phrases=("disabled term",),
            weight=9,
            scope="both",
            enabled=False,
        ),
    )


class DictionaryServiceTests(unittest.TestCase):
    def test_hotword_phrases_filter_entries_by_scope_and_enabled_state(self) -> None:
        service = DictionaryService(_build_entries())

        self.assertEqual(
            service.hotword_phrases(scope="default"),
            [
                ("codex", 8),
                ("code x", 8),
                ("terminal", 6),
                ("claude code", 7),
                ("claude", 7),
            ],
        )

    def test_normalize_rewrites_matching_phrase_to_canonical_term(self) -> None:
        service = DictionaryService(_build_entries())

        self.assertEqual(
            service.normalize("please ask code x to review", scope="default"),
            "please ask Codex to review",
        )

    def test_removed_openclaw_scope_is_rejected(self) -> None:
        service = DictionaryService(_build_entries())

        with self.assertRaisesRegex(ValueError, "scope must be one of"):
            service.normalize("send it to terminal", scope="openclaw")

    def test_normalize_prefers_longest_phrase_without_double_substitution(self) -> None:
        service = DictionaryService(_build_entries())

        self.assertEqual(
            service.normalize("claude code is ready", scope="default"),
            "Claude Code is ready",
        )
