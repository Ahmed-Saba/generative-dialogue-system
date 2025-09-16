from sqlalchemy import DateTime, ForeignKey, Text, UUID
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime
from enum import Enum as PyEnum
from app.database.base import Base
import uuid
from typing import TYPE_CHECKING

# Avoid circular import issues when using type hints for related models
if TYPE_CHECKING:
    from .conversation import Conversation

# ------------------------------
# Enum to define message roles
# ------------------------------
class MessageRole(PyEnum):
    """Enum representing the role of the message sender."""
    USER = "user"             # Sent by the user
    ASSISTANT = "assistant"   # Sent by the assistant (e.g. my AI model)
    SYSTEM = "system"         # System-level messages or instructions


# ------------------------------
# Message Model
# ------------------------------
class Message(Base):
    """
    SQLAlchemy model representing a message in a conversation.

    Each message is linked to a conversation and has a role
    indicating who sent it (user, assistant, or system).
    """
    __tablename__ = "messages"

    # Primary key - UUID for global uniqueness
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )

    # Message content (can be multi-line, so Text is used)
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )

    # Role of the message sender (user, assistant, system)
    role: Mapped[MessageRole] = mapped_column(
        SQLEnum(MessageRole),  # SQLAlchemy Enum, based on Python Enum
        nullable=False,
        index=True  # Indexed for faster querying/filtering by role
    )

    # Foreign key reference to parent conversation
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id"),  # Points to Conversation model
        nullable=False,
        index=True
    )

    # Timestamp of message creation (automatically set on insert)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    # --- Relationships ---

    # Back-reference to the parent conversation
    conversation: Mapped["Conversation"] = relationship(
        "Conversation",
        back_populates="messages"
    )

    def __repr__(self) -> str:
        # Helpful for debugging/logging
        return f"<Message(id={self.id!r}, role={self.role.value!r}, conversation_id={self.conversation_id!r})>"


# Notes:
# - Use `SQLEnum` for the column type and `PyEnum` for your Python enum.
