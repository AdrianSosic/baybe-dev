"""
PyTest configuration
"""
import os

from typing import List

import numpy as np
import pandas as pd
import pytest

from baybe.constraints import (
    CustomConstraint,
    DependenciesConstraint,
    ExcludeConstraint,
    NoLabelDuplicatesConstraint,
    PermutationInvarianceConstraint,
    ProductConstraint,
    SubSelectionCondition,
    SumConstraint,
    ThresholdCondition,
)
from baybe.core import BayBE
from baybe.parameters import (
    Categorical,
    Custom,
    GenericSubstance,
    NumericContinuous,
    NumericDiscrete,
    SUBSTANCE_ENCODINGS,
)
from baybe.searchspace import SearchSpace
from baybe.strategies.bayesian import SequentialGreedyRecommender
from baybe.strategies.sampling import RandomRecommender
from baybe.strategies.strategy import Strategy
from baybe.targets import NumericalTarget, Objective

# All fixture functions have prefix 'fixture_' and explicitly declared name so they
# can be reused by other fixtures, see
# https://docs.pytest.org/en/stable/reference/reference.html#pytest-fixture


@pytest.fixture(scope="session", autouse=True)
def disable_telemetry():
    """
    Disables telemetry during pytesting via fixture
    """
    # Remember the original value of the environment variables
    telemetry_enabled_before = os.environ.get("BAYBE_TELEMETRY_ENABLED")
    telemetry_userhash_before = os.environ.get("BAYBE_DEBUG_FAKE_USERHASH")
    telemetry_hosthash_before = os.environ.get("BAYBE_DEBUG_FAKE_HOSTHASH")

    # Set the environment variable to a certain value for the duration of the tests
    os.environ["BAYBE_TELEMETRY_ENABLED"] = "false"
    os.environ["BAYBE_DEBUG_FAKE_USERHASH"] = "PYTEST"
    os.environ["BAYBE_DEBUG_FAKE_HOSTHASH"] = "PYTEST"

    # Yield control to the tests
    yield

    # Restore the original value of the environment variables
    if telemetry_enabled_before is not None:
        os.environ["BAYBE_TELEMETRY_ENABLED"] = telemetry_enabled_before
    else:
        os.environ.pop("BAYBE_TELEMETRY_ENABLED")

    if telemetry_userhash_before is not None:
        os.environ["BAYBE_DEBUG_FAKE_USERHASH"] = telemetry_userhash_before
    else:
        os.environ.pop("BAYBE_DEBUG_FAKE_USERHASH")

    if telemetry_hosthash_before is not None:
        os.environ["BAYBE_DEBUG_FAKE_HOSTHASH"] = telemetry_hosthash_before
    else:
        os.environ.pop("BAYBE_DEBUG_FAKE_HOSTHASH")


# Add option to only run fast tests
def pytest_addoption(parser):
    """
    Changes pytest parser.
    """
    parser.addoption("--fast", action="store_true", help="fast: Runs reduced tests")


def pytest_configure(config):
    """
    Changes pytest marker configuration.
    """
    config.addinivalue_line("markers", "slow: mark test as slow to run")


def pytest_collection_modifyitems(config, items):
    """
    Marks slow tests as skip of flag is set.
    """
    if not config.getoption("--fast"):
        return

    skip_slow = pytest.mark.skip(reason="skip with --fast")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)


@pytest.fixture(params=[2], name="n_iterations", ids=["i2"])
def fixture_n_iterations(request):
    """
    Number of iterations ran in tests.
    """
    return request.param


@pytest.fixture(
    params=[pytest.param(1, marks=pytest.mark.slow), 3],
    name="batch_quantity",
    ids=["b1", "b3"],
)
def fixture_batch_quantity(request):
    """
    Number of recommendations requested per iteration. Testing 1 as edge case and 3
    as a case for >1.
    """
    return request.param


