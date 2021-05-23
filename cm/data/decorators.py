from typing import Any, Callable

from cm.exceptions import ValidationError


def validator(f: Callable[[Any], bool], error_message: str) -> Callable[[Any], bool]:
    def _wrapper(value: Any) -> bool:
        try:
            # If the validating function returns False, raise the given error message
            success = f(value)
            if not success:
                raise ValidationError(error_message.format(v=value))
        except ValidationError:
            # If the validator raises a ValidationError, just re-rasise it
            raise
        except Exception as e:
            # Reraise any other error as a validation error
            raise ValidationError(str(e))
        return success

    return _wrapper
