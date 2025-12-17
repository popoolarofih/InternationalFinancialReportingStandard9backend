import numpy as np
import pandas as pd


def get_fli_scalar():
    scenario_weights = pd.DataFrame(
        {
            "Scenarios": ["SCENARIO 1", "SCENARIO 2", "SCENARIO 3"],
            "Weights": [0.40, 0.30, 0.30],
        }
    )

    scenario_weights_1 = scenario_weights[
        scenario_weights["Scenarios"] == "SCENARIO 1"
    ]["Weights"].values[0]
    scenario_weights_2 = scenario_weights[
        scenario_weights["Scenarios"] == "SCENARIO 2"
    ]["Weights"].values[0]
    scenario_weights_3 = scenario_weights[
        scenario_weights["Scenarios"] == "SCENARIO 3"
    ]["Weights"].values[0]

    fli_scalar = pd.DataFrame(
        {
            "Quarters": [i + 1 for i in np.arange(40)],
            "Scenario 1": [
                0.750693064,
                0.736241291,
                0.721879727,
                0.707614626,
                0.706037055,
                0.704477353,
                0.702902204,
                0.70131151,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
            ],
            "Scenario 2": [
                0.796913158,
                0.783172894,
                0.769488573,
                0.755865745,
                0.75406716,
                0.752288909,
                0.750492854,
                0.748678906,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
            ],
            "Scenario 3": [
                0.843937607,
                0.831008607,
                0.818106038,
                0.805234614,
                0.803215464,
                0.801218985,
                0.79920222,
                0.797165086,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
                1,
            ],
        }
    )
    fli_scalar["WEIGHTED SCALARS"] = (
        (fli_scalar["Scenario 1"] * scenario_weights_1)
        + (fli_scalar["Scenario 2"] * scenario_weights_2)
        + (fli_scalar["Scenario 3"] * scenario_weights_3)
    )

    fli_scalar = fli_scalar.T
    fli_scalar.columns = fli_scalar.iloc[0].astype(int)
    fli_scalar = fli_scalar.iloc[1:]  # .reset_index()

    fli_scalar_dict = {
        "scenario_weights": scenario_weights,
        "fli_scalar_weights_per_qrt": fli_scalar,
    }
    return fli_scalar_dict