@pytest.fixture(
    params=[5, pytest.param(8, marks=pytest.mark.slow)],
    name="n_grid_points",
    ids=["grid5", "grid8"],
)
def fixture_n_grid_points(request):
    """
    Number of grid points used in e.g. the mixture tests. Test an even number
    (5 grid points will cause 4 sections) and a number that causes division into
    numbers that have no perfect floating point representation
    (8 grid points will cause 7 sections).
    """
    return request.param


@pytest.fixture(name="good_reference_values")
def fixture_good_reference_values():
    """
    Define some good reference values which are used by the utility function to
    generate fake good results. These only make sense for discrete parameters.
    """
    return {"Categorical_1": ["B"], "Categorical_2": ["OK"]}


@pytest.fixture(name="mock_substances")
def fixture_mock_substances():
    """
    A set of test substances.
    """
    substances = {
        "Water": "O",
        "THF": "C1CCOC1",
        "DMF": "CN(C)C=O",
        "Hexane": "CCCCCC",
    }

    return substances


@pytest.fixture(name="mock_categories")
def fixture_mock_categories():
    """
    A set of mock categories for categorical parameters.
    """
    return ["Type1", "Type2", "Type3"]


@pytest.fixture(name="parameters")
def fixture_parameters(
    parameter_names: List[str], mock_substances, mock_categories, n_grid_points
):
    """Provides example parameters via specified names."""
    valid_parameters = [
        Categorical(
            name="Categorical_1",
            values=["A", "B", "C"],
            encoding="OHE",
        ),
        Categorical(
            name="Categorical_2",
            values=["bad", "OK", "good"],
            encoding="OHE",
        ),
        Categorical(
            name="Switch_1",
            values=["on", "off"],
            encoding="OHE",
        ),
        Categorical(
            name="Switch_2",
            values=["left", "right"],
            encoding="OHE",
        ),
        Categorical(
            name="Frame_A",
            values=mock_categories,
        ),
        Categorical(
            name="Frame_B",
            values=mock_categories,
        ),
        Categorical(
            name="SomeSetting",
            values=["slow", "normal", "fast"],
            encoding="INT",
        ),
        NumericDiscrete(
            name="Num_disc_1",
            values=[1, 2, 7],
            tolerance=0.3,
        ),
        NumericDiscrete(
            name="Fraction_1",
            values=list(np.linspace(0, 100, n_grid_points)),
            tolerance=0.2,
        ),
        NumericDiscrete(
            name="Fraction_2",
            values=list(np.linspace(0, 100, n_grid_points)),
            tolerance=0.5,
        ),
        NumericDiscrete(
            name="Fraction_3",
            values=list(np.linspace(0, 100, n_grid_points)),
            tolerance=0.5,
        ),
        NumericDiscrete(
            name="Temperature",
            values=list(np.linspace(100, 200, n_grid_points)),
        ),
        NumericDiscrete(
            name="Pressure",
            values=list(np.linspace(0, 6, n_grid_points)),
        ),
        NumericContinuous(
            name="Conti_finite1",
            bounds=(0, 1),
        ),
        NumericContinuous(
            name="Conti_finite2",
            bounds=(-1, 0),
        ),
        NumericContinuous(
            name="Conti_infinite1",
            bounds=(None, 1),
        ),
        NumericContinuous(
            name="Conti_infinite2",
            bounds=(0, None),
        ),
        NumericContinuous(
            name="Conti_infinite3",
            bounds=(0, np.inf),
        ),
        NumericContinuous(
            name="Conti_infinite4",
            bounds=(-np.inf, 1),
        ),
        NumericContinuous(
            name="Conti_infinite5",
            bounds=(None, None),
        ),
        Custom(
            name="Custom_1",
            data=pd.DataFrame(
                {
                    "D1": [1.1, 1.4, 1.7],
                    "D2": [11, 23, 55],
                    "D3": [-4, -13, 4],
                },
                index=["mol1", "mol2", "mol3"],
            ),
        ),
        Custom(
            name="Custom_2",
            data=pd.DataFrame(
                {
                    "desc1": [1.1, 1.4, 1.7],
                    "desc2": [55, 23, 3],
                    "desc3": [4, 5, 6],
                },
                index=["A", "B", "C"],
            ),
        ),
        GenericSubstance(
            name="Solvent_1",
            data=mock_substances,
        ),
        GenericSubstance(
            name="Solvent_2",
            data=mock_substances,
            encoding="MORDRED",
        ),
        GenericSubstance(
            name="Solvent_3",
            data=mock_substances,
            encoding="MORDRED",
        ),
        *[
            GenericSubstance(
                name=f"Substance_1_{encoding}",
                data=mock_substances,
                encoding=encoding,
            )
            for encoding in SUBSTANCE_ENCODINGS
        ],
    ]
    return [p for p in valid_parameters if p.name in parameter_names]


