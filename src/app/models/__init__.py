r"""
Centralized access to all database models for the chat application.

This module imports and exposes all the database models through a single point of access, ensuring 
consistent and easy use across the application. 

Without this file, each module would need to import models individually, leading to redundant imports 
and scattered statements. Centralizing imports improves maintainability and reduces the risk of errors.

Example (without centralized imports):

# Without this __init__.py file, each script/module imports models individually
from app.models.user import User
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.message import MessageRole

Example (with centralized imports):

# With this __init__.py file, we can import all models from a single location
from app.models import User, Conversation, Message, MessageRole
"""

from .user import User
from .conversation import Conversation
from .message import Message, MessageRole

__all__ = [
    "User",
    "Conversation",
    "Message",
    "MessageRole"
]
