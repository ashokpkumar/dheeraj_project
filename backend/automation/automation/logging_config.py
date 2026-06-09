"""
Logging configuration for the automation application.
"""

import os
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Create logs directory if it doesn't exist
# LOGS_DIR = Path(__file__).resolve().parent.parent / 'logs'
LOGS_DIR = Path(__file__).resolve().parent / 'logs'
LOGS_DIR.mkdir(exist_ok=True)

# Log file paths
API_LOG_FILE = LOGS_DIR / 'api.log'
TASK_LOG_FILE = LOGS_DIR / 'tasks.log'
EXECUTOR_LOG_FILE = LOGS_DIR / 'executor.log'
ERROR_LOG_FILE = LOGS_DIR / 'errors.log'
LOGGING_CONFIG = 'logging.config.dictConfig'
# Logging configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{levelname}] {asctime} {name} {funcName}:{lineno} - {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
        'simple': {
            'format': '[{levelname}] {asctime} {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'level': 'DEBUG',
            'formatter': 'simple',
            'stream': 'ext://sys.stdout',
        },
        'api_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'level': 'DEBUG',
            'formatter': 'verbose',
            'filename': str(API_LOG_FILE),
            'maxBytes': 10485760,  # 10MB
            'backupCount': 5,
        },
        'tasks_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'level': 'DEBUG',
            'formatter': 'verbose',
            'filename': str(TASK_LOG_FILE),
            'maxBytes': 10485760,  # 10MB
            'backupCount': 5,
        },
        'executor_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'level': 'DEBUG',
            'formatter': 'verbose',
            'filename': str(EXECUTOR_LOG_FILE),
            'maxBytes': 10485760,  # 10MB
            'backupCount': 5,
        },
        'error_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'level': 'ERROR',
            'formatter': 'verbose',
            'filename': str(ERROR_LOG_FILE),
            'maxBytes': 10485760,  # 10MB
            'backupCount': 10,
        },
    },
    'loggers': {
        'rule_engine.views': {
            'handlers': ['console', 'api_file', 'error_file'],
            'level': 'DEBUG',
            'propagate': True,
        },
        'rule_engine.tasks': {
            'handlers': ['console', 'tasks_file', 'error_file'],
            'level': 'DEBUG',
            'propagate': True,
        },
        'rule_engine.executor': {
            'handlers': ['console', 'executor_file', 'error_file'],
            'level': 'DEBUG',
            'propagate': True,
        },
        'django': {
            'handlers': ['console', 'error_file'],
            'level': 'INFO',
            'propagate': True,
        },
        'celery': {
            'handlers': ['console', 'tasks_file', 'error_file'],
            'level': 'INFO',
            'propagate': True,
        },
    },
    'root': {
        'handlers': ['console', 'error_file'],
        'level': 'INFO',
    },
}


def setup_logger(name):
    """
    Get or create a logger with the given name.
    
    Args:
        name: Logger name (typically __name__)
    
    Returns:
        logging.Logger: Configured logger instance
    """
    return logging.getLogger(name)
