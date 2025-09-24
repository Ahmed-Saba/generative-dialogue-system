"""
Conversation repository for handling conversation-specific database operations.

This module provides the ConversationRepository class which extends BaseRepository
with conversation-specific functionality like user-specific conversations,
message loading, and conversation management.
"""

from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
import logging

from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user import User
from .base_repository import BaseRepository, NotFoundError, RepositoryError

logger = logging.getLogger(__name__)


class ConversationRepository(BaseRepository[Conversation]):
    """
    Repository for Conversation entity operations.

    Inherits common CRUD methods from BaseRepository, and extends
    it with conversation-specific operations such as:
      - Retrieving conversations by user
      - Loading related messages
      - Fetching conversation history
      - Soft or hard deletions if needed

    This repository ensures business logic remains separate from
    ORM/database logic (encapsulation of persistence layer).
    """

    def __init__(self, db: AsyncSession):
        """
        Initialize the ConversationRepository with an async session.

        Args:
            db (AsyncSession): The SQLAlchemy asynchronous database session.
        """
        super().__init__(Conversation, db)  # Binds the base repository to the Conversation model

    # =================================================================================================================
    # Create Operations
    # =================================================================================================================

    async def create_conversation(
        self,
        user_id: UUID,
        title: str | None = None
    ) -> Conversation:
        """
        Create a new conversation associated with a given user.

        This method verifies the user exists before creating the conversation.
        An optional title can be provided for the conversation.

        Args:
            user_id (UUID): The ID of the user who owns the conversation.
            title (Optional[str]): Optional title for the conversation.

        Returns:
            Conversation: The newly created Conversation entity.

        Raises:
            NotFoundError: If the user with the given ID does not exist.
            RepositoryError: For other database-related errors during creation.
        """
        logger.info(f"Creating new conversation for user: {user_id}")

        # Verify user exists
        user_query = select(User.id).where(User.id == user_id)
        user_result = await self.db.execute(user_query)
        if user_result.scalar_one_or_none() is None:
            raise NotFoundError(f"User with ID {user_id} not found")

        return await self.create(
            user_id=user_id,
            title=title.strip() if title else None
        )

    # =================================================================================================================
    # Read Operations (Single Entity)
    # =================================================================================================================

    async def get_user_conversation(
        self,
        user_id: UUID,
        conversation_id: UUID
    ) -> Conversation | None:
        """
        Retrieve a conversation that belongs to a specific user.

        This method enforces user-level ownership by checking that both the
        conversation ID and user ID match — preventing users from accessing
        conversations they do not own (important for security and isolation).

        Args:
            user_id (UUID): ID of the user who owns the conversation
            conversation_id (UUID): ID of the conversation to retrieve

        Returns:
            Optional[Conversation]: The conversation if it exists and belongs 
            to the user, otherwise None.

        Raises:
            RepositoryError: If a database error occurs during the operation.
        """
        try:
            # Build a query that ensures:
            # - The conversation ID matches
            # - The conversation belongs to the specified user
            query = select(Conversation).where(
                and_(
                    Conversation.id == conversation_id,
                    Conversation.user_id == user_id
                )
            )

            # Execute the query asynchronously
            result = await self.db.execute(query)

            # scalar_one_or_none() will return:
            # - A single Conversation object if found
            # - None if no match
            conversation = result.scalar_one_or_none()

            # Log outcome for audit/debugging
            if conversation:
                logger.debug(
                    f"Retrieved user conversation: {conversation_id} for user: {user_id}"
                )
            else:
                logger.debug(
                    f"No conversation {conversation_id} found for user: {user_id}"
                )

            return conversation

        except Exception as e:
            # Roll back not needed here since it's a read, but log and raise a consistent error
            logger.error(
                f"Error retrieving user conversation {conversation_id} for user {user_id}: {e}"
            )
            raise RepositoryError(
                "Failed to retrieve user conversation") from e

        # Why This Method Matters
        # | Feature                           | Benefit                                                      |
        # | --------------------------------- | ------------------------------------------------------------ |
        # | `Conversation.user_id == user_id` | Enforces ownership (auth logic at DB level)                  |
        # | `scalar_one_or_none()`            | Guarantees only one result or `None` (safe for primary keys) |
        # | Logs                              | Traceable and auditable behavior                             |
        # | Exception handling                | Clean, abstracted error management                           |

        # Optional Enhancements
        #   - Optional eager loading: Add a `load_messages: bool = False` flag to also fetch `.messages` with `selectinload` when needed.
        #   - Strict error variant: You could add a `get_user_conversation_or_raise()` that raises NotFoundError if not found (just like `get_by_id_or_raise()` in the base repo).

    async def get_by_user(
        self,
        user_id: UUID,
        offset: int = 0,
        limit: int = 50,
        load_messages: bool = False
    ) -> list[Conversation]:
        """
        Retrieve a paginated list of conversations for a specific user.

        Optionally loads messages for each conversation.

        Args:
            user_id (UUID): The ID of the user whose conversations to fetch.
            offset (int): Number of conversations to skip (for pagination).
            limit (int): Maximum number of conversations to return.
            load_messages (bool): If True, eagerly loads messages for each conversation.

        Returns:
            list[Conversation]: Conversations ordered by most recently updated first.

        Raises:
            RepositoryError: If database query fails.
        """
        try:
            # Build the base query to select conversations filtered by user_id
            query = (
                select(Conversation)  # Select Conversation entities
                # Filter by the given user_id
                .where(Conversation.user_id == user_id)
                # Order by updated_at descending (most recent first)
                .order_by(Conversation.updated_at.desc())
                .offset(offset)  # Skip a number of conversations (pagination)
                .limit(limit)  # Limit the number of conversations returned
            )

            # If load_messages is True, add an option to eagerly load the related messages to avoid lazy loading
            if load_messages:
                query = query.options(selectinload(Conversation.messages))

            # Execute the query asynchronously
            result = await self.db.execute(query)

            # Extract the list of Conversation objects from the result
            conversations = result.scalars().all()

            # Log the number of conversations retrieved for debugging
            logger.debug(
                f"Retrieved {len(conversations)} conversations for user: {user_id}")

            # Return the list of conversations
            return list(conversations)

        except Exception as e:
            # Log any exceptions that occur during the query execution
            logger.error(
                f"Error retrieving conversations for user {user_id}: {e}")

            # Raise a custom repository error to be handled by upper layers
            raise RepositoryError(
                f"Failed to retrieve user conversations") from e

    async def get_recent_conversations(
        self,
        user_id: UUID,
        limit: int = 10
    ) -> list[Conversation]:
        """
        Retrieve the most recently updated conversations for a specific user.

        This is commonly used to show recent activity (e.g. in a sidebar or dashboard),
        and ensures that conversations are sorted by `updated_at` in descending order.

        Args:
            user_id (UUID): The ID of the user.
            limit (int): Maximum number of conversations to return. Defaults to 10.

        Returns:
            list[Conversation]: A list of recent Conversation entities for the user.

        Raises:
            RepositoryError: If the database query fails unexpectedly.
        """
        try:
            # Build the query with filtering and sorting
            query = (
                select(Conversation)
                .where(Conversation.user_id == user_id)
                # Sort by recent updates
                .order_by(Conversation.updated_at.desc())
                .limit(limit)
            )

            result = await self.db.execute(query)
            conversations = result.scalars().all()

            logger.debug(
                f"Retrieved {len(conversations)} recent conversations for user: {user_id}"
            )
            return list(conversations)

        except Exception as e:
            logger.error(
                f"Error retrieving recent conversations for user {user_id}: {e}"
            )
            raise RepositoryError(
                "Failed to retrieve recent conversations") from e

        # Tip: Why Use `updated_at` for Recency?
        #   Using `updated_at` instead of `created_at` means conversations that recently had a new message or title
        #   change will appear first — which is the behavior users expect in chat interfaces or dashboards.

    async def search_user_conversations(
        self,
        user_id: UUID,
        search_term: str,
        offset: int = 0,
        limit: int = 50
    ) -> list[Conversation]:
        """
        Search conversations by title for a specific user.

        This method performs a case-insensitive search using `ILIKE` to match 
        conversation titles that contain the search term, while ensuring the 
        results are restricted to the given user.

        Args:
            user_id (UUID): ID of the user who owns the conversations.
            search_term (str): Keyword or partial string to search within titles.
            offset (int): Number of results to skip (for pagination).
            limit (int): Maximum number of results to return.

        Returns:
            list[Conversation]: List of matching conversations.

        Raises:
            RepositoryError: If a database error occurs.
        """
        try:
            # Use wildcard pattern for partial match in SQL (e.g. '%term%')
            search_pattern = f"%{search_term.strip()}%"

            # Build the query:
            # - Restrict to conversations owned by the user
            # - Title must match the search term using ILIKE (case-insensitive)
            # - Sort by last updated (most recent first)
            # - Apply pagination with offset & limit
            query = (
                select(Conversation)
                .where(
                    and_(
                        Conversation.user_id == user_id,
                        # Case-insensitive LIKE
                        Conversation.title.ilike(search_pattern)
                    )
                )
                .order_by(Conversation.updated_at.desc())
                .offset(offset)
                .limit(limit)
            )

            result = await self.db.execute(query)
            conversations = result.scalars().all()

            logger.debug(
                f"Found {len(conversations)} conversations for user {user_id} matching: '{search_term}'"
            )
            return list(conversations)

        except Exception as e:
            logger.error(
                f"Error searching conversations for user {user_id} with term '{search_term}': {e}"
            )
            raise RepositoryError("Failed to search user conversations") from e

        # Explanation of Key Logic
        # | Part                                        | Purpose                                                                               |
        # | ------------------------------------------- | ------------------------------------------------------------------------------------- |
        # | `Conversation.title.ilike(...)`             | Case-insensitive partial matching of conversation titles (uses `%term%` SQL pattern). |
        # | `and_(...)`                                 | Ensures both `user_id` **and** title match are required to return a result.           |
        # | `.order_by(Conversation.updated_at.desc())` | Prioritizes most recently active conversations.                                       |
        # | `.offset(...) / .limit(...)`                | Enables pagination.                                                                   |

        # Example Use Case:
        # If a user named "Alice" has 100 conversations and searches for "meeting", this method returns
        # up to 50 of her conversations where the title contains the word "meeting", sorted from newest to oldest.

    async def get_conversations_with_message_count(
        self,
        user_id: UUID,
        offset: int = 0,
        limit: int = 50
    ) -> list[tuple[Conversation, int]]:
        """
        Get conversations for a user along with the number of messages in each.

        This method is ideal for listing conversations in a UI, showing the total
        number of messages without loading each message (efficient aggregation).

        Args:
            user_id (UUID): ID of the user who owns the conversations.
            offset (int): Number of results to skip (pagination).
            limit (int): Max number of results to return.

        Returns:
            List[Tuple[Conversation, int]]: Each item contains the conversation and its message count.

        Raises:
            RepositoryError: If the database operation fails.
        """
        try:
            from sqlalchemy import func

            # Build query to:
            # - Select each conversation for the user
            # - LEFT JOIN messages to include conversations with 0 messages
            # - Count messages per conversation using SQL aggregate function
            # - Group by conversation ID to ensure count is per-conversation
            # - Sort by latest activity (updated_at)
            query = (
                select(
                    Conversation,
                    # Aggregate count per conversation
                    func.count(Message.id).label("message_count")
                )
                # Include conversations with no messages
                .outerjoin(Message, Conversation.id == Message.conversation_id)
                .where(Conversation.user_id == user_id)
                .group_by(Conversation.id)
                .order_by(Conversation.updated_at.desc())
                .offset(offset)
                .limit(limit)
            )

            # Execute and retrieve all rows
            result = await self.db.execute(query)
            rows = result.all()

            # Unpack each row into (Conversation, message_count)
            conversations_with_counts = [(row[0], row[1]) for row in rows]

            logger.debug(
                f"Retrieved {len(conversations_with_counts)} conversations with counts for user: {user_id}")
            return conversations_with_counts

        except Exception as e:
            logger.error(
                f"Error retrieving conversations with message counts for user {user_id}: {e}")
            raise RepositoryError(
                "Failed to retrieve conversations with message counts") from e

        # Explanation of Key SQLAlchemy Concepts
        # | Concept                                     | What It Does                                                                  |
        # | ------------------------------------------- | ----------------------------------------------------------------------------- |
        # | `.outerjoin(...)`                           | Ensures conversations with **no messages** are still included with count = 0. |
        # | `func.count(Message.id)`                    | SQL aggregate function that counts number of messages per conversation.       |
        # | `.group_by(Conversation.id)`                | Necessary when using aggregation to group results by each conversation.       |
        # | `.label('message_count')`                   | Aliases the count result so you can access it with `row[1]`.                  |
        # | `.order_by(Conversation.updated_at.desc())` | Sorts so the most recently updated conversations come first.                  |

        # Tip:
        # This pattern is extremely useful when building a dashboard or inbox-style view where you need lightweight
        # metadata (e.g., "5 messages") without loading all the message objects.

    async def get_empty_conversations(
        self,
        user_id: UUID,
        limit: int = 50
    ) -> list[Conversation]:
        """
        Retrieve conversations for a specific user that contain no messages.

        This method is particularly useful for maintenance tasks such as
        identifying and potentially cleaning up stale or unused conversations.

        Args:
            user_id (UUID): ID of the user who owns the conversations.
            limit (int): Maximum number of conversations to return.

        Returns:
            list[Conversation]: Conversations with zero messages.

        Raises:
            RepositoryError: If the database operation fails.
        """
        try:
            # Build a query to:
            # - Select conversations belonging to the user
            # - LEFT OUTER JOIN messages to include all conversations even if they have no messages
            # - Filter conversations where Message.id is NULL (i.e., no messages exist)
            # - Order by creation date descending to get newest empty conversations first
            query = (
                select(Conversation)
                .outerjoin(Message, Conversation.id == Message.conversation_id)
                .where(
                    and_(
                        Conversation.user_id == user_id,
                        # This condition filters to conversations with no messages
                        Message.id.is_(None)
                    )
                )
                .order_by(Conversation.created_at.desc())
                .limit(limit)
            )

            # Execute the query and fetch all matching Conversation entities
            result = await self.db.execute(query)
            conversations = result.scalars().all()

            logger.debug(
                f"Found {len(conversations)} empty conversations for user: {user_id}")
            return list(conversations)

        except Exception as e:
            logger.error(
                f"Error retrieving empty conversations for user {user_id}: {e}")
            raise RepositoryError(
                "Failed to retrieve empty conversations") from e

        # Explanation of Key Concepts:
        #   - `.outerjoin(...)`: Performs a LEFT OUTER JOIN so conversations without any messages are included in the results.
        #   - `Message.id.is_(None)`: Filters for conversations where no related message rows exist (NULL in SQL).
        #   - `.order_by(Conversation.created_at.desc())`: Sorts results to show newest empty conversations first, which is often useful for cleanup or review.
        #   - `.limit(limit)`: Limits the number of results to control load and pagination.

    async def get_with_messages(self, conversation_id: UUID) -> Conversation | None:
        """
        Retrieve a conversation along with all its associated messages.

        Args:
            conversation_id (UUID): The unique identifier of the conversation.

        Returns:
            Optional[Conversation]: The conversation with messages eagerly loaded,
            or None if no conversation matches the given ID.

        Raises:
            RepositoryError: If there is an error during the database operation.
        """
        try:
            # Construct the query to select a conversation by its ID
            # Use selectinload to eagerly load related messages in one query (avoiding lazy loading)
            query = (
                select(Conversation)
                # Filter by conversation ID
                .where(Conversation.id == conversation_id)
                # Eagerly load messages
                .options(selectinload(Conversation.messages))
            )

            result = await self.db.execute(query)
            conversation = result.scalar_one_or_none()

            if conversation:
                logger.debug(
                    f"Retrieved conversation with messages: {conversation_id}")
            else:
                logger.debug(
                    f"No conversation found with ID: {conversation_id}")

            return conversation
        except Exception as e:
            logger.error(
                f"Error retrieving conversation with messages {conversation_id}: {e}")
            raise RepositoryError(
                f"Failed to retrieve conversation with messages") from e

    async def get_with_user_and_messages(self, conversation_id: UUID) -> Conversation | None:
        """
        Retrieve a conversation with its associated user and messages eagerly loaded.

        Args:
            conversation_id (UUID): The unique identifier of the conversation.

        Returns:
            Optional[Conversation]: The conversation including user and messages,
            or None if no conversation matches the given ID.

        Raises:
            RepositoryError: If there is an error during the database operation.
        """
        try:
            # Build a query to select a Conversation by its ID
            # Use selectinload to eagerly load related user and messages to avoid lazy loading
            query = (
                select(Conversation)
                # Filter by conversation ID
                .where(Conversation.id == conversation_id)
                .options(
                    # Eagerly load the related user entity
                    selectinload(Conversation.user),
                    # Eagerly load all related messages
                    selectinload(Conversation.messages)
                )
            )

            result = await self.db.execute(query)
            conversation = result.scalar_one_or_none()

            if conversation:
                logger.debug(
                    f"Retrieved conversation with user and messages: {conversation_id}")
            else:
                logger.debug(
                    f"No conversation found with ID: {conversation_id}")

            return conversation
        except Exception as e:
            logger.error(
                f"Error retrieving conversation with user and messages {conversation_id}: {e}")
            raise RepositoryError(
                f"Failed to retrieve conversation with relationships") from e

    # =================================================================================================================
    # Update Operations
    # =================================================================================================================

    async def update_conversation_timestamp(self, conversation_id: UUID) -> Conversation | None:
        """
        Update the `updated_at` timestamp of a conversation to the current time.

        This is typically used to "bump" the conversation's last updated time,
        for example, when a new message is added, so it appears at the top
        of recent conversation lists.

        Args:
            conversation_id (UUID): The ID of the conversation to update.

        Returns:
            Optional[Conversation]: The updated Conversation instance if found,
                                   otherwise None.
        """
        logger.debug(f"Updating timestamp for conversation: {conversation_id}")
        from sqlalchemy import func

        # Update conversation's updated_at field to the current database time
        return await self.update(conversation_id, updated_at=func.now())

    async def update_title(self, conversation_id: UUID, title: str) -> Conversation | None:
        """
        Update the title of an existing conversation.

        Args:
            conversation_id (UUID): The unique identifier of the conversation to update.
            title (str): The new title to set for the conversation.

        Returns:
            Optional[Conversation]: The updated Conversation instance if found,
            otherwise None.
        """
        # Log the update operation for tracking purposes
        logger.info(f"Updating title for conversation: {conversation_id}")

        # Call the update method of the base repository to update the title
        return await self.update(conversation_id, title=title.strip())

    # =================================================================================================================
    # Delete Operations
    # =================================================================================================================

    async def delete_user_conversation(
        self,
        user_id: UUID,
        conversation_id: UUID
    ) -> bool:
        """
        Securely delete a conversation that belongs to a specific user.

        This method ensures that only the owner of a conversation can delete it.
        It's designed to enforce authorization at the data access level — an
        important safeguard in multi-user environments.

        Args:
            user_id (UUID): The ID of the user attempting to delete the conversation.
            conversation_id (UUID): The ID of the conversation to delete.

        Returns:
            bool: 
                - True if the conversation was successfully deleted.
                - False if the conversation does not exist or does not belong to the user.

        Raises:
            RepositoryError: If an unexpected database error occurs.
        """
        try:
            # Step 1: Confirm that the conversation exists and belongs to the user
            conversation = await self.get_user_conversation(user_id, conversation_id)
            if not conversation:
                logger.warning(
                    f"Conversation {conversation_id} not found or does not belong to user {user_id}"
                )
                return False  # Avoid unauthorized deletions

            # Step 2: Perform the actual deletion using the base repository method (cascade will handle messages)
            success = await self.delete(conversation_id)

            if success:
                logger.info(
                    f"Successfully deleted conversation {conversation_id} for user {user_id}"
                )

            return success

        except Exception as e:
            # Step 3: Log and raise a RepositoryError for unified error handling
            logger.error(
                f"Error deleting conversation {conversation_id} for user {user_id}: {e}"
            )
            raise RepositoryError("Failed to delete user conversation") from e

        # Why This Design Is Strong
        # | Feature                                                                | Benefit                                                       |
        # | ---------------------------------------------------------------------- | ------------------------------------------------------------- |
        # | Ownership check via `get_user_conversation`                            | Prevents unauthorized deletion                                |
        # | Cascade behavior via `relationship(..., cascade="all, delete-orphan")` | Automatically deletes messages when a conversation is deleted |
        # | Clear return value (`True` or `False`)                                 | Easy to handle in calling layer (e.g. services or API)        |
        # | Centralized logging                                                    | Useful for audit trails and debugging                         |
        # | Exception wrapping                                                     | Keeps repository-layer errors consistent and predictable      |

        # Suggested Follow-Up Enhancements
        #   - Soft deletion (optional): If you need to retain deleted conversations for audit/logs, consider a is_deleted: bool column instead of hard deletion.
        #   - Admin override: Later, you could allow privileged roles to delete any conversation by bypassing the ownership check.

    async def bulk_delete_conversations(
        self,
        user_id: UUID,
        conversation_ids: list[UUID]
    ) -> int:
        """
        Bulk delete multiple conversations owned by a specific user.

        This method first verifies that all provided conversation IDs belong to the user,
        preventing accidental deletion of conversations owned by others. Only valid
        conversations associated with the user are deleted.

        Args:
            user_id (UUID): The ID of the user who owns the conversations.
            conversation_ids (List[UUID]): List of conversation UUIDs to delete.

        Returns:
            int: Number of conversations successfully deleted.

        Raises:
            RepositoryError: If the deletion process encounters an error.
        """
        try:
            if not conversation_ids:
                # No conversations specified for deletion
                return 0

            # Verify ownership: select IDs of conversations belonging to the user
            query = select(Conversation.id).where(
                and_(
                    Conversation.user_id == user_id,
                    Conversation.id.in_(conversation_ids)
                )
            )
            result = await self.db.execute(query)
            valid_ids = [row[0] for row in result.all()]

            if not valid_ids:
                logger.warning(
                    f"No valid conversations found for user {user_id} in provided IDs")
                return 0

            # Perform bulk delete on conversations validated to belong to the user
            from sqlalchemy import delete
            stmt = delete(Conversation).where(Conversation.id.in_(valid_ids))
            result = await self.db.execute(stmt)
            deleted_count = result.rowcount

            logger.info(
                f"Bulk deleted {deleted_count} conversations for user {user_id}")
            return deleted_count

        except Exception as e:
            # Rollback transaction on error to maintain DB integrity
            await self.db.rollback()
            logger.error(
                f"Error bulk deleting conversations for user {user_id}: {e}")
            raise RepositoryError("Failed to bulk delete conversations") from e

        # Key Notes:
        #   - Validates ownership before deletion for security.
        #   - Uses `select` + `in_()` to filter conversations by user.
        #   - Performs a bulk delete with SQLAlchemy’s `delete()` construct.
        #   - Rolls back on exception to avoid partial state changes.

    # =================================================================================================================
    # Aggregation / Count Operations
    # =================================================================================================================

    async def count_user_conversations(self, user_id: UUID) -> int:
        """
        Count how many conversations are owned by a specific user.

        This uses the generic `count` method from the base repository
        with a filter on `user_id`.

        Args:
            user_id (UUID): The ID of the user.

        Returns:
            int: Number of conversations that belong to the user.
        """
        return await self.count(user_id=user_id)

        # ✅ This is a clean one-liner method leveraging the generic count logic from BaseRepository.


