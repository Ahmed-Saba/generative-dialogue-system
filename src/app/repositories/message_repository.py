"""
Message repository for handling message-specific database operations.

This module provides the MessageRepository class which extends BaseRepository
with message-specific functionality like conversation-based queries,
role-based filtering, and message history management.
"""

from typing import Optional, List
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
import logging

from app.models.message import Message, MessageRole
from app.models.conversation import Conversation
from .base_repository import BaseRepository, NotFoundError, RepositoryError

logger = logging.getLogger(__name__)


class MessageRepository(BaseRepository[Message]):
    """
    Repository for Message entity operations.

    Provides specialized methods for message management including
    conversation-based queries, role filtering, and message history.
    """

    def __init__(self, db: AsyncSession):
        """
        Initialize the message repository.

        Args:
            db: The async database session
        """
        super().__init__(Message, db)

    # =================================================================================================================
    # Create Operations
    # =================================================================================================================

    async def create_message(
        self,
        conversation_id: UUID,
        content: str,
        role: MessageRole
    ) -> Message:
        """
        Create a new message in a conversation.

        This method ensures the conversation exists before creating the message.
        It also updates the conversation's `updated_at` timestamp to reflect the
        new activity.

        Args:
            conversation_id (UUID): UUID of the conversation.
            content (str): The message content.
            role (MessageRole): The sender's role (user, assistant, system).

        Returns:
            Message: The created Message entity.

        Raises:
            NotFoundError: If the conversation does not exist.
            RepositoryError: If any database-related error occurs.
        """
        logger.info(
            f"Creating new {role.value} message in conversation: {conversation_id}")

        try:
            # Step 1: Ensure the conversation exists
            conversation_query = select(Conversation.id).where(
                Conversation.id == conversation_id)
            conversation_result = await self.db.execute(conversation_query)
            if conversation_result.scalar_one_or_none() is None:
                raise NotFoundError(
                    f"Conversation with ID {conversation_id} not found")

            # Step 2: Create the message
            message = await self.create(
                conversation_id=conversation_id,
                content=content.strip(),
                role=role
            )

            # Step 3: Update conversation's last activity timestamp
            from sqlalchemy import func, update
            stmt = (
                update(Conversation)
                .where(Conversation.id == conversation_id)
                .values(updated_at=func.now())
            )
            await self.db.execute(stmt)

            return message

        except Exception as e:
            logger.error(
                f"Failed to create message for conversation {conversation_id}: {e}")
            raise RepositoryError("Failed to create message") from e

    async def bulk_create_messages(
        self,
        messages_data: List[dict]
    ) -> List[Message]:
        """
        Create multiple messages in bulk for better performance.

        Args:
            messages_data: List of dictionaries containing message data
                          Each dict should have: conversation_id, content, role

        Returns:
            List of created Message entities

        Raises:
            RepositoryError: For database errors
        """
        try:
            # Return early if input list is empty
            if not messages_data:
                return []

            messages = []
            for data in messages_data:
                # Create a new Message instance from each dictionary's data
                message = Message(
                    conversation_id=data['conversation_id'],
                    content=data['content'].strip(),
                    role=data['role']
                )
                messages.append(message)
                # Add message to the current DB session (not committed yet)
                self.db.add(message)

            # Flush all pending additions to the database
            # This sends INSERTs without committing, so we get assigned IDs etc.
            await self.db.flush()

            # Refresh each message instance to populate DB-generated fields (like id, timestamps)
            for message in messages:
                await self.db.refresh(message)

            logger.info(f"Bulk created {len(messages)} messages")
            return messages
        except Exception as e:
            # Rollback session on error to keep DB consistent
            await self.db.rollback()
            logger.error(f"Error bulk creating messages: {e}")
            raise RepositoryError(f"Failed to bulk create messages") from e

    # =================================================================================================================
    # Read Operations
    # =================================================================================================================

    async def get_conversation_messages(
        self,
        conversation_id: UUID,
        offset: int = 0,
        limit: Optional[int] = None,
        order_desc: bool = False
    ) -> List[Message]:
        """
        Retrieve messages for a specific conversation.

        This method supports optional pagination and ordering to enable
        efficient browsing or infinite scrolling of conversation history.

        Args:
            conversation_id (UUID): The ID of the conversation.
            offset (int): Number of messages to skip (default is 0).
            limit (Optional[int]): Maximum number of messages to return (None for all).
            order_desc (bool): If True, orders messages by newest first; else oldest first.

        Returns:
            List[Message]: A list of Message entities ordered by creation time.

        Raises:
            RepositoryError: If a database error occurs.
        """
        try:
            query = select(Message).where(
                Message.conversation_id == conversation_id)

            # Apply sorting
            query = query.order_by(
                Message.created_at.desc() if order_desc else Message.created_at.asc()
            )

            # Pagination controls
            query = query.offset(offset)
            if limit is not None:
                query = query.limit(limit)

            result = await self.db.execute(query)
            messages = result.scalars().all()

            logger.debug(
                f"Retrieved {len(messages)} messages for conversation: {conversation_id}")
            return list(messages)

        except Exception as e:
            logger.error(
                f"Error retrieving messages for conversation {conversation_id}: {e}")
            raise RepositoryError(
                "Failed to retrieve conversation messages") from e

        # Method Summary: get_conversation_messages
        # | Detail             | Description                                           |
        # | ------------------ | ----------------------------------------------------- |
        # | **Purpose**        | Retrieves messages from a given conversation.         |
        # | **Params**         | `conversation_id`, `offset`, `limit`, `order_desc`    |
        # | **Ordering**       | Ascending by default, descending if `order_desc=True` |
        # | **Pagination**     | Supports offset/limit for client-side paging          |
        # | **Returns**        | A list of `Message` entities sorted by `created_at`   |
        # | **Error Handling** | Logs and raises `RepositoryError` on failure          |

    async def get_messages_by_role(
        self,
        conversation_id: UUID,
        role: MessageRole,
        limit: int = 50
    ) -> List[Message]:
        """
        Retrieve messages from a specific role within a conversation.

        This method filters messages by role (e.g., user, assistant, system),
        making it useful for debugging, analytics, or UI differentiation.

        Args:
            conversation_id (UUID): The ID of the conversation to query.
            role (MessageRole): The role to filter messages by.
            limit (int): Maximum number of messages to return (default: 50).

        Returns:
            List[Message]: Messages matching the specified role, ordered by creation time.

        Raises:
            RepositoryError: If a database error occurs during the query.
        """
        try:
            query = (
                select(Message)
                .where(
                    and_(
                        Message.conversation_id == conversation_id,
                        Message.role == role
                    )
                )
                .order_by(Message.created_at.asc())
                .limit(limit)
            )

            result = await self.db.execute(query)
            messages = result.scalars().all()

            logger.debug(
                f"Retrieved {len(messages)} {role.value} messages for conversation: {conversation_id}")
            return list(messages)

        except Exception as e:
            logger.error(
                f"Error retrieving {role.value} messages for conversation {conversation_id}: {e}")
            raise RepositoryError(
                f"Failed to retrieve messages by role") from e

    async def get_latest_message(self, conversation_id: UUID) -> Optional[Message]:
        """
        Retrieve the most recent message in a conversation.

        This method is useful for showing a conversation preview, 
        detecting the last user/assistant action, or sorting by activity.

        Args:
            conversation_id (UUID): The ID of the conversation.

        Returns:
            Optional[Message]: The latest message, or None if no messages exist.

        Raises:
            RepositoryError: If a database error occurs during the query.
        """
        try:
            query = (
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.desc())
                .limit(1)
            )

            result = await self.db.execute(query)
            message = result.scalar_one_or_none()

            if message:
                logger.debug(
                    f"Retrieved latest message for conversation: {conversation_id}")
            else:
                logger.debug(
                    f"No messages found for conversation: {conversation_id}")

            return message
        except Exception as e:
            logger.error(
                f"Error retrieving latest message for conversation {conversation_id}: {e}")
            raise RepositoryError(f"Failed to retrieve latest message") from e

        # Method Summary: get_latest_message
        # | Detail             | Description                                                        |
        # | ------------------ | ------------------------------------------------------------------ |
        # | **Purpose**        | Retrieves the most recent message from a specific conversation     |
        # | **Params**         | `conversation_id`                                                  |
        # | **Ordering**       | Ordered by `created_at DESC` (newest first)                        |
        # | **Limit**          | 1 message                                                          |
        # | **Returns**        | The latest `Message` entity or `None` if no messages exist         |
        # | **Use Cases**      | Displaying last activity preview, chat summaries, recency tracking |
        # | **Error Handling** | Logs error and raises `RepositoryError`                            |

    async def get_message_with_conversation(self, message_id: UUID) -> Optional[Message]:
        """
        Retrieve a message along with its associated conversation.

        This is useful when you need both the message details and its
        parent conversation for context or audit purposes.

        Args:
            message_id (UUID): The ID of the message to retrieve.

        Returns:
            Optional[Message]: The message with its conversation loaded,
            or None if the message was not found.

        Raises:
            RepositoryError: If an error occurs during database access.
        """
        try:
            query = (
                select(Message)
                .where(Message.id == message_id)
                .options(selectinload(Message.conversation))
            )

            result = await self.db.execute(query)
            message = result.scalar_one_or_none()

            if message:
                logger.debug(
                    f"Retrieved message with conversation: {message_id}")
            else:
                logger.debug(f"No message found with ID: {message_id}")

            return message
        except Exception as e:
            logger.error(
                f"Error retrieving message with conversation {message_id}: {e}")
            raise RepositoryError(
                f"Failed to retrieve message with conversation") from e

    async def search_messages(
        self,
        conversation_id: UUID,
        search_term: str,
        role: Optional[MessageRole] = None,
        limit: int = 50
    ) -> List[Message]:
        """
        Search messages within a conversation by content.

        Allows full-text-like search using ILIKE for case-insensitive matching,
        optionally filtering by message role (e.g., user, assistant).

        Args:
            conversation_id: UUID of the conversation
            search_term: Term to search for in message content
            role: Optional role filter (e.g., user, assistant, system)
            limit: Maximum number of messages to return

        Returns:
            List of matching Message entities ordered by newest first

        Raises:
            RepositoryError: If the search query fails
        """
        try:
            # Prepare the search pattern for case-insensitive match using SQL ILIKE
            # Trim whitespace, wrap with wildcards
            search_pattern = f"%{search_term.strip()}%"

            # Build base conditions for the query
            conditions = [
                Message.conversation_id == conversation_id,
                # Case-insensitive pattern match
                Message.content.ilike(search_pattern)
            ]

            # Optionally filter by role if specified (e.g., only user messages)
            if role is not None:
                conditions.append(Message.role == role)

            # Construct the final query with optional role filter
            query = (
                select(Message)
                .where(and_(*conditions))  # Combine all conditions safely
                # Most recent messages first
                .order_by(Message.created_at.desc())
                .limit(limit)
            )

            # Execute and collect matching messages
            result = await self.db.execute(query)
            messages = result.scalars().all()

            logger.debug(
                f"Found {len(messages)} messages matching '{search_term}' in conversation: {conversation_id}")
            return list(messages)

        except Exception as e:
            logger.error(
                f"Error searching messages in conversation {conversation_id} for term '{search_term}': {e}")
            raise RepositoryError("Failed to search messages") from e

    async def get_conversation_history(
        self,
        conversation_id: UUID,
        include_system: bool = True,
        limit: Optional[int] = None
    ) -> List[Message]:
        """
        Get conversation history in chronological order.

        This method is optimized for retrieving conversation context
        for AI processing or user display, optionally filtering out
        system messages and returning only the most recent interactions.

        Args:
            conversation_id: UUID of the conversation
            include_system: Whether to include system messages in the result
            limit: Maximum number of messages to return (most recent N)

        Returns:
            List of Message entities in chronological (oldest-first) order

        Raises:
            RepositoryError: If the query fails due to a database error
        """
        try:
            # Base query: all messages in the conversation
            query = select(Message).where(
                Message.conversation_id == conversation_id)

            # Optionally exclude system messages from the history
            if not include_system:
                query = query.where(Message.role != MessageRole.SYSTEM)

            # Default order is chronological (oldest first)
            query = query.order_by(Message.created_at.asc())

            if limit is not None:
                # When a limit is applied, we need to fetch the *most recent* N messages,
                # then re-order them into chronological order for correct context flow.

                # Step 1: Create a subquery selecting the latest N messages in reverse order
                subquery = (
                    select(Message)
                    .where(Message.conversation_id == conversation_id)
                    .order_by(Message.created_at.desc())
                    .limit(limit)
                ).subquery()

                # Step 2: Re-select from the subquery and re-order chronologically
                query = select(Message).select_from(
                    subquery).order_by(Message.created_at.asc())

            # Execute the query and return results
            result = await self.db.execute(query)
            messages = result.scalars().all()

            logger.debug(
                f"Retrieved conversation history with {len(messages)} messages for: {conversation_id}")
            return list(messages)

        except Exception as e:
            logger.error(
                f"Error retrieving conversation history for {conversation_id}: {e}")
            raise RepositoryError(
                "Failed to retrieve conversation history") from e

    async def get_recent_messages_across_conversations(
        self,
        user_id: UUID,
        limit: int = 50
    ) -> List[Message]:
        """
        Get recent messages from all conversations belonging to a specific user.

        This is useful for displaying an activity feed or recent chat history
        across multiple conversations.

        Args:
            user_id: UUID of the user whose conversations' messages are retrieved
            limit: Maximum number of messages to return (defaults to 50)

        Returns:
            List of Message entities ordered by most recent first

        Raises:
            RepositoryError: If the query or execution fails
        """
        try:
            # Build a query selecting Message entities joined with their Conversations
            # Filter by user_id on the Conversation to get messages only from this user's conversations
            query = (
                select(Message)
                .join(Conversation, Message.conversation_id == Conversation.id)
                .where(Conversation.user_id == user_id)
                # Eagerly load the Conversation relationship on the Message for convenience
                .options(selectinload(Message.conversation))
                # Order messages by creation time descending (newest first)
                .order_by(Message.created_at.desc())
                # Limit the result set to the specified limit
                .limit(limit)
            )

            # Execute the query asynchronously
            result = await self.db.execute(query)

            # Extract the list of Message entities from the result
            messages = result.scalars().all()

            logger.debug(
                f"Retrieved {len(messages)} recent messages for user: {user_id}")

            return list(messages)

        except Exception as e:
            logger.error(
                f"Error retrieving recent messages for user {user_id}: {e}")
            raise RepositoryError(f"Failed to retrieve recent messages") from e

    async def count_conversation_messages(self, conversation_id: UUID) -> int:
        """
        Count the number of messages in a conversation.

        This provides a simple count of all messages (regardless of role)
        within the specified conversation.

        Args:
            conversation_id: UUID of the conversation to count messages for

        Returns:
            int: Total number of messages in the conversation
        """
        # Delegates to the base repository's generic count() method
        return await self.count(conversation_id=conversation_id)

    async def count_messages_by_role(self, conversation_id: UUID, role: MessageRole) -> int:
        """
        Count messages of a specific role in a conversation.

        Useful for determining how many user/assistant/system messages
        exist within a given conversation.

        Args:
            conversation_id: UUID of the conversation to filter messages from
            role: The specific role (user, assistant, system) to count

        Returns:
            int: Number of messages that match the specified role within the conversation

        Raises:
            RepositoryError: If the count query fails due to a database error
        """
        try:
            from sqlalchemy import func

            # Build count query to get number of messages with the specified role
            query = select(func.count(Message.id)).where(
                and_(
                    Message.conversation_id == conversation_id,  # Filter by conversation
                    Message.role == role                          # Filter by role
                )
            )

            # Execute the query
            result = await self.db.execute(query)

            # Get the count from the result
            count = result.scalar() or 0

            logger.debug(
                f"Counted {count} {role.value} messages in conversation: {conversation_id}")
            return count
        except Exception as e:
            logger.error(
                f"Error counting {role.value} messages for conversation {conversation_id}: {e}")
            raise RepositoryError("Failed to count messages by role") from e

    async def get_user_message_count(self, user_id: UUID) -> int:
        """
        Get the total number of messages across all conversations belonging to a user.

        This counts every message that is part of any conversation owned by the specified user.

        Args:
            user_id: UUID of the user whose message count is to be retrieved

        Returns:
            The total count of messages across all the user's conversations

        Raises:
            RepositoryError: If the query fails
        """
        try:
            from sqlalchemy import func

            # Build a query to count Message IDs by joining Message to Conversation,
            # filtering conversations by the specified user_id
            query = (
                select(func.count(Message.id))
                .join(Conversation, Message.conversation_id == Conversation.id)
                .where(Conversation.user_id == user_id)
            )

            # Execute the query asynchronously
            result = await self.db.execute(query)

            # Extract the scalar count result or default to 0 if none
            count = result.scalar() or 0

            logger.debug(f"User {user_id} has {count} total messages")

            return count

        except Exception as e:
            logger.error(f"Error counting messages for user {user_id}: {e}")
            raise RepositoryError(f"Failed to count user messages") from e

    async def update_message_content(self, message_id: UUID, content: str) -> Optional[Message]:
        """
        Update the content of a message.

        This method updates the textual content of a specific message
        identified by its UUID. It trims whitespace from the new content
        before saving.

        Args:
            message_id: UUID of the message to update
            content: New content string for the message

        Returns:
            The updated Message entity if found, otherwise None

        Raises:
            RepositoryError: If the update operation fails
        """
        logger.info(f"Updating content for message: {message_id}")

        # Call the generic update method inherited from BaseRepository,
        # updating only the content field after trimming whitespace.
        return await self.update(message_id, content=content.strip())

    async def delete_conversation_messages(self, conversation_id: UUID) -> int:
        """
        Delete all messages in a conversation.

        This method removes every message associated with the specified conversation.
        It is typically used when a conversation is being deleted or its history
        needs to be cleared completely.

        Args:
            conversation_id: UUID of the conversation whose messages are to be deleted

        Returns:
            The total number of messages deleted from the conversation

        Raises:
            RepositoryError: If the deletion operation fails
        """
        try:
            from sqlalchemy import delete

            # Construct a delete statement targeting all messages in the conversation
            stmt = delete(Message).where(
                Message.conversation_id == conversation_id)

            # Execute the delete statement asynchronously
            result = await self.db.execute(stmt)

            # Get the count of rows affected (messages deleted)
            deleted_count = result.rowcount

            logger.info(
                f"Deleted {deleted_count} messages from conversation: {conversation_id}")

            return deleted_count

        except Exception as e:
            # Rollback the transaction in case of failure to maintain DB consistency
            await self.db.rollback()

            logger.error(
                f"Error deleting messages from conversation {conversation_id}: {e}")
            raise RepositoryError(
                f"Failed to delete conversation messages") from e


