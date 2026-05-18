from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from vibemouse.platform.system_integration import show_system_notification


_LOG = logging.getLogger(__name__)
_DEEPL_TRANSLATE_URL = "https://api-free.deepl.com/v2/translate"
_MYMEMORY_TRANSLATE_URL = "https://api.mymemory.translated.net/get"
_OPUS_MT_MODEL_ID = "Helsinki-NLP/opus-mt-zh-en"
_OPUS_MT_CACHE_DIR_ENV = "VIBEMOUSE_OPUS_MT_CACHE_DIR"


def contains_chinese(text: str) -> bool:
    return any(
        "\u3400" <= char <= "\u4dbf"
        or "\u4e00" <= char <= "\u9fff"
        or "\uf900" <= char <= "\ufaff"
        for char in text
    )


def translate_text_to_english(
    text: str,
    *,
    timeout_s: float = 4.0,
    fetcher: Callable[[str, float], Any] | None = None,
    provider: str = "auto",
    deepl_auth_key: str | None = None,
    deepl_api_url: str | None = None,
    libretranslate_url: str | None = None,
    libretranslate_api_key: str | None = None,
    mymemory_email: str | None = None,
    mymemory_key: str | None = None,
) -> str | None:
    normalized = text.strip()
    if not normalized:
        return None

    if fetcher is not None:
        payload = fetcher(normalized, timeout_s)
        translated = _extract_google_style_translated_text(payload)
        return _clean_translation(normalized, translated)

    selected_provider = provider.strip().lower() or "auto"
    for current_provider in _translation_provider_order(
        selected_provider,
        libretranslate_url=libretranslate_url,
    ):
        try:
            translated = _translate_with_provider(
                current_provider,
                normalized,
                timeout_s,
                deepl_auth_key=deepl_auth_key,
                deepl_api_url=deepl_api_url,
                libretranslate_url=libretranslate_url,
                libretranslate_api_key=libretranslate_api_key,
                mymemory_email=mymemory_email,
                mymemory_key=mymemory_key,
            )
        except Exception as error:
            _LOG.warning(
                "Translation provider %s failed, trying next provider: %s",
                current_provider,
                error,
            )
            continue
        cleaned = _clean_translation(normalized, translated)
        if cleaned:
            return cleaned
    return None


def maybe_show_translation_toast(
    text: str,
    *,
    title: str = "English Translation",
    translation_timeout_s: float = 4.0,
    notification_timeout_s: float = 8.0,
    provider: str = "auto",
    deepl_auth_key: str | None = None,
    deepl_api_url: str | None = None,
    libretranslate_url: str | None = None,
    libretranslate_api_key: str | None = None,
    mymemory_email: str | None = None,
    mymemory_key: str | None = None,
) -> bool:
    normalized = text.strip()
    if not normalized or not contains_chinese(normalized):
        return False

    try:
        translated = translate_text_to_english(
            normalized,
            timeout_s=translation_timeout_s,
            provider=provider,
            deepl_auth_key=deepl_auth_key,
            deepl_api_url=deepl_api_url,
            libretranslate_url=libretranslate_url,
            libretranslate_api_key=libretranslate_api_key,
            mymemory_email=mymemory_email,
            mymemory_key=mymemory_key,
        )
    except Exception as error:
        _LOG.warning("Failed to translate transcript for toast: %s", error)
        return False

    if not translated:
        return False

    try:
        return show_system_notification(
            title,
            translated,
            timeout_s=notification_timeout_s,
        )
    except Exception as error:
        _LOG.warning("Failed to show translation toast: %s", error)
        return False


def _translation_provider_order(
    selected_provider: str,
    *,
    libretranslate_url: str | None,
) -> tuple[str, ...]:
    if selected_provider == "deepl":
        return ("deepl",)
    if selected_provider == "opus_mt":
        return ("opus_mt",)
    if selected_provider == "libretranslate":
        return ("libretranslate",)
    if selected_provider == "mymemory":
        return ("mymemory",)
    if (libretranslate_url or "").strip():
        return ("deepl", "libretranslate", "mymemory")
    return ("deepl", "mymemory")


def _translate_with_provider(
    provider: str,
    text: str,
    timeout_s: float,
    *,
    deepl_auth_key: str | None,
    deepl_api_url: str | None,
    libretranslate_url: str | None,
    libretranslate_api_key: str | None,
    mymemory_email: str | None,
    mymemory_key: str | None,
) -> str | None:
    if provider == "deepl":
        return _translate_with_deepl(
            text,
            timeout_s,
            auth_key=deepl_auth_key,
            api_url=deepl_api_url,
        )
    if provider == "opus_mt":
        return _translate_with_opus_mt(text)
    if provider == "libretranslate":
        return _translate_with_libretranslate(
            text,
            timeout_s,
            base_url=libretranslate_url,
            api_key=libretranslate_api_key,
        )
    if provider == "mymemory":
        return _translate_with_mymemory(
            text,
            timeout_s,
            email=mymemory_email,
            api_key=mymemory_key,
        )
    raise ValueError(f"Unsupported translation provider: {provider}")


def _translate_with_opus_mt(text: str) -> str | None:
    return _OPUS_MT_TRANSLATOR.translate(text)


