# models/user.py
#
# Defines the "users" table. Each attribute below becomes a column.

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime
from services.database_service import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(120), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)  # never store the raw password!
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<User id={self.id} email={self.email}>"
