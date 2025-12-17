#!/usr/bin/env python3
"""
Script to create a default admin user for the Tatum Bank IFRS9 API
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm import Session
from api.database.database import SessionLocal
from api.models.user import User
from api.utils.deps import get_password_hash
from api.schema.user import RoleTypeEnum

def create_admin_user():
    """Create the default admin user"""
    db: Session = SessionLocal()

    try:
        # Check if admin user already exists
        existing_admin = db.query(User).filter(User.email == "info@bstconsulting.co.uk").first()
        if existing_admin:
            print("Admin user already exists!")
            return

        # Create admin user
        admin_user = User(
            full_name="BST",
            email="info@bstconsulting.co.uk",
            hashed_password=get_password_hash("Test@1234."),
            role=RoleTypeEnum.SUPER_ADMIN,
            status="active",
            is_temporary_password=False,
            verification_code=None,
            temp_password_set_at=None,
            refresh_token=None,
            refresh_token_expires_at=None,
            last_logged_in=None,
        )

        db.add(admin_user)
        db.commit()
        db.refresh(admin_user)

        print("Admin user created successfully!")
        print(f"Email: {admin_user.email}")
        print(f"Name: {admin_user.full_name}")
        print(f"Role: {admin_user.role}")
        print(f"Status: {admin_user.status}")

    except Exception as e:
        print(f"Error creating admin user: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    create_admin_user()
