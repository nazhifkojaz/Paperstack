"""Database error handling utilities.

Provides shared functions for consistent database error handling,
logging, and transaction cleanup across route handlers.
"""
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


@asynccontextmanager
async def handle_unique_violation(
    db: AsyncSession,
    detail_message: str,
    logger_instance: logging.Logger,
    context: Optional[dict] = None,
):
    """Handle IntegrityError from unique constraint violations.

    Yields control to the caller. If IntegrityError is raised during
    the yielded block, this context manager will:
    1. Rollback the database transaction
    2. Log the error with provided context
    3. Raise HTTPException with 400 status and detail_message

    Args:
        db: Database session to rollback on error
        detail_message: User-friendly error message for HTTP 400 response
        logger_instance: Logger instance for error tracking
        context: Optional dict with user_id, resource identifiers, etc.

    Raises:
        HTTPException: Always raises 400 with detail_message on IntegrityError

    Example:
        ```python
        async with handle_unique_violation(
            db, "Tag with this name already exists", logger, {"user_id": user.id}
        ):
            await db.commit()
        ```
    """
    try:
        yield
    except IntegrityError as exc:
        await db.rollback()
        # Log with context if provided
        if context:
            logger_instance.warning(
                "Unique constraint violation: %s. Context: %s. Error: %s",
                detail_message,
                context,
                exc,
            )
        else:
            logger_instance.warning(
                "Unique constraint violation: %s. Error: %s",
                detail_message,
                exc,
            )
        raise HTTPException(status_code=400, detail=detail_message)
    except Exception:
        # Rollback for any other exception too
        await db.rollback()
        raise


@asynccontextmanager
async def background_task_transaction(
    db: AsyncSession,
    operation_name: str,
    logger_instance: logging.Logger,
    conversation_id: Optional[str] = None,
):
    """Context manager for background task database operations with error logging.

    FastAPI BackgroundTasks swallow exceptions, so this context manager
    ensures errors are logged before the task completes. On any exception:
    1. Log the error with context (operation name, conversation_id)
    2. Rollback the transaction
    3. Re-raise (FastAPI BackgroundTasks will swallow it)

    Args:
        db: Database session
        operation_name: Description of operation (e.g., "save_assistant_message")
        logger_instance: Logger instance for error tracking
        conversation_id: Optional conversation ID for log context

    Example:
        ```python
        async with background_task_transaction(bg_db, "save_message", logger, conv_id):
            bg_db.add(msg)
            await bg_db.commit()
            logger.info("Message saved successfully")
        ```
    """
    try:
        yield
    except Exception as exc:
        if conversation_id:
            logger_instance.exception(
                "Background task '%s' failed for conversation %s: %s",
                operation_name,
                conversation_id,
                exc,
            )
        else:
            logger_instance.exception(
                "Background task '%s' failed: %s",
                operation_name,
                exc,
            )
        await db.rollback()
        raise
