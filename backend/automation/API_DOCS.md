# API Documentation

## Base URL
```
http://localhost:8000/api/
```

## Endpoints

### Rule Engines

#### List Rule Engines
```http
GET /rule-engines/
```

**Response:**
```json
{
  "count": 10,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "rule_name": "daily_audit",
      "is_active": true,
      "created_at": "2024-01-15T10:30:00Z"
    }
  ]
}
```

#### Get Rule Engine
```http
GET /rule-engines/{id}/
```

#### Create Rule Engine
```http
POST /rule-engines/
Content-Type: application/json

{
  "rule_name": "daily_audit",
  "is_active": true
}
```

#### Execute Rule Engine
```http
POST /rule-engines/{id}/execute/
Content-Type: application/json

{
  "manual": true
}
```

**Response:**
```json
{
  "status": "success",
  "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "rule_engine_id": 1,
  "message": "Rule execution started"
}
```

### Scheduled Jobs

#### List Scheduled Jobs
```http
GET /scheduled-jobs/
```

**Response:**
```json
{
  "count": 5,
  "results": [
    {
      "id": 1,
      "rule_name": "daily_audit",
      "rule_id": 1,
      "is_active": true,
      "interval": 1,
      "unit": "days",
      "schedule_config": {
        "type": "daily",
        "time": "08:00"
      },
      "created_at": "2024-01-15T10:30:00Z"
    }
  ]
}
```

#### Get Scheduled Job
```http
GET /scheduled-jobs/{id}/
```

#### Create Scheduled Job
```http
POST /scheduled-jobs/
Content-Type: application/json

{
  "rule_name": "daily_audit",
  "rule_id": 1,
  "is_active": true,
  "schedule_config": {
    "type": "daily",
    "time": "08:00"
  }
}
```

**Schedule Config Types:**

##### Interval
```json
{
  "type": "interval",
  "interval": 5,
  "unit": "minutes"
}
```

##### Daily
```json
{
  "type": "daily",
  "time": "08:00"
}
```

##### Weekly
```json
{
  "type": "weekly",
  "days": ["Monday", "Wednesday", "Friday"],
  "time": "08:00"
}
```

##### Once
```json
{
  "type": "once",
  "date": "2024-12-31",
  "time": "23:59"
}
```

#### Update Scheduled Job
```http
PATCH /scheduled-jobs/{id}/
Content-Type: application/json

{
  "is_active": false,
  "schedule_config": {
    "type": "daily",
    "time": "09:00"
  }
}
```

#### Delete Scheduled Job
```http
DELETE /scheduled-jobs/{id}/
```

### Celery Tasks

#### Get Task Status
```http
GET /celery-tasks/{task_id}/status/
```

**Response:**
```json
{
  "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "SUCCESS",
  "result": {
    "status": "success",
    "rule_engine_id": 1,
    "execution_log": [
      {
        "node": 1,
        "function": "validate_data",
        "result": true
      }
    ]
  }
}
```

### System

#### Get System Status
```http
GET /system/status/
```

**Response:**
```json
{
  "status": "healthy",
  "orchestrator_mode": true,
  "redis_connected": true,
  "database_connected": true,
  "celery_workers": 4,
  "active_tasks": 5,
  "scheduled_jobs": 3
}
```

#### Get Configuration
```http
GET /system/config/
```

**Response:**
```json
{
  "mode": "ORCHESTRATOR",
  "debug": false,
  "celery_broker": "redis://localhost:6379/0",
  "timezone": "UTC"
}
```

## Error Responses

### 400 Bad Request
```json
{
  "error": "Invalid request",
  "details": {
    "rule_name": ["This field is required."]
  }
}
```

### 404 Not Found
```json
{
  "error": "Not found",
  "detail": "Rule engine with id 999 not found"
}
```

### 500 Internal Server Error
```json
{
  "error": "Internal server error",
  "detail": "An unexpected error occurred"
}
```

## Authentication

Currently, no authentication is required. In production, implement:

```bash
# Add to requirements.txt
djangorestframework-simplejwt==5.3.0
```

Update `settings.py`:
```python
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
}
```

## Rate Limiting

Not currently implemented. Consider adding:

```bash
# Add to requirements.txt
djangorestframework==3.16.1
```

Update `settings.py`:
```python
REST_FRAMEWORK = {
    'DEFAULT_THROTTLE_CLASSES': (
        'rest_framework.throttling.AnonRateThrottle',
    ),
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour'
    }
}
```

## Examples

### Execute a Rule Engine
```bash
curl -X POST http://localhost:8000/api/rule-engines/1/execute/ \
  -H "Content-Type: application/json" \
  -d '{"manual": true}'
```

### Create a Daily Scheduled Job
```bash
curl -X POST http://localhost:8000/api/scheduled-jobs/ \
  -H "Content-Type: application/json" \
  -d '{
    "rule_name": "daily_sync",
    "rule_id": 1,
    "is_active": true,
    "schedule_config": {
      "type": "daily",
      "time": "08:00"
    }
  }'
```

### Get Task Status
```bash
curl http://localhost:8000/api/celery-tasks/{task_id}/status/
```

### List All Scheduled Jobs
```bash
curl http://localhost:8000/api/scheduled-jobs/
```

## Filtering & Pagination

### Pagination
```http
GET /rule-engines/?page=2&page_size=10
```

### Filtering
```http
GET /scheduled-jobs/?is_active=true&rule_name=audit
```

### Ordering
```http
GET /rule-engines/?ordering=-created_at
```

## Webhooks & Callbacks

Not currently implemented. Consider adding webhook support for:
- Task completion
- Scheduled job execution
- Error notifications

## WebSocket Support

Not currently implemented. Consider adding for:
- Real-time task status updates
- Live monitoring

## Version

Current API Version: 1.0

No versioning currently implemented. Consider:
- `/api/v1/` prefix for future compatibility
- `Accept` header versioning
