"""
Module for generating and queueing "SMS messages" to a RabbitMQ task queue.
"""

import logging
import pika
import string
import random
from smssim import constants


def generate_phone_number():
    """
    Generates a random 10-digit phone number.
    :return: A random 10-digit phone number.
    :rtype: str
    """
    return ''.join(random.choices(string.digits, k=10))


def generate_message(max_length=100):
    """
    Generates a random string of letters and numbers of a random length between
    1 and max_length.
    :param max_length: The maximum length of the generated string.
    :type max_length: int
    :return: A random string of letters and numbers.
    :rtype: str
    """
    # First generate a number between 1 and max_length.
    length = random.randint(1, max_length)

    # Then generate and return a random string of that length.
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


def queue_sms_messages(num_messages=1000):
    """
    Queues a number of SMS messages to the RabbitMQ task queue.
    :param num_messages: The number of messages to queue.
    """
    with pika.BlockingConnection(pika.ConnectionParameters(host=constants.RABBITMQ_HOST)) as conn:
        channel = conn.channel()
        channel.queue_delete(queue=constants.PASSED_QUEUE_NAME)
        channel.queue_delete(queue=constants.FAILED_QUEUE_NAME)
        channel.queue_delete(queue=constants.TASK_QUEUE_NAME)
        channel.queue_delete(queue=constants.DELAY_TIMES_QUEUE_NAME)

        # Set this queue to be durable so that it will survive a RabbitMQ restart.
        channel.queue_declare(queue=constants.TASK_QUEUE_NAME, durable=True)

        for i in range(num_messages):
            full_message = f"{generate_phone_number()},{generate_message()}"

            # Use a default exchange identified by an empty string.
            channel.basic_publish(
                exchange='',
                routing_key=constants.TASK_QUEUE_NAME,
                body=full_message,
                properties=pika.BasicProperties(delivery_mode=pika.spec.PERSISTENT_DELIVERY_MODE))

            logging.info(" [*] Queued %r" % full_message)
