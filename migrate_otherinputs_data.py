import pandas as pd
from sqlmodel import Session, create_engine, select
from api.models.otherinputs import RepaymentFrequency, CollateralAssumption
from api.database.database import engine

def migrate_otherinputs_data():
    with Session(engine) as session:
        # Load Excel file
        file_path = 'worktemplates/OtherInputs.xlsx'
        df = pd.read_excel(file_path, sheet_name='Other Inputs', header=0)

        # Migrate RepaymentFrequency (rows 3-8)
        repayment_df = df.iloc[3:9, 1:3].copy()
        repayment_df.columns = ['repayment_frequency', 'times_per_year']
        repayment_df = repayment_df.dropna().reset_index(drop=True)

        for _, row in repayment_df.iterrows():
            existing = session.exec(
                select(RepaymentFrequency).where(RepaymentFrequency.repayment_frequency == row['repayment_frequency'])
            ).first()
            if not existing:
                rf = RepaymentFrequency(
                    repayment_frequency=row['repayment_frequency'],
                    times_per_year=int(row['times_per_year'])
                )
                session.add(rf)

        # Migrate CollateralAssumption (rows 12-14)
        collateral_df = df.iloc[12:15, 1:6].copy()
        collateral_df.columns = [
            'collateral_description',
            'cbn_accepted_collateral_type',
            'haircut',
            'time_to_recovery_years',
            'direct_recovery_cost'
        ]
        collateral_df = collateral_df.dropna().reset_index(drop=True)

        for _, row in collateral_df.iterrows():
            existing = session.exec(
                select(CollateralAssumption).where(CollateralAssumption.collateral_description == row['collateral_description'])
            ).first()
            if not existing:
                ca = CollateralAssumption(
                    collateral_description=row['collateral_description'],
                    cbn_accepted_collateral_type=row['cbn_accepted_collateral_type'],
                    haircut=float(row['haircut']),
                    time_to_recovery_years=float(row['time_to_recovery_years']),
                    direct_recovery_cost=float(row['direct_recovery_cost'])
                )
                session.add(ca)

        session.commit()
        print("Data migration from Excel to database completed successfully.")

if __name__ == "__main__":
    migrate_otherinputs_data()

