"""Test Polars implementations of constraints."""

import polars as pl
import pytest

from baybe.searchspace.discrete import _apply_polars_constraint_filter


def _lazyframe_from_product(parameters):
    """Create a Polars lazyframe from the product of given parameters and return it."""
    param_frames = [pl.LazyFrame({p.name: p.values}) for p in parameters]

    # Handling edge cases
    if len(param_frames) == 1:
        return param_frames[0]

    # Cross-join parameters
    res = param_frames[0]
    for frame in param_frames[1:]:
        res = res.join(frame, how="cross", force_parallel=True)

    return res


@pytest.mark.parametrize("parameter_names", [["Fraction_1", "Fraction_2"]])
@pytest.mark.parametrize("constraint_names", [["Constraint_8"]])
def test_polars_prodsum1(parameters, constraints):
    """Tests Polars implementation of sum constraint."""
    ldf = _lazyframe_from_product(parameters)

    ldf = _apply_polars_constraint_filter(ldf, constraints)

    # Number of entries with 1,2-sum above 150
    ldf = ldf.with_columns(sum=pl.sum_horizontal(["Fraction_1", "Fraction_2"]))
    ldf = ldf.filter(pl.col("sum") > 150)
    num_entries = len(ldf.collect())

    assert num_entries == 0


@pytest.mark.parametrize("parameter_names", [["Fraction_1", "Fraction_2"]])
@pytest.mark.parametrize("constraint_names", [["Constraint_9"]])
def test_polars_prodsum2(parameters, constraints):
    """Tests Polars implementation of product constrain."""
    ldf = _lazyframe_from_product(parameters)

    ldf = _apply_polars_constraint_filter(ldf, constraints)

    # Number of entries with product under 30
    df = ldf.filter(
        pl.reduce(lambda acc, x: acc * x, pl.col(["Fraction_1", "Fraction_2"])).alias(
            "prod"
        )
        < 30
    ).collect()

    num_entries = len(df)
    assert num_entries == 0


@pytest.mark.parametrize("parameter_names", [["Fraction_1", "Fraction_2"]])
@pytest.mark.parametrize("constraint_names", [["Constraint_10"]])
def test_polars_prodsum3(parameters, constraints):
    """Tests Polars implementation of exact sum constraint."""
    ldf = _lazyframe_from_product(parameters)

    ldf = _apply_polars_constraint_filter(ldf, constraints)

    # Number of entries with sum unequal to 100
    ldf = ldf.with_columns(sum=pl.sum_horizontal(["Fraction_1", "Fraction_2"]))
    df = ldf.select(abs(pl.col("sum") - 100)).filter(pl.col("sum") > 0.01).collect()

    num_entries = len(df)

    assert num_entries == 0


@pytest.mark.parametrize(
    "parameter_names",
    [["Solvent_1", "SomeSetting", "Temperature", "Pressure"]],
)
@pytest.mark.parametrize(
    "constraint_names", [["Constraint_4", "Constraint_5", "Constraint_6"]]
)
def test_polars_exclusion(mock_substances, parameters, constraints):
    """Tests Polars implementation of exclusion constraint."""
    ldf = _lazyframe_from_product(parameters)

    ldf = _apply_polars_constraint_filter(ldf, constraints)

    # Number of entries with either first/second substance and a temperature above 151

    df = ldf.filter(
        (pl.col("Temperature") > 151)
        & (pl.col("Solvent_1").is_in(list(mock_substances)[:2]))
    ).collect()
    num_entries = len(df)
    assert num_entries == 0

    # Number of entries with either last / second last substance and a pressure above 5
    df = ldf.filter(
        (pl.col("Pressure") > 5)
        & (pl.col("Solvent_1").is_in(list(mock_substances)[-2:]))
    ).collect()
    num_entries = len(df)
    assert num_entries == 0

    # Number of entries with pressure below 3 and temperature above 120
    df = ldf.filter((pl.col("Pressure") < 3) & (pl.col("Temperature") > 120)).collect()
    num_entries = len(df)
    assert num_entries == 0
