from api.database import SessionLocal
from api.models.user import StagingFile, EADFile, LGDFile, FLIFile, User

db = SessionLocal()

print("Users:")
users = db.query(User).all()
for user in users:
    print(f"ID: {user.id}, Email: {user.email}")

print("\nStaging Files:")
staging_files = db.query(StagingFile).all()
for f in staging_files:
    print(f"ID: {f.id}, User ID: {f.user_id}, Data length: {len(f.data) if f.data else 0}")

print("\nEAD Files:")
ead_files = db.query(EADFile).all()
for f in ead_files:
    print(f"ID: {f.id}, User ID: {f.user_id}, Data length: {len(f.month_year_data) if f.month_year_data else 0}")

print("\nLGD Files:")
lgd_files = db.query(LGDFile).all()
for f in lgd_files:
    print(f"ID: {f.id}, User ID: {f.user_id}, Data length: {len(f.data) if f.data else 0}")

print("\nFLI Files:")
fli_files = db.query(FLIFile).all()
for f in fli_files:
    print(f"ID: {f.id}, User ID: {f.user_id}, Forecast scalars length: {len(f.forecast_scalars) if f.forecast_scalars else 0}")

db.close()
