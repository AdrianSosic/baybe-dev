"""Functionality for multi-target objectives."""

from __future__ import annotations

import gc
import warnings
from typing import ClassVar

import pandas as pd
from attrs import define, field
from attrs.validators import deep_iterable, instance_of, min_len
from typing_extensions import override

from baybe.objectives.base import Objective
from baybe.objectives.validation import validate_target_names
from baybe.targets.numerical import NumericalTarget
from baybe.utils.basic import to_tuple
from baybe.utils.dataframe import transform_target_columns


@define(frozen=True, slots=False)
class ParetoObjective(Objective):
    """An objective handling multiple targets in a Pareto sense."""

    is_multi_output: ClassVar[bool] = True
    # See base class.

    _targets: tuple[NumericalTarget, ...] = field(
        converter=to_tuple,
        validator=[
            min_len(2),
            deep_iterable(member_validator=instance_of(NumericalTarget)),
            validate_target_names,
        ],
        alias="targets",
    )
    "The targets considered by the objective."

    @override
    @property
    def targets(self) -> tuple[NumericalTarget, ...]:
        return self._targets

    @override
    @property
    def n_outputs(self) -> int:
        return len(self._targets)

    @override
    def transform(
        self,
        df: pd.DataFrame | None = None,
        /,
        *,
        allow_missing: bool = False,
        allow_extra: bool | None = None,
        data: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        # >>>>>>>>>> Deprecation
        if not ((df is None) ^ (data is None)):
            raise ValueError(
                "Provide the dataframe to be transformed as first positional argument."
            )

        if data is not None:
            df = data
            warnings.warn(
                "Providing the dataframe via the `data` argument is deprecated and "
                "will be removed in a future version. Please pass your dataframe "
                "as positional argument instead.",
                DeprecationWarning,
            )

        # Mypy does not infer from the above that `df` must be a dataframe here
        assert isinstance(df, pd.DataFrame)

        if allow_extra is None:
            allow_extra = True
            if set(df.columns) - {p.name for p in self.targets}:
                warnings.warn(
                    "For backward compatibility, the new `allow_extra` flag is set "
                    "to `True` when left unspecified. However, this behavior will be "
                    "changed in a future version. If you want to invoke the old "
                    "behavior, please explicitly set `allow_extra=True`.",
                    DeprecationWarning,
                )
        # <<<<<<<<<< Deprecation

        return transform_target_columns(
            df, self.targets, allow_missing=allow_missing, allow_extra=allow_extra
        )


# Collect leftover original slotted classes processed by `attrs.define`
gc.collect()
