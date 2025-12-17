from sqlmodel import Session, select
from api.database.database import engine
from api.models.otherinputs import RepaymentFrequency, CollateralAssumption
import pandas as pd

def load_other_inputs():
    """Return repayment frequencies and collateral assumptions as pandas DataFrames loaded from the database."""
    with Session(engine) as session:
        repayment_freqs = session.exec(select(RepaymentFrequency)).all()
        collateral_assumptions = session.exec(select(CollateralAssumption)).all()

        repayment_df = pd.DataFrame(
            [(rf.repayment_frequency, rf.times_per_year) for rf in repayment_freqs],
            columns=['Repayment Frequency', 'Times per Year']
        )

        collateral_df = pd.DataFrame(
            [
                (ca.collateral_description, ca.cbn_accepted_collateral_type, ca.haircut, ca.time_to_recovery_years, ca.direct_recovery_cost)
                for ca in collateral_assumptions
            ],
            columns=['Collateral Description', 'CBN Accepted Collateral Type', 'Haircut', 'Time to Recovery (years)', 'Direct Recovery Cost']
        )

        return repayment_df, collateral_df