# | **Method Name**                        | **Purpose**                                      | **Key Arguments**                             | **Returns**                                    | **Notes**                          |
# | -------------------------------------- | ------------------------------------------------ | --------------------------------------------- | ---------------------------------------------- | ---------------------------------- |
# | `create_conversation`                  | Create a new conversation for a user             | `user_id`, `title` (optional)                 | Created `Conversation` entity                  | Validates user existence           |
# | `get_user_conversation`                | Get a specific conversation for a user           | `user_id`, `conversation_id`                  | `Conversation` or `None`                       | Ensures ownership                  |
# | `get_by_user`                          | Get paginated conversations for a user           | `user_id`, `offset`, `limit`, `load_messages` | List of `Conversation` entities                | Optional message loading           |
# | `get_recent_conversations`             | Get most recent conversations for a user         | `user_id`, `limit`                            | List of `Conversation` entities                | Ordered by `updated_at` descending |
# | `search_user_conversations`            | Search conversations by title for a user         | `user_id`, `search_term`, `offset`, `limit`   | List of matching `Conversation` entities       | Case-insensitive search            |
# | `get_conversations_with_message_count` | Get conversations with their message counts      | `user_id`, `offset`, `limit`                  | List of tuples `(Conversation, message_count)` | Uses SQL aggregation               |
# | `get_empty_conversations`              | Get conversations with no messages               | `user_id`, `limit`                            | List of empty `Conversation` entities          | Useful for cleanup                 |
# | `get_with_messages`                    | Get a conversation with all messages loaded      | `conversation_id`                             | `Conversation` or `None`                       | Eager loads messages               |
# | `get_with_user_and_messages`           | Get a conversation with user and messages loaded | `conversation_id`                             | `Conversation` or `None`                       | Eager loads user and messages      |
# | `update_title`                         | Update conversation title                        | `conversation_id`, `title`                    | Updated `Conversation` or `None`               | Strips title whitespace            |
# | `update_conversation_timestamp`        | Update the `updated_at` timestamp                | `conversation_id`                             | Updated `Conversation` or `None`               | For bumping recency                |
# | `delete_user_conversation`             | Delete a conversation owned by a user            | `user_id`, `conversation_id`                  | `True` if deleted, `False` otherwise           | Checks ownership before deletion   |
# | `bulk_delete_conversations`            | Bulk delete multiple user conversations          | `user_id`, list of `conversation_ids`         | Number of conversations deleted                | Validates ownership on all IDs     |
# | `count_user_conversations`             | Count the total conversations owned by a user    | `user_id`                                     | Integer count                                  | Simple count                       |
