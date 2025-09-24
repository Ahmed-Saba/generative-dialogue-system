"""
Repository layer initialization module.

This module exports all repository classes for easy importing throughout the application.
The repository pattern provides a clean abstraction layer between the business logic
and data access layer, making the code more testable and maintainable.

Usage:
    from app.repositories import UserRepository, ConversationRepository, MessageRepository
"""

from .base_repository import BaseRepository
from .user_repository import UserRepository
from .conversation_repository import ConversationRepository
from .message_repository import MessageRepository

__all__ = [
    "BaseRepository",
    "UserRepository", 
    "ConversationRepository",
    "MessageRepository"
]
