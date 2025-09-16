from sqlalchemy import String, DateTime, Boolean, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime
from app.database.base import Base
import uuid
from typing import TYPE_CHECKING

# Avoid circular import issues when using type hints for related models
if TYPE_CHECKING:
    from .conversation import Conversation

class User(Base):
    """
    SQLAlchemy model for User.

    Represents an application user with credentials, profile information,
    and a one-to-many relationship with conversations.
    """
    __tablename__ = "users"

    # Unique identifier for the user (primary key)
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True  # Indexed for faster lookups
    )

    # Username (must be unique and non-null)
    username: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        index=True,
        nullable=False
    )

    # Email address (must be unique and non-null)
    email: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=False
    )

    # Hashed password (never store plain-text passwords)
    hashed_password: Mapped[str] = mapped_column(
        String(255),    # Can handle long hashes like bcrypt
        nullable=False
    )

    # Whether the user account is active (soft-deletion toggle)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )

    # Timestamp for when the user was created
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    # Timestamp for last update (auto-updated on modification)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    # --- Relationships ---

    # One-to-Many: A user can have multiple conversations
    conversations: Mapped[list["Conversation"]] = relationship(
        "Conversation",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="select"
    )

    def __repr__(self) -> str:
        # Helpful for debugging/logging
        return f"<User(id={self.id!r}, username={self.username!r}, email={self.email!r})>"
