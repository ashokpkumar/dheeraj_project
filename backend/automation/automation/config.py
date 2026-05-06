"""
Configuration utilities for the automation app.
"""

import os
from typing import Optional


def is_orchestrator_mode() -> bool:
    """
    Check if the application is running in orchestrator mode.
    
    Returns:
        bool: True if IS_ORCHESTRATOR env var is set to True
    """
    return os.getenv('IS_ORCHESTRATOR', 'False').lower() in ('true', '1', 'yes')


def get_redis_url() -> str:
    """
    Get Redis connection URL from environment.
    
    Returns:
        str: Redis URL (default: redis://localhost:6379/0)
    """
    return os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')


def get_database_config() -> dict:
    """
    Get database configuration from environment variables.
    
    Returns:
        dict: Database configuration dictionary
    """
    return {
        'ENGINE': os.getenv('DB_ENGINE', 'mssql'),
        'NAME': os.getenv('DB_NAME', 'master'),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', '1433'),
        'USER': os.getenv('DB_USER', 'sa'),
        'PASSWORD': os.getenv('DB_PASSWORD', ''),
    }


def get_celery_config() -> dict:
    """
    Get Celery configuration from environment.
    
    Returns:
        dict: Celery configuration dictionary
    """
    return {
        'broker_url': get_redis_url(),
        'result_backend': os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0'),
        'orchestrator_mode': is_orchestrator_mode(),
    }


def log_startup_info() -> None:
    """Log startup information about the configured mode."""
    config = get_celery_config()
    mode = 'ORCHESTRATOR' if config['orchestrator_mode'] else 'WORKER'
    
    print("=" * 70)
    print(f"Application Mode: {mode}")
    print(f"Redis URL: {config['broker_url']}")
    print(f"Orchestrator Mode: {config['orchestrator_mode']}")
    print("=" * 70)
