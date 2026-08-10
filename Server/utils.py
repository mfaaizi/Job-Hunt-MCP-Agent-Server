"""
Shared parameter-coercion helpers for MCP tools.

Small local models sometimes send the literal string "null" (or other
string forms) instead of an actual JSON null/boolean for optional
arguments. Pydantic's strict bool validation rejects a string like "null"
outright — at the schema-validation layer, before the tool function body
even runs — so a plain `Optional[bool]` type hint isn't enough to catch
this the way normalize_optional_str catches it for string params.

The fix has two parts, both needed together:
  1. Loosen the parameter's type hint to accept bool | str | None, so
     Pydantic doesn't reject the call outright.
  2. Explicitly coerce the value with coerce_optional_bool() inside the
     function body.
"""
from typing import Optional, Union

_NULL_LIKE_STRINGS = {"null", "none", "nil", "undefined", ""}
_TRUE_STRINGS = {"true", "1", "yes", "y", "on"}
_FALSE_STRINGS = {"false", "0", "no", "n", "off"}


def coerce_optional_bool(value: Union[bool, str, None], default: Optional[bool] = None) -> Optional[bool]:
    """
    Coerces a bool-ish value that may have arrived as a string (including
    the placeholder string "null") into an actual Optional[bool].
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _NULL_LIKE_STRINGS:
            return default
        if normalized in _TRUE_STRINGS:
            return True
        if normalized in _FALSE_STRINGS:
            return False
        raise ValueError(f"Could not interpret '{value}' as a boolean (true/false).")
    raise ValueError(f"Could not interpret {value!r} as a boolean (true/false).")
