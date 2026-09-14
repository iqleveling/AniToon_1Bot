from __future__ import annotations

from dataclasses import dataclass

from helper.database import db

DEFAULT_AUDIO_PREFIX = "[AniToon]"
DEFAULT_AUDIO_LANGUAGE = "Japanese"
DEFAULT_SUBTITLE_PREFIX = "[AniToon]"
DEFAULT_SUBTITLE_LANGUAGE = "English"


@dataclass(frozen=True)
class MetadataSettings:
    audio_prefix: str = DEFAULT_AUDIO_PREFIX
    audio_language: str = DEFAULT_AUDIO_LANGUAGE
    subtitle_prefix: str = DEFAULT_SUBTITLE_PREFIX
    subtitle_language: str = DEFAULT_SUBTITLE_LANGUAGE

    @property
    def audio_name(self) -> str:
        return _join(self.audio_prefix, self.audio_language)

    @property
    def subtitle_name(self) -> str:
        return _join(self.subtitle_prefix, self.subtitle_language)


def _clean(value: object, fallback: str) -> str:
    value = str(value or "").strip()
    return value if value else fallback


def _join(prefix: str, language: str) -> str:
    prefix = str(prefix or "").strip()
    language = str(language or "").strip()
    return f"{prefix} {language}".strip()


def _legacy_parts(value: object, default_prefix: str, default_language: str) -> tuple[str, str]:
    text = str(value or "").strip()
    if not text or text == "AniToon Official":
        return default_prefix, default_language
    if text.startswith("[") and "]" in text:
        end = text.find("]") + 1
        return text[:end].strip(), text[end:].strip() or default_language
    return "", text


async def get_metadata(user_id: int) -> MetadataSettings:
    await db.add_user(user_id)
    user = await db.get_user_data(user_id) or {}
    ap, al = _legacy_parts(user.get("audio_name"), DEFAULT_AUDIO_PREFIX, DEFAULT_AUDIO_LANGUAGE)
    sp, sl = _legacy_parts(user.get("sub_name"), DEFAULT_SUBTITLE_PREFIX, DEFAULT_SUBTITLE_LANGUAGE)
    return MetadataSettings(
        audio_prefix=_clean(user.get("audio_prefix"), ap),
        audio_language=_clean(user.get("audio_language"), al),
        subtitle_prefix=_clean(user.get("subtitle_prefix"), sp),
        subtitle_language=_clean(user.get("subtitle_language"), sl),
    )


async def save_metadata(user_id: int, settings: MetadataSettings) -> None:
    await db.set_metadata_parts(
        user_id,
        audio_prefix=settings.audio_prefix,
        audio_language=settings.audio_language,
        subtitle_prefix=settings.subtitle_prefix,
        subtitle_language=settings.subtitle_language,
    )


async def update_metadata_part(user_id: int, kind: str, field: str, value: str) -> MetadataSettings:
    current = await get_metadata(user_id)
    values = {
        "audio_prefix": current.audio_prefix,
        "audio_language": current.audio_language,
        "subtitle_prefix": current.subtitle_prefix,
        "subtitle_language": current.subtitle_language,
    }
    key = f"{kind}_{field}"
    if key not in values:
        raise ValueError("Invalid metadata field")
    values[key] = str(value).strip()
    updated = MetadataSettings(**values)
    await save_metadata(user_id, updated)
    return updated


async def reset_metadata(user_id: int) -> MetadataSettings:
    settings = MetadataSettings()
    await save_metadata(user_id, settings)
    return settings
