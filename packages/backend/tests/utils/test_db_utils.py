"""Tests for database utility context managers."""

import logging
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.utils.db_utils import handle_unique_violation


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.rollback = AsyncMock()
    return db


@pytest.fixture
def mock_logger():
    return MagicMock(spec=logging.Logger)


# ---------------------------------------------------------------------------
# handle_unique_violation
# ---------------------------------------------------------------------------

class TestHandleUniqueViolation:

    async def test_success_no_exception(self, mock_db):
        async with handle_unique_violation(mock_db, "Duplicate tag name", MagicMock()):
            pass

        mock_db.rollback.assert_not_called()

    async def test_integrity_error_rolls_back_and_raises_400(self, mock_db, mock_logger):
        with pytest.raises(HTTPException) as exc_info:
            async with handle_unique_violation(
                mock_db, "Tag with this name already exists", mock_logger,
                context={"user_id": "user-1"},
            ):
                raise IntegrityError("duplicate key", params=None, orig=None)

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Tag with this name already exists"
        mock_db.rollback.assert_called_once()
        mock_logger.warning.assert_called_once()

    async def test_integrity_error_without_context(self, mock_db, mock_logger):
        with pytest.raises(HTTPException) as exc_info:
            async with handle_unique_violation(
                mock_db, "Already exists", mock_logger,
            ):
                raise IntegrityError("duplicate key", params=None, orig=None)

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Already exists"
        mock_db.rollback.assert_called_once()
        mock_logger.warning.assert_called_once()

    async def test_other_exception_rolls_back_and_re_raises(self, mock_db, mock_logger):
        with pytest.raises(ValueError, match="something went wrong"):
            async with handle_unique_violation(
                mock_db, "Should not be used", mock_logger,
            ):
                raise ValueError("something went wrong")

        mock_db.rollback.assert_called_once()
