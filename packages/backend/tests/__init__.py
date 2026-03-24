# Test configuration for SQLite compatibility (optional)

import datetime
import uuid as uuid_module

from sqlalchemy import event
from sqlalchemy.engine import Engine
import sqlite3

# Register adapters for SQLite (only used if SQLite is chosen)
sqlite3.register_adapter(datetime.datetime, lambda x: x.isoformat())
sqlite3.register_adapter(uuid_module.UUID, lambda x: str(x))  # Store UUID as string


@event.listens_for(Engine, "connect", once=True)
def _setup_sqlite_functions(dbapi_conn, connection_record):
    """Add missing PostgreSQL functions for SQLite compatibility.

    This only applies to SQLite connections. PostgreSQL connections
    use the native functions.
    """
    # Only apply these patches for SQLite connections
    # Check if the connection is a SQLite connection
    if not hasattr(dbapi_conn, 'create_function'):
        # Not a SQLite connection (likely PostgreSQL), skip the patches
        return

    # Create a now() function that returns current timestamp as a string
    def _now():
        return datetime.datetime.now(datetime.timezone.utc).isoformat()

    # Create a gen_random_uuid() function for UUID generation
    def _gen_random_uuid():
        return str(uuid_module.uuid4())

    # Register now() function (name, num_params, func)
    dbapi_conn.create_function("now", 0, _now)
    dbapi_conn.create_function("gen_random_uuid", 0, _gen_random_uuid)
