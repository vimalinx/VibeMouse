from __future__ import annotations

import re
from collections.abc import Iterable

from vibemouse.config import DictionaryEntry


_SCOPE_CHOICES = {"default", "both"}


class DictionaryService:
    def __init__(self, entries: Iterable[DictionaryEntry]) -> None:
        self._entries = tuple(entries)

    def hotword_phrases(self, scope: str) -> list[tuple[str, int]]:
        phrases: list[tuple[str, int]] = []
        seen: set[str] = set()
        for entry in self._entries_for_scope(scope):
            for phrase in entry.phrases:
                key = phrase.casefold()
                if key in seen:
                    continue
                seen.add(key)
                phrases.append((phrase, entry.weight))
        return phrases

    def normalize(self, text: str, *, scope: str) -> str:
        rules = self._normalization_rules(scope)
        if not rules:
            return text

        pattern = re.compile(
            "|".join(
                f"(?P<rule_{index}>{_phrase_pattern(phrase)})"
                for index, (phrase, _) in enumerate(rules)
            ),
            re.IGNORECASE,
        )

        def replace(match: re.Match[str]) -> str:
            if match.lastgroup is None:
                return match.group(0)
            index = int(match.lastgroup.split("_", 1)[1])
            return rules[index][1]

        return pattern.sub(replace, text)

    def _entries_for_scope(self, scope: str) -> tuple[DictionaryEntry, ...]:
        normalized_scope = _normalize_scope(scope)
        return tuple(
            entry
            for entry in self._entries
            if entry.enabled and _scope_matches(entry.scope, normalized_scope)
        )

    def _normalization_rules(self, scope: str) -> list[tuple[str, str]]:
        rules: list[tuple[str, str]] = []
        for entry in self._entries_for_scope(scope):
            for phrase in entry.phrases:
                rules.append((phrase, entry.term))

        return sorted(
            rules,
            key=lambda item: (-len(item[0]), item[0].casefold(), item[1].casefold()),
        )


def _normalize_scope(scope: str) -> str:
    normalized = scope.strip().lower()
    if normalized not in _SCOPE_CHOICES:
        options = ", ".join(sorted(_SCOPE_CHOICES))
        raise ValueError(f"scope must be one of: {options}; got {scope!r}")
    return normalized


def _scope_matches(entry_scope: str, requested_scope: str) -> bool:
    if requested_scope == "both":
        return True
    return entry_scope == "both" or entry_scope == requested_scope


def _phrase_pattern(phrase: str) -> str:
    escaped = re.escape(phrase)
    if _needs_leading_boundary(phrase):
        escaped = rf"(?<!\w){escaped}"
    if _needs_trailing_boundary(phrase):
        escaped = rf"{escaped}(?!\w)"
    return escaped


def _needs_leading_boundary(phrase: str) -> bool:
    return bool(phrase) and _is_ascii_word_char(phrase[0])


def _needs_trailing_boundary(phrase: str) -> bool:
    return bool(phrase) and _is_ascii_word_char(phrase[-1])


def _is_ascii_word_char(char: str) -> bool:
    return char.isascii() and (char.isalnum() or char == "_")