@pytest.fixture(name="targets")
def fixture_targets(target_names: List[str]):
    """Provides example targets via specified names."""
    valid_targets = [
        NumericalTarget(
            name="Target_max",
            mode="MAX",
        ),
        NumericalTarget(
            name="Target_min",
            mode="MIN",
        ),
        NumericalTarget(
            name="Target_max_bounded",
            mode="MAX",
            bounds=(0, 100),
        ),
        NumericalTarget(
            name="Target_min_bounded",
            mode="MIN",
            bounds=(0, 100),
        ),
        NumericalTarget(
            name="Target_match_bell",
            mode="MATCH",
            bounds=(0, 100),
            bounds_transform_func="BELL",
        ),
        NumericalTarget(
            name="Target_match_triangular",
            mode="MATCH",
            bounds=(0, 100),
            bounds_transform_func="TRIANGULAR",
        ),
    ]
    return [t for t in valid_targets if t.name in target_names]


@pytest.fixture(name="constraints")
def fixture_constraints(constraint_names: List[str], mock_substances, n_grid_points):
    """Provides example constraints via specified names."""

    def custom_function(ser: pd.Series) -> bool:
        if ser.Solvent_1 == "water":
            if ser.Temperature > 120 and ser.Pressure > 5:
                return False
            if ser.Temperature > 180 and ser.Pressure > 3:
                return False
        if ser.Solvent_1 == "C3":
            if ser.Temperature < 150 and ser.Pressure > 3:
                return False
        return True

    valid_constraints = {
        "Constraint_1": DependenciesConstraint(
            parameters=["Switch_1", "Switch_2"],
            conditions=[
                SubSelectionCondition(selection=["on"]),
                SubSelectionCondition(selection=["right"]),
            ],
            affected_parameters=[
                ["Solvent_1", "Fraction_1"],
                ["Frame_A", "Frame_B"],
            ],
        ),
        "Constraint_2": DependenciesConstraint(
            parameters=["Switch_1"],
            conditions=[SubSelectionCondition(selection=["on"])],
            affected_parameters=[["Solvent_1", "Fraction_1"]],
        ),
        "Constraint_3": DependenciesConstraint(
            parameters=["Switch_2"],
            conditions=[SubSelectionCondition(selection=["right"])],
            affected_parameters=[["Frame_A", "Frame_B"]],
        ),
        "Constraint_4": ExcludeConstraint(
            parameters=["Temperature", "Solvent_1"],
            combiner="AND",
            conditions=[
                ThresholdCondition(threshold=151, operator=">"),
                SubSelectionCondition(selection=list(mock_substances)[:2]),
            ],
        ),
        "Constraint_5": ExcludeConstraint(
            parameters=["Pressure", "Solvent_1"],
            combiner="AND",
            conditions=[
                ThresholdCondition(threshold=5, operator=">"),
                SubSelectionCondition(selection=list(mock_substances)[-2:]),
            ],
        ),
        "Constraint_6": ExcludeConstraint(
            parameters=["Pressure", "Temperature"],
            combiner="AND",
            conditions=[
                ThresholdCondition(threshold=3, operator="<"),
                ThresholdCondition(threshold=120, operator=">"),
            ],
        ),
        "Constraint_7": CustomConstraint(
            parameters=["Pressure", "Solvent_1", "Temperature"],
            validator=custom_function,
        ),
        "Constraint_8": SumConstraint(
            parameters=["Fraction_1", "Fraction_2"],
            condition=ThresholdCondition(threshold=150, operator="<="),
        ),
        "Constraint_9": ProductConstraint(
            parameters=["Fraction_1", "Fraction_2"],
            condition=ThresholdCondition(threshold=30, operator=">="),
        ),
        "Constraint_10": SumConstraint(
            parameters=["Fraction_1", "Fraction_2"],
            condition=ThresholdCondition(threshold=100, operator="="),
        ),
        "Constraint_11": PermutationInvarianceConstraint(
            parameters=["Solvent_1", "Solvent_2", "Solvent_3"],
            dependencies=DependenciesConstraint(
                parameters=["Fraction_1", "Fraction_2", "Fraction_3"],
                conditions=[
                    ThresholdCondition(threshold=0.0, operator=">"),
                    ThresholdCondition(threshold=0.0, operator=">"),
                    SubSelectionCondition(
                        selection=list(np.linspace(0, 100, n_grid_points)[1:])
                    ),
                ],
                affected_parameters=[["Solvent_1"], ["Solvent_2"], ["Solvent_3"]],
            ),
        ),
        "Constraint_12": SumConstraint(
            parameters=["Fraction_1", "Fraction_2", "Fraction_3"],
            condition=ThresholdCondition(threshold=100, operator="=", tolerance=0.01),
        ),
        "Constraint_13": NoLabelDuplicatesConstraint(
            parameters=["Solvent_1", "Solvent_2", "Solvent_3"],
        ),
    }
    return [valid_constraints[c] for c in constraint_names]


