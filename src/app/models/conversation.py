from sqlalchemy import String, DateTime, ForeignKey, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime
from app.database.base import Base
from .user import User
import uuid
from typing import TYPE_CHECKING

# Avoid circular import issues when using type hints for related models
if TYPE_CHECKING:
    from .user import User
    from .message import Message

class Conversation(Base):
    """
    SQLAlchemy model for a Conversation.

    Represents a chat conversation, which is owned by a single user and can contain many messages.
    """
    __tablename__ = "conversations"

    # Primary key: UUID (generated using uuid4), indexed for faster lookup
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    
    # Optional title for the conversation (can be null)
    title: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True
    )

    # Foreign key linking the conversation to its owner (User)
    # UUID type must match the users.id field
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        index=True
    )

    # Automatically set when the conversation is created
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    # Automatically updated whenever the conversation is modified
    updated_at: Mapped[datetime] = mapped_column(DateTime(
        timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False)

    # --- Relationships ---

    # Many-to-One: Each conversation belongs to a single user
    user: Mapped["User"] = relationship(
        "User",
        back_populates="conversations"
    )

    # One-to-Many: A conversation has many messages
    messages: Mapped[list["Message"]] = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        lazy="select",
        order_by="Message.created_at"
    )

    def __repr__(self) -> str:
        return f"<Conversation(id={self.id!r}, title={self.title!r}, user_id={self.user_id!r})>"


# You might later consider adding:
#   - `is_archived` or `is_deleted` for soft deletion logic.
#   - `last_message_at` to optimize listing latest conversations.
