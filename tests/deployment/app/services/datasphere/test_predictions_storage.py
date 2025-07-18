import os
import sqlite3
from unittest.mock import patch

import pandas as pd
import pytest

from deployment.app.services.datasphere_service import save_predictions_to_db
from tests.deployment.app.services.datasphere.conftest import verify_predictions_saved


def test_save_predictions_to_db(
    monkeypatch, mock_init_db, mock_get_db, temp_db, sample_predictions_data
):
    """Test saving predictions from CSV to database"""
    monkeypatch.setattr("deployment.app.services.datasphere_service.get_db_connection", mock_get_db)
    monkeypatch.setattr("deployment.app.db.schema.init_db", mock_init_db)
    # Настраиваем мок для использования тестовой БД
    conn = sqlite3.connect(temp_db["db_path"])
    conn.row_factory = sqlite3.Row
    mock_get_db.return_value = conn

    # Вызываем тестируемую функцию с прямым соединением
    # Временно печатаем параметры job для диагностики
    import json
    cursor = conn.cursor()
    cursor.execute("SELECT parameters FROM jobs WHERE job_id = ?", (temp_db["job_id"],))
    job_params_row = cursor.fetchone()
    print("DIAG JOB PARAMETERS:", job_params_row["parameters"])
    # Теперь вызываем функцию
    result = save_predictions_to_db(
        predictions_path=temp_db["predictions_path"],
        job_id=temp_db["job_id"],
        model_id=temp_db["model_id"],
        direct_db_connection=conn,
    )
    # Диагностика: смотрим, что реально в prediction_results
    cursor.execute("SELECT * FROM prediction_results WHERE job_id = ?", (temp_db["job_id"],))
    pred_result_row = cursor.fetchone()
    print("DIAG PREDICTION_RESULTS ROW:", pred_result_row)

    # Используем общую функцию проверки результатов
    verify_predictions_saved(conn, result, sample_predictions_data)
    conn.close()


def test_save_predictions_to_db_invalid_path(monkeypatch, mock_get_db, temp_db):
    """Test handling of invalid prediction file path"""
    monkeypatch.setattr("deployment.app.services.datasphere_service.get_db_connection", mock_get_db)
    conn = sqlite3.connect(temp_db["db_path"])
    conn.row_factory = sqlite3.Row
    mock_get_db.return_value = conn

    with pytest.raises(FileNotFoundError):
        save_predictions_to_db(
            predictions_path="/nonexistent/path/predictions.csv",
            job_id=temp_db["job_id"],
            model_id=temp_db["model_id"],
            direct_db_connection=conn,
        )
    conn.close()


def test_save_predictions_to_db_invalid_format(monkeypatch, mock_get_db, temp_db):
    """Test handling of invalid prediction file format"""
    monkeypatch.setattr("deployment.app.services.datasphere_service.get_db_connection", mock_get_db)
    conn = sqlite3.connect(temp_db["db_path"])
    conn.row_factory = sqlite3.Row
    mock_get_db.return_value = conn

    # Создаем файл с неправильным форматом
    invalid_path = os.path.join(temp_db["temp_dir_path"], "invalid.csv")
    with open(invalid_path, "w") as f:
        f.write("This is not a valid CSV file")

    with pytest.raises(ValueError):
        save_predictions_to_db(
            predictions_path=invalid_path,
            job_id=temp_db["job_id"],
            model_id=temp_db["model_id"],
            direct_db_connection=conn,
        )
    conn.close()


@patch("deployment.app.services.datasphere_service.get_db_connection")
def test_save_predictions_to_db_missing_columns(
    mock_get_db, temp_db, sample_predictions_data
):
    """Test handling of prediction file with missing required columns"""
    conn = sqlite3.connect(temp_db["db_path"])
    conn.row_factory = sqlite3.Row
    mock_get_db.return_value = conn

    # Создаем CSV с отсутствующими колонками квантилей
    missing_data = sample_predictions_data.copy()
    # Удаляем некоторые колонки
    del missing_data["0.05"]
    del missing_data["0.25"]

    # Создаем и сохраняем DataFrame
    missing_cols_path = os.path.join(temp_db["temp_dir_path"], "missing_cols.csv")
    pd.DataFrame(missing_data).to_csv(missing_cols_path, index=False)

    with pytest.raises(ValueError):
        save_predictions_to_db(
            predictions_path=missing_cols_path,
            job_id=temp_db["job_id"],
            model_id=temp_db["model_id"],
            direct_db_connection=conn,
        )
    conn.close()


@patch("deployment.app.services.datasphere_service.get_db_connection")
def test_save_predictions_to_db_db_connection_failure(mock_get_db, temp_db):
    """Test handling of database connection failure during predictions save"""
    # Simulate DB connection raising an OperationalError
    mock_get_db.side_effect = sqlite3.OperationalError("Database is unavailable")

    with pytest.raises(sqlite3.OperationalError):
        save_predictions_to_db(
            predictions_path=temp_db["predictions_path"],
            job_id=temp_db["job_id"],
            model_id=temp_db["model_id"],
        )
