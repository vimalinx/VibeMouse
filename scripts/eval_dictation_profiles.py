from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, replace
from pathlib import Path
import sys
from typing import Any, Protocol

if __package__ in {None, ""}:
    PROJECT_ROOT = Path(__file__).resolve().parents[1]
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

from vibemouse.config import AppConfig, DictionaryEntry, load_config
from vibemouse.core.dictionary import DictionaryService
from vibemouse.core.transcriber import SenseVoiceTranscriber


PROFILE_CHOICES = ("fast", "enhanced")
TARGET_CHOICES = ("default",)


@dataclass(frozen=True)
class EvalRecord:
    audio_path: Path
    output_target: str
    reference_text: str
    expected_terms: tuple[str, ...] = ()
    note: str | None = None


class _EvalTranscriber(Protocol):
    def availability(self, *, output_target: str = "default") -> Any: ...

    def transcribe(
        self,
        audio_path: Path,
        *,
        output_target: str = "default",
        hotwords: list[tuple[str, int]] | None = None,
    ) -> str: ...


def load_eval_records(path: Path) -> list[EvalRecord]:
    records: list[EvalRecord] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError(
                    f"Expected JSON object on line {line_number}, got {type(payload).__name__}"
                )
            output_target = _normalize_choice(
                _require_string(payload, "output_target", line_number),
                TARGET_CHOICES,
                field_name="output_target",
            )
            expected_terms = _coerce_string_list(
                payload.get("expected_terms", []),
                field_name="expected_terms",
                line_number=line_number,
            )
            note = payload.get("note")
            if note is not None and not isinstance(note, str):
                raise ValueError(
                    f"Field 'note' on line {line_number} must be a string when provided"
                )
            records.append(
                EvalRecord(
                    audio_path=Path(_require_string(payload, "audio_path", line_number)),
                    output_target=output_target,
                    reference_text=_require_string(
                        payload,
                        "reference_text",
                        line_number,
                    ),
                    expected_terms=tuple(expected_terms),
                    note=note,
                )
            )
    return records


