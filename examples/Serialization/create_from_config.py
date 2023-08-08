"""
This example shows how to load a user defined configuration file and use it to create
a BayBE object. In such a configuration file, the objects used to create a BayBE object
are represented by strings instead of other python objects.
We use the following configuration dictionaries, representing a valid BayBE object.
Note that the json format is required for the config file. Instead of providing the
actual class instances you can create such a config by providing a dictionary with
"type":"name of the class". Example: FPSRecommender() becomes {"type": "FPSRecommender"}
"""

from baybe import BayBE


CONFIG = """
{
    "parameters": [
        {
            "type": "CategoricalParameter",
            "name": "Granularity",
            "values": [
                "coarse",
                "fine",
                "ultra-fine"
            ],
            "encoding": "OHE"
        },
        {
            "type": "NumericalDiscreteParameter",
            "name": "Pressure[bar]",
            "values": [
                1,
                5,
                10
            ],
            "tolerance": 0.2
        },
        {
            "type": "SubstanceParameter",
            "name": "Solvent",
            "data": {
                "Solvent A": "COC",
                "Solvent B": "CCCCC",
                "Solvent C": "COCOC",
                "Solvent D": "CCOCCOCCN"
            },
            "decorrelate": true,
            "encoding": "MORDRED"
        }
    ],
    "constraints": [],
    "objective": {
        "mode": "SINGLE",
        "targets": [
            {
                "name": "Yield",
                "mode": "MAX"
            }
        ]
    },
    "strategy": {
        "initial_recommender": {
            "type": "FPSRecommender"
        },
        "recommender": {
            "type": "SequentialGreedyRecommender",
            "surrogate_model_cls": "GP",
            "acquisition_function_cls": "qEI"
        },
        "allow_repeated_recommendations": false,
        "allow_recommending_already_measured": false
    }
}
"""

# Although we know in this case that the config represents a valid configuration for a
# BayBE object, it is a good practice to enclose the creation in a try block.
try:
    baybe = BayBE.from_config(CONFIG)
    # We now perform a recommendation as usual and print it.
    recommendation = baybe.recommend(batch_quantity=3)
    print(recommendation)
except Exception:  # pylint: disable=W0702
    # Using the CONFIG that is given in this file, this should not be reached.
    print("Something is wrong with the configuration file.")