@pytest.fixture(name="target_names")
def fixture_default_target_selection():
    """The default targets to be used if not specified differently."""
    return ["Target_max"]


@pytest.fixture(name="parameter_names")
def fixture_default_parameter_selection():
    """Default parameters used if not specified differently."""
    return ["Categorical_1", "Categorical_2", "Num_disc_1"]


@pytest.fixture(name="constraint_names")
def fixture_default_constraint_selection():
    """Default constraints used if not specified differently."""
    return []


@pytest.fixture(name="baybe")
def fixture_baybe(parameters, constraints, strategy, objective):
    """Returns a BayBE"""
    return BayBE(
        searchspace=SearchSpace.create(parameters=parameters, constraints=constraints),
        strategy=strategy,
        objective=objective,
    )


@pytest.fixture(name="strategy")
def fixture_default_strategy(
    recommender,
    initial_recommender,
):
    """The default strategy to be used if not specified differently."""
    return Strategy(
        recommender=recommender,
        initial_recommender=initial_recommender,
        allow_repeated_recommendations=False,
        allow_recommending_already_measured=False,
    )


@pytest.fixture(name="acquisition_function_cls")
def fixture_default_acquisition_function():
    """The default acquisition function to be used if not specified differently."""
    return "qEI"


@pytest.fixture(name="surrogate_model_cls")
def fixture_default_surrogate_model():
    """The default surrogate model to be used if not specified differently."""
    return "GP"


@pytest.fixture(name="recommender")
def fixture_recommender(surrogate_model_cls, acquisition_function_cls):
    """The default recommender to be used if not specified differently."""
    return SequentialGreedyRecommender(
        surrogate_model_cls=surrogate_model_cls,
        acquisition_function_cls=acquisition_function_cls,
    )


@pytest.fixture(name="initial_recommender")
def fixture_initial_recommender():
    """The default initial recommender to be used if not specified differently."""
    return RandomRecommender()


@pytest.fixture(name="objective")
def fixture_default_objective(targets):
    """The default objective to be used if not specified differently."""
    mode = "SINGLE" if len(targets) == 1 else "DESIRABILITY"
    return Objective(mode=mode, targets=targets)
