from api.database import SessionLocal
from api.data_model import User

db = SessionLocal()
users = db.query(User).all()
for user in users:
    print(user.id, user.email, user.full_name, user.role, user.status)
db.close()
