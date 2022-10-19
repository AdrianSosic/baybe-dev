"""
Functionality for parameter constraints.
"""
from __future__ import annotations

import logging
import operator as ops
from abc import ABC, abstractmethod
from functools import reduce
from inspect import isabstract

from typing import ClassVar, Dict, List, Literal, Type, Union

import pandas as pd
from funcy import rpartial
from pydantic import BaseModel, conlist, Extra, validator

from .utils import check_if_in

log = logging.getLogger(__name__)


class Condition(ABC, BaseModel, extra=Extra.forbid, arbitrary_types_allowed=True):
    """
    Abstract base class for all conditions. Conditions are part of constraints,
    a constraint can have multiple conditions.
    """

    # class variables
    type: ClassVar[str]
    parameter: str
    SUBCLASSES: ClassVar[Dict[str, Type[Constraint]]] = {}

    @classmethod
    def create(cls, config: dict) -> Condition:
        """Creates a new object matching the given specifications."""
        config = config.copy()
        condition_type = config.pop("type")
        check_if_in(condition_type, list(Condition.SUBCLASSES.keys()))
        return cls.SUBCLASSES[condition_type](**config)

    @classmethod
    def __init_subclass__(cls, **kwargs):
        """Registers new subclasses dynamically."""
        super().__init_subclass__(**kwargs)
        if not isabstract(cls):
            cls.SUBCLASSES[cls.type] = cls

    @abstractmethod
    def evaluate(self, data: pd.Series) -> pd.Series:
        """
        Evaluates the condition on a given data series.

        Parameters
        ----------
        data : pd.Series
            A series containing parameter values.

        Returns
        -------
        pd.Series
            A boolean series indicating which elements satisfy the condition.
        """


class ThresholdCondition(Condition):
    """
    Class for modelling threshold-based conditions.
    """

    # class variables
    type = "THRESHOLD"
    threshold: float
    operator: Literal["<", "<=", "=", "==", "!=", ">", ">="]

    # define the valid operators
    _operator_dict = {
        "<": ops.lt,
        "<=": ops.le,
        "=": ops.eq,
        "==": ops.eq,
        "!=": ops.ne,
        ">": ops.gt,
        ">=": ops.ge,
    }

    def evaluate(self, data: pd.Series) -> pd.Series:
        """See base class."""
        return data.apply(rpartial(self._operator_dict[self.operator], self.threshold))


class SubSelectionCondition(Condition):
    """
    Class for defining valid parameter entries.
    """

    # class variables
    type = "SUBSELECTION"
    selection: list

    # TODO: Set up a validation that checks the sublist only contains valid entries.
    #  As this depends on the `Parameter`, it might be better to do it in `Constraint`.

    def evaluate(self, data: pd.Series) -> pd.Series:
        """See base class."""
        return data.isin(self.selection)


class Constraint(ABC, BaseModel, extra=Extra.forbid, arbitrary_types_allowed=True):
    """
    Abstract base class for all constraints. Constraints use conditions and chain them
    together to filter unwanted entries from the searchspace.
    """

    # class variables
    type: ClassVar[str]
    SUBCLASSES: ClassVar[Dict[str, Constraint]] = {}

    # TODO: it might turn out these are not needed at a later development stage
    eval_during_creation: ClassVar[bool]
    eval_during_modeling: ClassVar[bool]

    @classmethod
    def create(cls, config: dict) -> Constraint:
        """Creates a new object matching the given specifications."""
        config = config.copy()
        constraint_type = config.pop("type")
        check_if_in(constraint_type, list(Constraint.SUBCLASSES.keys()))
        return cls.SUBCLASSES[constraint_type](**config)

    @classmethod
    def __init_subclass__(cls, **kwargs):
        """Registers new subclasses dynamically."""
        super().__init_subclass__(**kwargs)
        if not isabstract(cls):
            cls.SUBCLASSES[cls.type] = cls

    @abstractmethod
    def evaluate(self, data: pd.DataFrame) -> pd.Index:
        """
        Evaluates the constraint on a given set of parameter combinations.

        Parameters
        ----------
        data : pd.DataFrame
            A dataframe where each row represents a particular parameter combination.

        Returns
        -------
        pd.Index
            The dataframe indices of rows where the constraint is violated.
        """


