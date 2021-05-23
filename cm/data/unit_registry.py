"""Overwritten version of the pint unit registry with fixes to allow percentage signs."""

import pint


def _fix_percent(x: str) -> str:
    return x.replace("%%", " per_mille ").replace("%", " percent ")


class UnitRegistry(pint.UnitRegistry):  # type: ignore
    def __call__(self, input_string, **kwargs):  # type: ignore
        """Hack around `pint#429 <https://github.com/hgrecco/pint/issues/429>`_
        to support % sign
        """
        return super().__call__(_fix_percent(input_string), **kwargs)

    def parse_expression(self, input_string, *args, **kwargs):  # type: ignore
        """Allow % sign"""
        return super().parse_expression(_fix_percent(input_string), *args, **kwargs)

    def parse_units(self, input_string, *args, **kwargs):  # type: ignore
        """Allow % sign"""
        return super().parse_units(_fix_percent(input_string), *args, **kwargs)
