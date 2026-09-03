# app/db/database.py
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import DATABASE_URL, ENVIRONMENT

_is_sqlite = DATABASE_URL.startswith("sqlite")

# Production: use connection pooling for PostgreSQL
# Dev: SQLite with WAL mode for better concurrency
_engine_kwargs = {
    "pool_pre_ping": True,
    "echo": False,
}

if _is_sqlite:
    _engine_kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
else:
    # PostgreSQL connection pool tuned for 25K concurrent users
    _engine_kwargs.update({
        "pool_size": 20,           # persistent connections per worker
        "max_overflow": 30,        # extra connections under burst
        "pool_timeout": 10,        # seconds to wait for a connection
        "pool_recycle": 1800,      # recycle connections every 30 min
        "pool_pre_ping": True,     # verify connections before use
    })

engine = create_engine(DATABASE_URL, **_engine_kwargs)

if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA cache_size=-64000")  # 64MB cache
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()