def evaluate_dataset(
    dataset_path: Path,
    config: AppConfig,
    *,
    profiles: tuple[str, ...] = PROFILE_CHOICES,
    transcriber_factory=SenseVoiceTranscriber,
) -> dict[str, object]:
    records = load_eval_records(dataset_path)
    normalized_profiles = tuple(
        _normalize_choice(profile, PROFILE_CHOICES, field_name="profile")
        for profile in profiles
    )
    dictionary_service = DictionaryService(config.dictionary)
    transcribers: dict[tuple[str, str], _EvalTranscriber] = {}
    summaries = {profile: _new_summary(profile) for profile in normalized_profiles}
    record_results: list[dict[str, object]] = []

    for record in records:
        hotwords = dictionary_service.hotword_phrases(record.output_target)
        expected_terms = _resolve_expected_terms(record, config.dictionary)
        for profile in normalized_profiles:
            transcriber = _transcriber_for(
                transcribers,
                config,
                output_target=record.output_target,
                profile=profile,
                transcriber_factory=transcriber_factory,
            )
            status = transcriber.availability(output_target=record.output_target)
            summary = summaries[profile]
            summary["backend_id"] = getattr(status, "backend_id", "unknown")
            summary["attempted_records"] += 1

            if not bool(getattr(status, "available", False)):
                summary["unavailable_records"] += 1
                reason = getattr(status, "reason", None) or "backend unavailable"
                _append_unique(summary["unavailable_reasons"], reason)
                record_results.append(
                    {
                        "profile": profile,
                        "output_target": record.output_target,
                        "audio_path": str(record.audio_path),
                        "backend_id": summary["backend_id"],
                        "available": False,
                        "reason": reason,
                        "reference_text": record.reference_text,
                        "expected_terms": list(expected_terms),
                    }
                )
                continue

            raw_text = transcriber.transcribe(
                record.audio_path,
                output_target=record.output_target,
                hotwords=hotwords,
            )
            normalized_text = dictionary_service.normalize(
                raw_text,
                scope=record.output_target,
            )
            matched_terms = [
                term for term in expected_terms if term.casefold() in normalized_text.casefold()
            ]
            exact_match = normalized_text == record.reference_text

            summary["transcribed_records"] += 1
            summary["exact_matches"] += int(exact_match)
            summary["term_hits"] += len(matched_terms)
            summary["term_total"] += len(expected_terms)

            record_results.append(
                {
                    "profile": profile,
                    "output_target": record.output_target,
                    "audio_path": str(record.audio_path),
                    "backend_id": summary["backend_id"],
                    "available": True,
                    "reference_text": record.reference_text,
                    "normalized_text": normalized_text,
                    "exact_match": exact_match,
                    "expected_terms": list(expected_terms),
                    "matched_terms": matched_terms,
                }
            )

    for profile, summary in summaries.items():
        transcribed_records = int(summary["transcribed_records"])
        term_total = int(summary["term_total"])
        summary["available"] = int(summary["unavailable_records"]) == 0
        summary["exact_match_rate"] = (
            summary["exact_matches"] / transcribed_records if transcribed_records else 0.0
        )
        summary["term_hit_rate"] = (
            summary["term_hits"] / term_total if term_total else None
        )
        summary["profile"] = profile

    return {
        "dataset_path": str(dataset_path),
        "dataset_size": len(records),
        "profiles": summaries,
        "records": record_results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate VibeMouse dictation profiles against a JSONL fixture."
    )
    parser.add_argument(
        "--dataset",
        required=True,
        type=Path,
        help="Path to a JSONL fixture with audio_path/output_target/reference_text rows.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Optional config path. Defaults to the runtime config resolution path.",
    )
    parser.add_argument(
        "--profile",
        action="append",
        choices=PROFILE_CHOICES,
        dest="profiles",
        help="Profile(s) to evaluate. Defaults to both fast and enhanced.",
    )
    args = parser.parse_args(argv)

    config = load_config(args.config)
    report = evaluate_dataset(
        args.dataset,
        config,
        profiles=tuple(args.profiles or PROFILE_CHOICES),
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def _new_summary(profile: str) -> dict[str, object]:
    return {
        "profile": profile,
        "backend_id": None,
        "attempted_records": 0,
        "transcribed_records": 0,
        "unavailable_records": 0,
        "unavailable_reasons": [],
        "exact_matches": 0,
        "exact_match_rate": 0.0,
        "term_hits": 0,
        "term_total": 0,
        "term_hit_rate": None,
        "available": False,
    }


def _transcriber_for(
    cache: dict[tuple[str, str], _EvalTranscriber],
    config: AppConfig,
    *,
    output_target: str,
    profile: str,
    transcriber_factory,
) -> _EvalTranscriber:
    cache_key = (output_target, profile)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    profile_map = dict(config.profiles)
    profile_map[output_target] = profile
    variant_config = replace(config, profiles=profile_map)
    transcriber = transcriber_factory(variant_config)
    cache[cache_key] = transcriber
    return transcriber


def _resolve_expected_terms(
    record: EvalRecord,
    entries: tuple[DictionaryEntry, ...],
) -> list[str]:
    if record.expected_terms:
        return list(record.expected_terms)

    reference_text = record.reference_text.casefold()
    resolved: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        if not entry.enabled or not _scope_matches(entry.scope, record.output_target):
            continue
        key = entry.term.casefold()
        if key in seen or key not in reference_text:
            continue
        seen.add(key)
        resolved.append(entry.term)
    return resolved


def _scope_matches(entry_scope: str, output_target: str) -> bool:
    return entry_scope == "both" or entry_scope == output_target


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _require_string(
    payload: dict[str, object],
    field_name: str,
    line_number: int,
) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"Field '{field_name}' on line {line_number} must be a non-empty string"
        )
    return value.strip()


def _coerce_string_list(
    value: object,
    *,
    field_name: str,
    line_number: int,
) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"Field '{field_name}' on line {line_number} must be a list")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(
                f"Field '{field_name}' on line {line_number} must contain non-empty strings"
            )
        items.append(item.strip())
    return items


def _normalize_choice(value: str, choices: tuple[str, ...], *, field_name: str) -> str:
    normalized = value.strip().lower()
    if normalized not in choices:
        options = ", ".join(choices)
        raise ValueError(f"{field_name} must be one of: {options}; got {value!r}")
    return normalized


if __name__ == "__main__":
    raise SystemExit(main())