# | Method Name                                | Purpose                                                                  | Input Parameters                                        | Output                                    | Notes                                                        |
# | ------------------------------------------ | ------------------------------------------------------------------------ | ------------------------------------------------------- | ----------------------------------------- | ------------------------------------------------------------ |
# | `create_message`                           | Create a new message in a conversation                                   | `conversation_id`, `content`, `role`                    | Created `Message` entity                  | Verifies conversation exists, updates conversation timestamp |
# | `bulk_create_messages`                     | Bulk create multiple messages for better performance                     | List of dicts with `conversation_id`, `content`, `role` | List of created `Message` entities        | Efficient batch insert with flush & refresh                  |
# | `get_conversation_messages`                | Retrieve messages for a conversation with pagination & order             | `conversation_id`, `offset`, `limit`, `order_desc`      | List of `Message` entities                | Order can be ascending or descending                         |
# | `get_messages_by_role`                     | Retrieve messages filtered by role within a conversation                 | `conversation_id`, `role`, `limit`                      | List of `Message` entities                | Returns oldest first                                         |
# | `get_latest_message`                       | Get the most recent message in a conversation                            | `conversation_id`                                       | Latest `Message` or None                  |                                                              |
# | `get_message_with_conversation`            | Get a message along with its conversation                                | `message_id`                                            | `Message` entity with loaded conversation | Useful for context                                           |
# | `search_messages`                          | Search messages by content with optional role filtering                  | `conversation_id`, `search_term`, `role`, `limit`       | List of matching `Message` entities       | Case-insensitive search                                      |
# | `get_conversation_history`                 | Get conversation messages in chronological order with optional filtering | `conversation_id`, `include_system`, `limit`            | List of `Message` entities                | Efficient pagination using subquery if limited               |
# | `get_recent_messages_across_conversations` | Get recent messages from all user conversations                          | `user_id`, `limit`                                      | List of recent `Message` entities         | Ordered descending by creation time                          |
# | `count_conversation_messages`              | Count total messages in a conversation                                   | `conversation_id`                                       | Integer count                             | Uses base repo count method                                  |
# | `count_messages_by_role`                   | Count messages of a specific role in a conversation                      | `conversation_id`, `role`                               | Integer count                             | Uses SQL COUNT                                               |
# | `get_user_message_count`                   | Count total messages across all conversations of a user                  | `user_id`                                               | Integer count                             | Joins conversation table to filter by user                   |
# | `update_message_content`                   | Update content of a specific message                                     | `message_id`, `content`                                 | Updated `Message` or None                 | Strips whitespace before update                              |
# | `delete_conversation_messages`             | Delete all messages in a conversation                                    | `conversation_id`                                       | Number of messages deleted                | Rolls back and logs on error                                 |
