## Example for constraints in a hybrid searchspace

# Example for optimizing a synthetic test functions in a hybrid space with one
# constraint in the discrete subspace and one constraint in the continuous subspace.
# All test functions that are available in BoTorch are also available here and wrapped
# via the `botorch_function_wrapper`.
# This example assumes some basic familiarity with using BayBE.
# We thus refer to [`campaign`](./../Basics/campaign.md) for a basic example.
# Also, there is a large overlap with other examples with regards to using the test function.
# We thus refer to [`discrete_space`](./../Searchspaces/discrete_space.md) for
# details on this aspect.


### Necessary imports for this example

import numpy as np
from botorch.test_functions import Rastrigin

from baybe import Campaign
from baybe.constraints import (
    ContinuousLinearEqualityConstraint,
    DiscreteSumConstraint,
    ThresholdCondition,
)
from baybe.objective import Objective
from baybe.parameters import NumericalContinuousParameter, NumericalDiscreteParameter
from baybe.searchspace import SearchSpace
from baybe.targets import NumericalTarget
from baybe.utils.botorch_wrapper import botorch_function_wrapper

### Defining the test function

# See [`discrete_space`](./../Searchspaces/discrete_space.md) for details.

DIMENSION = 4
TestFunctionClass = Rastrigin

# Specify a numerical stride for discrete parameters.
# If you make it too small, it will make calculations expensive.
# If you make it too large, constraints might not be satisfied anywhere.
STRIDE = 1.0

if not hasattr(TestFunctionClass, "dim"):
    TestFunction = TestFunctionClass(dim=DIMENSION)
else:
    TestFunction = TestFunctionClass()
    DIMENSION = TestFunctionClass().dim

BOUNDS = TestFunction.bounds
WRAPPED_FUNCTION = botorch_function_wrapper(test_function=TestFunction)

### Creating the searchspace and the objective

# Since the searchspace is continuous, we construct `NumericalContinuousParameter`.
# We use the data of the test function to deduce bounds and number of parameters.
parameters = [
    NumericalDiscreteParameter(
        name=f"x_{k + 1}",
        values=np.arange(
            np.round(BOUNDS[0, k], 0),
            np.round(BOUNDS[1, k], 0) + STRIDE,
            STRIDE,
        ).tolist(),
    )
    for k in range(0, DIMENSION // 2)
] + [
    NumericalContinuousParameter(
        name=f"x_{k+1}",
        bounds=(BOUNDS[0, k], BOUNDS[1, k]),
    )
    for k in range(DIMENSION // 2, DIMENSION)
]

# We model the following constraints:
# `1.0*x_1 + 1.0*x_2 = 1.0`
# `1.0*x_3 - 1.0*x_4 = 2.0`
constraints = [
    DiscreteSumConstraint(
        parameters=["x_1", "x_2"],
        condition=ThresholdCondition(
            threshold=1.0, operator="==", tolerance=STRIDE / 2.0
        ),
    ),
    ContinuousLinearEqualityConstraint(
        parameters=["x_3", "x_4"], coefficients=[1.0, -1.0], rhs=2.0
    ),
]

searchspace = SearchSpace.from_product(parameters=parameters, constraints=constraints)
objective = Objective(
    mode="SINGLE", targets=[NumericalTarget(name="Target", mode="MIN")]
)

### Construct the campaign and run some iterations

campaign = Campaign(
    searchspace=searchspace,
    objective=objective,
)

BATCH_SIZE = 5
N_ITERATIONS = 2

for k in range(N_ITERATIONS):
    recommendation = campaign.recommend(batch_size=BATCH_SIZE)

    # target value are looked up via the botorch wrapper
    target_values = []
    for index, row in recommendation.iterrows():
        target_values.append(WRAPPED_FUNCTION(*row.to_list()))

    recommendation["Target"] = target_values

    campaign.add_measurements(recommendation)

### Verify the constraints
measurements = campaign.measurements
TOLERANCE = 0.01

# `1.0*x_1 + 1.0*x_2 = 1.0`
print(
    "1.0*x_1 + 1.0*x_2 = 1.0 satisfied in all recommendations? ",
    np.allclose(
        1.0 * measurements["x_1"] + 1.0 * measurements["x_2"], 1.0, atol=TOLERANCE
    ),
)

# `1.0*x_3 - 1.0*x_4 = 2.0`
print(
    "1.0*x_3 - 1.0*x_4 = 2.0 satisfied in all recommendations? ",
    np.allclose(
        1.0 * measurements["x_3"] - 1.0 * measurements["x_4"], 2.0, atol=TOLERANCE
    ),
)
