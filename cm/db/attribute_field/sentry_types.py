from typing import Any, Dict


class JSONString(str):
    """Sentry type used to communicate that a string has already been encoded as json."""

    pass


class EncodedDict(Dict[str, Any]):
    """Sentry type used to communicate that a dict has already been encoded for use on the frontend."""

    pass
