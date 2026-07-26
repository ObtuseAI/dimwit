"""Opaque character identifiers accepted by local character-generation paths."""

CHARACTER_IDS = (
    "01_vorlax",
    "02_ekris",
    "03_zythan",
    "04_qorin",
    "05_therak",
    "06_ullio",
    "07_kelous",
    "08_nexor",
)
CHARACTER_ID_SET = frozenset(CHARACTER_IDS)


def require_character_id(value: object) -> str:
    """Bind an untrusted value to one exact locally owned roster identifier."""
    if not isinstance(value, str) or value not in CHARACTER_ID_SET:
        raise ValueError(f"unknown character id: {value!r}")
    return value
