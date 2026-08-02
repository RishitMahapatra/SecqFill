"""
Thin DB connection layer. No ORM on purpose — this app is a handful of
tables with simple access patterns, and raw SQL keeps the pgvector queries
(cosine distance search) transparent instead of hidden behind ORM magic.
"""
import os
from contextlib import contextmanager

import psycopg
from dotenv import load_dotenv
from pgvector.psycopg import register_vector

load_dotenv()

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://localhost:5432/secqfill"
)


@contextmanager
def get_db():
    conn = psycopg.connect(DATABASE_URL, autocommit=True)
    register_vector(conn)
    try:
        yield conn
    finally:
        conn.close()
