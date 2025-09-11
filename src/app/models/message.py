from sqlalchemy import DateTime, ForeignKey, Text, UUID
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime
from enum import Enum as PyEnum
from database import Base
from .conversation import Conversation
import uuid


class MessageRole(PyEnum):
    """Enum for message roles"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )

    role: Mapped[MessageRole] = mapped_column(
        SQLEnum(MessageRole),
        nullable=False,
        index=True
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id"),
        nullable=False,
        index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    # Relationships
    conversation: Mapped["Conversation"] = relationship(
        "Conversation",
        back_populates="messages"
    )

    def __repr__(self) -> str:
        return f"<Message(id={self.id!r}, role={self.role.value!r}, conversation_id={self.conversation_id!r})>"


# Notes:
# - Use `SQLEnum` for the column type and `PyEnum` for your Python enum.
