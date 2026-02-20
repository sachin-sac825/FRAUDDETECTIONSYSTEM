"""Celery tasks for UPI Fraud demo.

Run a worker with:
  celery -A tasks.celery worker --loglevel=info

Requires a Redis broker at redis://localhost:6379/0 by default. You can set
`CELERY_BROKER_URL` and `CELERY_RESULT_BACKEND` environment variables.
"""
import os
from celery import Celery

CELERY_BROKER = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', CELERY_BROKER)

celery = Celery('upi', broker=CELERY_BROKER, backend=CELERY_BACKEND)


@celery.task(bind=True)
def process_transaction_task(self, payload: dict):
    """Process a transaction in background by delegating to `app.process_transaction()`.

    The payload is expected to contain keys used by `process_transaction`.
    """
    try:
        # import lazily to avoid circular import issues at module import time
        from app import process_transaction

        upi = payload.get('upi_number') or payload.get('upi')
        amount = float(payload.get('amount', 0))
        hour = int(payload.get('hour', 0))
        day = int(payload.get('day', 1))
        month = int(payload.get('month', 1))
        year = int(payload.get('year', 2024))
        merchant = payload.get('merchant', 'Unknown Merchant')
        category = payload.get('category', 'Transfer')
        location = payload.get('location', 'Unknown')
        device_id = payload.get('device_id')

        tx, preds = process_transaction(upi, amount, hour, day, month, year, merchant, category, location, device_id=device_id)

        # Return simple JSON-serializable structure
        return {'success': True, 'transaction': tx, 'predictions': preds}
    except Exception as e:
        return {'success': False, 'error': str(e)}
