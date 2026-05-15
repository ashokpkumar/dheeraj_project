"""
Emulator Agent (Windows-side)
=============================

Manages the pool of available emulators and handles worker claims.

Each worker claims a slot of emulators on startup (e.g., 4 emulators).
The agent tracks what's claimed and what's available.
Workers send heartbeats to keep their claim alive (TTL-based).
If a worker dies, its claim expires and those emulators become available again.

API Endpoints:
  POST /emulators/claim           - Worker claims N emulators on startup
  POST /emulators/release/{id}    - Worker releases its claim on shutdown
  POST /emulators/heartbeat/{id}  - Worker renews its claim (every 20s)
  GET  /emulators/status          - Show all claimed/available emulators
  POST /emulators/scrape          - Process claims via emulator
  GET  /health                    - Health check
"""

from flask import Flask, jsonify, request
import redis
import uuid
import os
import logging
from datetime import datetime

# ─────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────

app = Flask(__name__)

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Redis for worker registry
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
REDIS_DB = int(os.getenv('REDIS_DB', 0))

try:
    r = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        decode_responses=True
    )
    r.ping()
    logger.info(f"✓ Connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
except Exception as e:
    logger.error(f"✗ Failed to connect to Redis: {e}")
    raise

# Emulator Configuration
TOTAL_EMULATORS = int(os.getenv('TOTAL_EMULATORS', 16))
EMULATORS_PER_CLAIM = int(os.getenv('EMULATORS_PER_CLAIM', 4))
CLAIM_TTL = int(os.getenv('CLAIM_TTL', 60))  # seconds before claim expires

logger.info(f"Configuration: TOTAL_EMULATORS={TOTAL_EMULATORS}, "
            f"EMULATORS_PER_CLAIM={EMULATORS_PER_CLAIM}, CLAIM_TTL={CLAIM_TTL}s")

# ─────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────

def get_all_emulators():
    """Return list of all available emulators with their ports."""
    return [
        {"id": i, "port": 5550 + i}
        for i in range(1, TOTAL_EMULATORS + 1)
    ]


def get_claimed_emulators():
    """Return set of emulator IDs currently claimed by workers."""
    claimed = set()
    for key in r.scan_iter("emulator:claim:*"):
        emulator_ids = r.smembers(key)
        if emulator_ids:
            claimed.update(emulator_ids)
    return claimed


def get_available_emulators(count=None):
    """Return list of available (unclaimed) emulators."""
    if count is None:
        count = EMULATORS_PER_CLAIM

    claimed = get_claimed_emulators()
    available = [e for e in get_all_emulators() if str(e["id"]) not in claimed]
    return available[:count]


# ─────────────────────────────────────────────────────────────
# API Endpoints
# ─────────────────────────────────────────────────────────────

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    try:
        r.ping()
        return jsonify({
            'status': 'healthy',
            'service': 'emulator_agent',
            'redis': 'connected',
            'timestamp': datetime.utcnow().isoformat()
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'service': 'emulator_agent',
            'redis': 'disconnected',
            'error': str(e)
        }), 503


@app.route('/emulators/status', methods=['GET'])
def emulator_status():
    """Show all emulators and their status (claimed/available)."""
    all_emulators = get_all_emulators()
    claimed = get_claimed_emulators()

    status = {
        'total': len(all_emulators),
        'claimed': len(claimed),
        'available': len(all_emulators) - len(claimed),
        'emulators': [
            {
                **e,
                'status': 'claimed' if str(e['id']) in claimed else 'available'
            }
            for e in all_emulators
        ],
        'worker_claims': {}
    }

    # Show which worker claimed which emulators
    for key in r.scan_iter("emulator:claim:*"):
        worker_id = key.split(':')[-1]
        emulator_ids = [int(x) for x in r.smembers(key)]
        ttl = r.ttl(key)
        status['worker_claims'][worker_id] = {
            'emulators': sorted(emulator_ids),
            'ttl': ttl
        }

    return jsonify(status), 200


@app.route('/emulators/claim', methods=['POST'])
def claim_emulators():
    """
    Worker calls this on startup to claim a slot of emulators.

    Request JSON:
    {
        "count": 4,                    # optional, defaults to EMULATORS_PER_CLAIM
        "hostname": "worker-node-1"    # optional, for logging
    }

    Response:
    {
        "worker_id": "abc123",
        "emulators": [
            {"id": 1, "port": 5551},
            {"id": 2, "port": 5552},
            ...
        ]
    }
    """
    data = request.get_json() or {}
    count = data.get('count', EMULATORS_PER_CLAIM)
    hostname = data.get('hostname', 'unknown')

    logger.info(f"Claim request from {hostname}: {count} emulators")

    # Get available emulators
    available = get_available_emulators(count)

    if len(available) < count:
        logger.warning(
            f"Not enough emulators for {hostname}. "
            f"Requested: {count}, Available: {len(available)}"
        )
        return jsonify({
            'error': 'not_enough_emulators',
            'requested': count,
            'available': len(available)
        }), 409

    # Generate worker ID
    worker_id = str(uuid.uuid4())[:8]

    # Store claim in Redis with TTL
    emulator_ids = [str(e['id']) for e in available]
    claim_key = f"emulator:claim:{worker_id}"
    r.sadd(claim_key, *emulator_ids)
    r.expire(claim_key, CLAIM_TTL)

    # Register worker metadata
    worker_key = f"worker:metadata:{worker_id}"
    r.hset(worker_key, mapping={
        'hostname': hostname,
        'emulator_count': len(available),
        'emulator_ids': ','.join(emulator_ids),
        'claimed_at': datetime.utcnow().isoformat()
    })
    r.expire(worker_key, CLAIM_TTL)

    logger.info(
        f"✓ Claimed for {worker_id} ({hostname}): "
        f"emulators {emulator_ids}"
    )

    return jsonify({
        'worker_id': worker_id,
        'emulators': available,
        'ttl': CLAIM_TTL
    }), 200


@app.route('/emulators/heartbeat/<worker_id>', methods=['POST'])
def heartbeat(worker_id):
    """
    Worker sends this every ~20 seconds to keep its claim alive.
    Renews the TTL on the Redis key.
    """
    claim_key = f"emulator:claim:{worker_id}"
    metadata_key = f"worker:metadata:{worker_id}"

    if not r.exists(claim_key):
        logger.warning(f"Heartbeat from unknown worker {worker_id}")
        return jsonify({'error': 'worker_not_found'}), 404

    # Renew TTL
    r.expire(claim_key, CLAIM_TTL)
    r.expire(metadata_key, CLAIM_TTL)

    return jsonify({
        'status': 'ok',
        'worker_id': worker_id,
        'ttl': CLAIM_TTL
    }), 200


@app.route('/emulators/release/<worker_id>', methods=['POST'])
def release_emulators(worker_id):
    """
    Worker calls this on graceful shutdown to release its emulators immediately
    (rather than waiting for TTL expiry).
    """
    claim_key = f"emulator:claim:{worker_id}"
    metadata_key = f"worker:metadata:{worker_id}"

    emulator_ids = r.smembers(claim_key)

    r.delete(claim_key)
    r.delete(metadata_key)

    logger.info(f"✓ Released emulators for {worker_id}: {emulator_ids}")

    return jsonify({
        'status': 'released',
        'worker_id': worker_id,
        'emulators_released': list(emulator_ids)
    }), 200


@app.route('/emulators/list', methods=['GET'])
def list_workers():
    """List all currently online workers with their emulator assignments."""
    workers = []

    for key in r.scan_iter("worker:metadata:*"):
        worker_id = key.split(':')[-1]
        metadata = r.hgetall(key)
        claim_key = f"emulator:claim:{worker_id}"
        emulator_ids = sorted([int(x) for x in r.smembers(claim_key)])

        workers.append({
            'worker_id': worker_id,
            'hostname': metadata.get('hostname', 'unknown'),
            'emulator_ids': emulator_ids,
            'emulator_count': len(emulator_ids),
            'claimed_at': metadata.get('claimed_at'),
            'ttl': r.ttl(claim_key)
        })

    return jsonify({
        'total_workers': len(workers),
        'workers': workers
    }), 200


@app.route('/emulators/scrape', methods=['POST'])
def scrape_claims():
    """
    Process claims using assigned emulators.

    Request JSON:
    {
        "worker_id": "abc123",
        "claim_ids": ["claim1", "claim2", ...],
        "emulator_ids": [1, 2, 3, 4],
        "method": "SEARCH BY CCN",
        "cert_date_mmddyy": "010120"
    }

    Note: This is a placeholder. The actual scraping logic should be
    implemented in your emulator integration layer.
    """
    data = request.get_json() or {}
    worker_id = data.get('worker_id')
    claim_ids = data.get('claim_ids', [])
    emulator_ids = data.get('emulator_ids', [])

    logger.info(
        f"Scrape request from {worker_id}: "
        f"{len(claim_ids)} claims using emulators {emulator_ids}"
    )

    # TODO: Implement actual emulator scraping logic
    # This would involve:
    # 1. Connecting to EXTRA emulator sessions on specified ports
    # 2. Processing each claim
    # 3. Returning results

    return jsonify({
        'status': 'success',
        'worker_id': worker_id,
        'claims_processed': len(claim_ids),
        'emulators_used': emulator_ids,
        'results': []  # TODO: Add actual results
    }), 200


# ─────────────────────────────────────────────────────────────
# Error Handlers
# ─────────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'not_found'}), 404


@app.errorhandler(500)
def server_error(e):
    logger.error(f"Server error: {e}")
    return jsonify({'error': 'internal_server_error'}), 500


if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("  Emulator Agent Starting")
    logger.info("=" * 60)
    logger.info(f"Total Emulators: {TOTAL_EMULATORS}")
    logger.info(f"Emulators per Claim: {EMULATORS_PER_CLAIM}")
    logger.info(f"Claim TTL: {CLAIM_TTL}s")
    logger.info(f"Redis: {REDIS_HOST}:{REDIS_PORT}")
    logger.info("=" * 60)

    port = int(os.getenv('EMULATOR_AGENT_PORT', 8765))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