def _translate_with_deepl(
    text: str,
    timeout_s: float,
    *,
    auth_key: str | None,
    api_url: str | None,
) -> str | None:
    normalized_auth_key = (auth_key or "").strip()
    if not normalized_auth_key:
        return None

    base_url = (api_url or "").strip() or _DEEPL_TRANSLATE_URL
    payload = _post_json(
        base_url,
        {
            "text": [text],
            "target_lang": "EN",
            "source_lang": "ZH",
        },
        timeout_s=timeout_s,
        headers={"Authorization": f"DeepL-Auth-Key {normalized_auth_key}"},
    )
    if not isinstance(payload, dict):
        return None
    translations = payload.get("translations")
    if not isinstance(translations, list) or not translations:
        return None
    first = translations[0]
    if not isinstance(first, dict):
        return None
    translated = first.get("text")
    if not isinstance(translated, str):
        return None
    return translated


class _OpusMTTranslator:
    def __init__(self, model_id: str) -> None:
        self._model_id = model_id
        self._tokenizer: Any | None = None
        self._model: Any | None = None
        self._cache_dir = _default_opus_mt_cache_dir()
        self._load_lock = threading.Lock()
        self._translate_lock = threading.Lock()

    def translate(self, text: str) -> str | None:
        normalized = text.strip()
        if not normalized:
            return None
        self._ensure_loaded()
        if self._tokenizer is None or self._model is None:
            return None

        with self._translate_lock:
            encoded = self._tokenizer(
                [normalized],
                return_tensors="pt",
                padding=True,
            )
            generated = self._model.generate(**encoded)
            decoded = self._tokenizer.batch_decode(
                generated,
                skip_special_tokens=True,
            )
        if not decoded:
            return None
        return str(decoded[0]).strip() or None

    def _ensure_loaded(self) -> None:
        if self._tokenizer is not None and self._model is not None:
            return

        with self._load_lock:
            if self._tokenizer is not None and self._model is not None:
                return

            try:
                transformers_module = __import__(
                    "transformers",
                    fromlist=["MarianMTModel", "MarianTokenizer"],
                )
            except Exception as error:
                raise RuntimeError(
                    "opus_mt provider requires the transformers package"
                ) from error

            tokenizer_ctor = getattr(transformers_module, "MarianTokenizer")
            model_ctor = getattr(transformers_module, "MarianMTModel")
            cache_dir = str(self._cache_dir)
            self._tokenizer = tokenizer_ctor.from_pretrained(
                self._model_id,
                cache_dir=cache_dir,
            )
            self._model = model_ctor.from_pretrained(
                self._model_id,
                cache_dir=cache_dir,
            )

def _default_opus_mt_cache_dir() -> Path:
    configured = os.getenv(_OPUS_MT_CACHE_DIR_ENV, "").strip()
    if configured:
        return Path(configured).expanduser()

    var_tmp = Path("/var/tmp")
    if var_tmp.exists() and os.access(var_tmp, os.W_OK):
        return var_tmp / "vibemouse-opus-mt"

    return Path(tempfile.gettempdir()) / "vibemouse-opus-mt"


_OPUS_MT_TRANSLATOR = _OpusMTTranslator(_OPUS_MT_MODEL_ID)


def _translate_with_libretranslate(
    text: str,
    timeout_s: float,
    *,
    base_url: str | None,
    api_key: str | None,
) -> str | None:
    raw_base_url = (base_url or "").strip()
    if not raw_base_url:
        return None

    payload: dict[str, object] = {
        "q": text,
        "source": "auto",
        "target": "en",
    }
    normalized_api_key = (api_key or "").strip()
    if normalized_api_key:
        payload["api_key"] = normalized_api_key

    normalized_base_url = raw_base_url.rstrip("/")
    response = _post_json(
        f"{normalized_base_url}/translate",
        payload,
        timeout_s=timeout_s,
    )
    if not isinstance(response, dict):
        return None
    translated = response.get("translatedText")
    if not isinstance(translated, str):
        return None
    return translated


def _translate_with_mymemory(
    text: str,
    timeout_s: float,
    *,
    email: str | None,
    api_key: str | None,
) -> str | None:
    query: dict[str, str] = {
        "q": text,
        "langpair": "zh-CN|en-US",
        "mt": "1",
    }
    normalized_email = (email or "").strip()
    normalized_api_key = (api_key or "").strip()
    if normalized_email:
        query["de"] = normalized_email
    if normalized_api_key:
        query["key"] = normalized_api_key

    params = urlencode(query)
    request = Request(
        f"{_MYMEMORY_TRANSLATE_URL}?{params}",
        headers={"User-Agent": "VibeMouse/0.2"},
    )
    with urlopen(request, timeout=timeout_s) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        return None
    response_data = payload.get("responseData")
    if not isinstance(response_data, dict):
        return None
    translated = response_data.get("translatedText")
    if not isinstance(translated, str):
        return None
    return translated


def _post_json(
    url: str,
    payload: dict[str, object],
    *,
    timeout_s: float,
    headers: dict[str, str] | None = None,
) -> Any:
    request_headers = {
        "Content-Type": "application/json",
        "User-Agent": "VibeMouse/0.2",
    }
    if headers:
        request_headers.update(headers)
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=request_headers,
        method="POST",
    )
    with urlopen(request, timeout=timeout_s) as response:
        return json.loads(response.read().decode("utf-8"))


def _clean_translation(source_text: str, translated: str | None) -> str | None:
    if translated is None:
        return None
    cleaned = translated.strip()
    if not cleaned or cleaned.casefold() == source_text.casefold():
        return None
    return cleaned


def _extract_google_style_translated_text(payload: Any) -> str | None:
    if not isinstance(payload, list) or not payload:
        return None

    segments = payload[0]
    if not isinstance(segments, list):
        return None

    parts: list[str] = []
    for segment in segments:
        if not isinstance(segment, list) or not segment:
            continue
        translated = segment[0]
        if isinstance(translated, str) and translated:
            parts.append(translated)

    if not parts:
        return None

    return "".join(parts)