class ExcludeConstraint(Constraint):
    """
    Class for modelling exclusion constraints.
    """

    # class variables
    type = "EXCLUDE"
    eval_during_creation = True
    eval_during_modeling = False
    conditions: conlist(Union[dict, Condition], min_items=1)
    combiner: Literal["AND", "OR", "XOR"] = "AND"

    @validator("conditions")
    def validate_conditions(cls, conditions):
        """Validates the conditions."""
        return [
            c if isinstance(c, Condition) else Condition.create(c) for c in conditions
        ]

    _combiner_dict = {
        "AND": ops.and_,
        "OR": ops.or_,
        "XOR": ops.xor,
    }

    # TODO: validate that condition types match with the allowed parameter types
    # TODO: NUM_CONTINUOUS should also work for "THRESHOLD" but that requires
    #  additional logic
    _conditions_allowed_parameters = {
        "THRESHOLD": ["NUM_DISCRETE"],
        "SUBSELECTION": ["CAT", "NUM_DISCRETE", "SUBSTANCE", "CUSTOM"],
    }

    def evaluate(self, data: pd.DataFrame) -> pd.Index:
        """See base class."""
        satisfied = [cond.evaluate(data[cond.parameter]) for cond in self.conditions]
        res = reduce(self._combiner_dict[self.combiner], satisfied)
        return data.index[res]


class ParametersListConstraint(Constraint, ABC):
    """
    Intermediate base class for constraints that can only be defined on joint
    parameter spaces.
    """

    # class variables
    parameters: List[str]

    @validator("parameters")
    def validate_params(cls, parameters):
        """Validates the parameter list."""
        if len(parameters) != len(set(parameters)):
            raise AssertionError(
                f"The given 'parameter' list must have unique values "
                f"but was: {parameters}."
            )
        return parameters


class SumTargetConstraint(ParametersListConstraint):
    """
    Class for modelling sum constraints.
    """

    # class variables
    type = "SUM_TARGET"
    eval_during_creation = True
    eval_during_modeling = False
    target_value: float
    tolerance: float = 0.0

    def evaluate(self, data: pd.DataFrame) -> pd.Index:
        """See base class."""
        mask_bad = (
            data[self.parameters].sum(axis=1) - self.target_value
        ).abs() > self.tolerance

        return data.index[mask_bad]


class ProdTargetConstraint(ParametersListConstraint):
    """
    Class for modelling product constraints.
    """

    # class variables
    type = "PROD_TARGET"
    eval_during_creation = True
    eval_during_modeling = False
    target_value: float
    tolerance: float = 0.0

    def evaluate(self, data: pd.DataFrame) -> pd.Index:
        """See base class."""
        mask_bad = (
            data[self.parameters].prod(axis=1) - self.target_value
        ).abs() > self.tolerance

        return data.index[mask_bad]


class NoLabelDuplicatesConstraint(ParametersListConstraint):
    """
    Constraint class for excluding entries where the occurring labels are not unique.
    This can be useful to remove entries that arise from e.g. a permutation invariance.
    Examples:
        - A,B,C,D would remain
        - A,A,B,C would be removed
        - A,A,B,B would be removed
        - A,A,B,A would be removed
        - A,C,A,C would be removed
        - A,C,B,C would be removed
    """

    # class variables
    type = "NO_LABEL_DUPLICATES"
    eval_during_creation = True
    eval_during_modeling = False

    def evaluate(self, data: pd.DataFrame) -> pd.Index:
        """See base class."""
        mask_bad = data[self.parameters].nunique(axis=1) != len(self.parameters)

        return data.index[mask_bad]


class LinkedParametersConstraint(ParametersListConstraint):
    """
    Constraint class for linking the values of parameters. This constraint type
    effectively allows generating parameter sets that relate to the same underlying
    quantity, e.g. two parameters that represent the same molecule using different
    encodings. Linking the parameters removes all entries from the searchspace where
    the parameter values differ.
    """

    # class variables
    type = "LINKED_PARAMETERS"
    eval_during_creation = True
    eval_during_modeling = False

    def evaluate(self, data: pd.DataFrame) -> pd.Index:
        """See base class."""
        mask_bad = data[self.parameters].nunique(axis=1) != 1

        return data.index[mask_bad]


class PermutationInvarianceConstraint(ParametersListConstraint):
    """
    Constraint class for declaring that a set of parameters are permutation invariant,
    that is, (val_from_param1, val_from_param2) is equivalent to
    (val_from_param2, val_from_param1).

    Note: This constraint cannot be evaluated during creation.
    """

    # class variables
    type = "PERMUTATION_INVARIANCE"
    # TODO update usage in different evaluation stages once that is implemented in
    #  strategy and surrogate
    eval_during_creation = True
    eval_during_modeling = False

    def evaluate(self, data: pd.DataFrame) -> pd.Index:
        """See base class."""

        # Merge a permutation invariant representation of all affected parameters with
        # the other parameters and indicate duplicates
        other_params = data.columns.drop(self.parameters).tolist()
        df_eval = pd.concat(
            [
                data[other_params].copy(),
                data[self.parameters].apply(frozenset, axis=1),
            ],
            axis=1,
        )
        mask_bad = df_eval.duplicated(keep="first")

        return data.index[mask_bad]
