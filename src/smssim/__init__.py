# Import shortcuts for convenient shorter import statements.
from .smspool import SmsWorkerPool
from .producer import queue_sms_messages
from .worker import send_sms
from .smspool import tasks_remaining, compute_avg_delay, gather_results
from . import constants

# Silence errors from pika
import logging

logging.getLogger("pika").setLevel(logging.CRITICAL)
