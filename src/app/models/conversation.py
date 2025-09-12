from sqlalchemy import String, DateTime, ForeignKey, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime
from app.database.base import Base
from .user import User
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .user import User
    from .message import Message

class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )

    title: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True
    )

    # IMPORTANT: use UUID here (same type as users.id)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    updated_at: Mapped[datetime] = mapped_column(DateTime(
        timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False)

    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="conversations"
    )

    messages: Mapped[list["Message"]] = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        lazy="select",
        order_by="Message.created_at"
    )

    def __repr__(self) -> str:
        return f"<Conversation(id={self.id!r}, title={self.title!r}, user_id={self.user_id!r})>"
