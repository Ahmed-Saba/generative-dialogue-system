from sqlalchemy.orm import DeclarativeBase

# Declarative base for SQLAlchemy models.
# Import this Base into each models module when declaring ORM classes.
class Base(DeclarativeBase):
    pass
