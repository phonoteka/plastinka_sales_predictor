import sqlite3

import pytest

from deployment.app.db.database import (  # Added DatabaseError import
    DatabaseError,
    dict_factory,
    execute_query,
)
from deployment.app.db.schema import init_db  # Import init_db

# Use a dedicated in-memory database for these tests to avoid interference
TEST_DB_PATH = ":memory:"


@pytest.fixture(scope="function")
def db_conn():
    """Fixture to set up and tear down the in-memory database for each test."""
    # Directly connect to the in-memory database for the test
    conn = sqlite3.connect(TEST_DB_PATH)

    # Enable Foreign Key support
    conn.execute("PRAGMA foreign_keys = ON;")

    # Set dict_factory for this connection
    conn.row_factory = dict_factory  # Use dict_factory

    # Initialize schema using init_db
    init_db(connection=conn)

    # Removed: cursor = conn.cursor() # No longer needed here as init_db handles it
    # Removed: cursor.executescript(SCHEMA_SQL) # Redundant call as init_db already does this
    conn.commit()  # Commit changes made by init_db for this connection

    # Verify PRAGMA is ON
    cursor = conn.cursor()  # Re-initialize cursor for the assertion below
    cursor.execute("PRAGMA foreign_keys;")
    fk_status = cursor.fetchone()
    assert fk_status["foreign_keys"] == 1, (
        "Foreign keys should be ON for the test connection"
    )

    yield conn

    conn.close()


def test_foreign_key_enforcement_on_insert_jobs_history(db_conn):
    """
    Test that inserting into job_status_history fails if the job_id does not exist in jobs.
    """
    with pytest.raises(DatabaseError) as excinfo:
        execute_query(
            "INSERT INTO job_status_history (job_id, status, progress, status_message, updated_at) VALUES (?, ?, ?, ?, ?)",
            db_conn,
            (
                "non_existent_job_id",
                "running",
                50.0,
                "Processing...",
                "2023-01-01T12:00:00",
            ),
        )
    assert "foreign key constraint failed" in str(excinfo.value.original_error).lower()


def test_foreign_key_enforcement_on_insert_training_results_model(db_conn):
    """
    Test that inserting into training_results fails if the model_id does not exist in models.
    """
    # First, create a job and a parameter set, as training_results depends on them too
    job_id = "test_job_fk_model"
    execute_query(
        "INSERT INTO jobs (job_id, job_type, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        db_conn,
        (job_id, "training", "pending", "2023-01-01T00:00:00", "2023-01-01T00:00:00"),
    )

    config_id = "test_config_fk_model"
    execute_query(
        "INSERT INTO configs (config_id, config, created_at) VALUES (?, ?, ?)",
        db_conn,
        (config_id, "{}", "2023-01-01T00:00:00"),
    )

    with pytest.raises(DatabaseError) as excinfo:
        execute_query(
            "INSERT INTO training_results (result_id, job_id, model_id, config_id, metrics, duration) VALUES (?, ?, ?, ?, ?, ?)",
            db_conn,
            ("tr_res_1", job_id, "non_existent_model_id", config_id, "{}", 100),
        )
    assert (
        "foreign key constraint failed" in str(excinfo.value.original_error).lower()
        or "no such table: models" in str(excinfo.value.original_error).lower()
    )


def test_foreign_key_enforcement_on_insert_training_results_config(db_conn):
    """
    Test that inserting into training_results fails if the config_id does not exist in configs.
    """
    job_id = "test_job_fk_config"
    execute_query(
        "INSERT INTO jobs (job_id, job_type, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        db_conn,
        (job_id, "training", "pending", "2023-01-01T00:00:00", "2023-01-01T00:00:00"),
    )

    model_id = "test_model_fk_config"
    execute_query(
        "INSERT INTO models (model_id, job_id, model_path, created_at) VALUES (?, ?, ?, ?)",
        db_conn,
        (model_id, job_id, "/path/to/model", "2023-01-01T00:00:00"),
    )

    with pytest.raises(DatabaseError) as excinfo:
        execute_query(
            "INSERT INTO training_results (result_id, job_id, model_id, config_id, metrics, duration) VALUES (?, ?, ?, ?, ?, ?)",
            db_conn,
            ("tr_res_2", job_id, model_id, "non_existent_config_id", "{}", 100),
        )
    assert "foreign key constraint failed" in str(excinfo.value.original_error).lower()


def test_foreign_key_cascade_delete_jobs(db_conn):
    """
    Test that deleting a job cascades to delete related job_status_history entries.
    (Assuming ON DELETE CASCADE is set on the foreign key in schema - if not, this test would fail
     or need to be adapted to test restricted delete if that's the behavior).
    The current schema for job_status_history.job_id does NOT specify ON DELETE CASCADE.
    So, this test should verify that deleting a job with history entries is RESTRICTED.
    """
    job_id = "job_to_delete"

    # Create a job
    execute_query(
        "INSERT INTO jobs (job_id, job_type, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        db_conn,
        (job_id, "test_type", "pending", "2023-01-01T00:00:00", "2023-01-01T00:00:00"),
    )

    # Create a history entry for this job
    execute_query(
        "INSERT INTO job_status_history (job_id, status, progress, status_message, updated_at) VALUES (?, ?, ?, ?, ?)",
        db_conn,
        (job_id, "running", 50.0, "Processing...", "2023-01-01T12:00:00"),
    )

    # Attempt to delete the job
    with pytest.raises(DatabaseError) as excinfo:
        execute_query(
            "DELETE FROM jobs WHERE job_id = ?", db_conn, (job_id,)
        )
    assert "foreign key constraint failed" in str(excinfo.value.original_error).lower()

    # Verify job and history entry still exist
    job_entry = execute_query(
        "SELECT * FROM jobs WHERE job_id = ?", db_conn, (job_id,)
    )
    history_entry = execute_query(
        "SELECT * FROM job_status_history WHERE job_id = ?",
        db_conn,
        (job_id,),
        fetchall=True,
    )

    assert job_entry is not None
    assert len(history_entry) == 1


def test_successful_insert_with_valid_foreign_keys(db_conn):
    """
    Test that inserts are successful when foreign keys are valid.
    """
    job_id = "valid_job_id"
    execute_query(
        "INSERT INTO jobs (job_id, job_type, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        db_conn,
        (job_id, "test_type", "pending", "2023-01-01T00:00:00", "2023-01-01T00:00:00"),
    )

    # This should succeed
    execute_query(
        "INSERT INTO job_status_history (job_id, status, progress, status_message, updated_at) VALUES (?, ?, ?, ?, ?)",
        db_conn,
        (job_id, "completed", 100.0, "Done", "2023-01-01T13:00:00"),
    )

    history_entry = execute_query(
        "SELECT * FROM job_status_history WHERE job_id = ?",
        db_conn,
        (job_id,),
        fetchall=True,
    )
    assert len(history_entry) == 1
    assert history_entry[0]["status"] == "completed"
