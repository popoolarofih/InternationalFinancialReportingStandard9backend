import os
import tempfile
import pandas as pd
import numpy as np
import pytest

from ifrsmodel.PD.PDtransition import (
    calculate_cumulative_pds,
    calculate_conditional_pds,
    calculate_conditional_pds_monthly,
    calculate_scaled_conditional_pds_monthly,
    calculate_scaled_marginal_pds_monthly,
    calculate_marginal_pds_for_all_scenarios,
)


@pytest.fixture
def sample_df():
    # Create a small deterministic dataset with the expected columns used by the functions
    sectors = ["Agriculture", "Construction", "Manufacturing", "Services", "Trading"]
    rows = []
    for sector in sectors:
        # Two performing exposures: one that remains performing, one that goes to default
        rows.append({
            "Business sector": sector,
            "Performance classification 2": "Performing",
            "PD Performance after qtr 1": "Performing",
            "Outstanding Balance (₦)": 100.0,
        })
        rows.append({
            "Business sector": sector,
            "Performance classification 2": "Performing",
            "PD Performance after qtr 1": "Default",
            "Outstanding Balance (₦)": 50.0,
        })
        # One non-performing row to ensure filtering works
        rows.append({
            "Business sector": sector,
            "Performance classification 2": "Watchlist",
            "PD Performance after qtr 1": "NA",
            "Outstanding Balance (₦)": 200.0,
        })
    df = pd.DataFrame(rows)
    return df


@pytest.fixture
def quarters():
    return [
        pd.Timestamp('2024-09-30'),
        pd.Timestamp('2024-12-31'),
        pd.Timestamp('2025-03-31'),
        pd.Timestamp('2025-06-30'),
    ]


def test_calculate_cumulative_pds_basic(sample_df, quarters):
    sectors = ["Agriculture", "Construction", "Manufacturing", "Services", "Trading"]
    cum_df = calculate_cumulative_pds(sample_df, sectors, quarters)

    # Expect one row per sector and one column per quarter
    assert list(cum_df.index) == sectors
    assert cum_df.shape == (len(sectors), len(quarters))

    # Values should be probabilities in [0,1] and non-decreasing across quarters
    assert ((cum_df.values >= 0) & (cum_df.values <= 1)).all()
    for sector in sectors:
        vals = cum_df.loc[sector].values
        assert np.all(np.diff(vals) >= -1e-12)  # non-decreasing with tolerance


def test_conditional_and_monthly_conversion(sample_df, quarters):
    sectors = ["Agriculture", "Construction", "Manufacturing", "Services", "Trading"]
    cum_df = calculate_cumulative_pds(sample_df, sectors, quarters)

    # Conditional PDs (quarterly) uses the first cumulative pd column as h_q
    cond_q_df = calculate_conditional_pds(cum_df)
    assert cond_q_df.shape == cum_df.shape

    # Convert to monthly using the implemented formula: h_m = 1 - (1 - h_q)^(1/3)
    cond_monthly = calculate_conditional_pds_monthly(cond_q_df)

    # Expect 12 months (3 months per quarter * 4 quarters)
    assert cond_monthly.shape[1] == 12

    for sector in sectors:
        h_q = float(cond_q_df.loc[sector].iloc[0])
        expected_h_m = 1.0 - (1.0 - h_q) ** (1.0 / 3.0)
        # Compare to first month value (they are constant per quarter in this implementation)
        got = float(cond_monthly.loc[sector, 'Month 1'])
        assert pytest.approx(expected_h_m, rel=1e-6) == got


def test_scaled_and_marginal_workflow(sample_df, quarters):
    sectors = ["Agriculture", "Construction", "Manufacturing", "Services", "Trading"]
    cum_df = calculate_cumulative_pds(sample_df, sectors, quarters)
    cond_q_df = calculate_conditional_pds(cum_df)
    cond_monthly = calculate_conditional_pds_monthly(cond_q_df)

    # Use scalar list of ones to keep values unchanged
    scalars = [1.0] * 12
    scaled = calculate_scaled_conditional_pds_monthly(cond_monthly, scalars)

    # scaled should equal the first 12 months of cond_monthly (within tolerance)
    for sector in sectors:
        np.testing.assert_allclose(
            scaled.loc[sector].astype(float).values,
            cond_monthly.loc[sector].values[:12].astype(float),
            rtol=1e-8,
            atol=1e-12,
        )

    # Now compute marginal PDs from scaled conditionals
    marginal = calculate_scaled_marginal_pds_monthly(scaled)
    assert marginal.shape == scaled.shape

    # Marginals should be in [0,1] and their sum per sector should be <= 1
    for sector in sectors:
        vals = marginal.loc[sector].astype(float).values
        assert (vals >= 0).all() and (vals <= 1).all()
        assert vals.sum() <= 1.0 + 1e-12


def test_marginal_pds_for_all_scenarios(sample_df, quarters):
    # Build the chain up to conditional monthly
    sectors = ["Agriculture", "Construction", "Manufacturing", "Services", "Trading"]
    cum_df = calculate_cumulative_pds(sample_df, sectors, quarters)
    cond_q_df = calculate_conditional_pds(cum_df)
    cond_monthly = calculate_conditional_pds_monthly(cond_q_df)

    # Dummy macro scalars object with the required method
    class DummyMacro:
        def get_scalars_by_scenario(self, key):
            return [1.0] * 12

    macro = DummyMacro()
    results = calculate_marginal_pds_for_all_scenarios(cond_monthly, macro)

    # Expect keys for the scenarios
    expected_keys = {"Base Marginal", "Best Marginal", "Worse Marginal", "Scenario Weighted"}
    assert set(results.keys()) == expected_keys

    # Each entry should be a DataFrame with the same index as sectors
    for df in results.values():
        assert list(df.index) == sectors
        assert df.shape[1] == 12
        # Values in valid probability range
        assert ((df.values >= 0) & (df.values <= 1)).all()

