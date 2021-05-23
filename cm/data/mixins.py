from typing import Any, TypeVar

T = TypeVar("T")


class CopyProhibited(Exception):
    pass


class ProhibitCopy:
    def __deepcopy__(self: T, memo: Any) -> T:
        raise CopyProhibited(
            f"{self.__class__.__name__} objects should never be copied!"
        )

    def __copy__(self: T, memo: Any) -> T:
        raise CopyProhibited(
            f"{self.__class__.__name__} objects should never be copied!"
        )
