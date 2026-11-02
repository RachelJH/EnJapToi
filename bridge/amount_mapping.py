"""External operational KRW-string -> cheese configuration; no inferred exchange rate."""
import json
from pathlib import Path
import re


TIERS = frozenset((1000, 2000, 3000, 4000, 5000, 30000))
MAX_BYTES = 65536


class MappingError(ValueError):
    """Fixed diagnostic only: never include configuration content or file paths."""


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise MappingError('Invalid amount mapping')
        result[key] = value
    return result


def load(path):
    """Load one startup snapshot. Missing/invalid files never fall back to a map."""
    try:
        with Path(path).open('rb') as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise MappingError('Invalid amount mapping')
        value = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=_unique_keys)
        if not isinstance(value, dict):
            raise MappingError('Invalid amount mapping')
        for key, tier in value.items():
            if (not re.fullmatch(r'[1-9][0-9]{0,11}', key)
                    or type(tier) is not int or tier not in TIERS):
                raise MappingError('Invalid amount mapping')
        # {} deliberately maps no amounts. Missing entries never imply a ratio.
        return value
    except (OSError, ValueError, TypeError, RecursionError):
        raise MappingError('Invalid amount mapping') from None
