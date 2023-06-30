"""
Module that implements functions for RabbitMQ workers to use on separate processes.
"""

import functools
import sys
import pika
import time
from numpy.random import normal
import random
import os
from pathlib import Path
import logging
from datetime import datetime
from smssim import constants


def init_logging(sim_name):
    """
    Initializes logging module to create a "smssim_logs" folder in the
    user's home directory. Each worker will have its own unique log file
    based on it's process ID.
    :param sim_name: The name of the simulation, used for log folder name.
    """

    if sim_name is None:
        log_folder_name = os.path.join(Path.home(),
                                       "smssim_logs",
                                       datetime.now().strftime("%Y%m%d-%H%M%S"))
    else:
        log_folder_name = os.path.join(Path.home(),
                                       "smssim_logs",
                                       sim_name,
                                       datetime.now().strftime("%Y%m%d-%H%M%S"))
    Path(log_folder_name).mkdir(parents=True, exist_ok=True)
    logging.basicConfig(format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
                        datefmt='%H:%M:%S',
                        handlers=[
                            logging.StreamHandler(sys.stdout),
                            logging.FileHandler(os.path.join(log_folder_name,
                                                             "pid_" + str(os.getpid()) + ".log")),
                        ],
                        level=logging.DEBUG)


def send_sms(failure_rate, send_delay_mean):
    """
    Simulate sending an SMS message. Delay is selected from a normal
    distribution around the provied mean. Failure rate is implemented by
    choosing random numbers and comparing them to the failure rate.
    :param failure_rate: Percentage of messages that should fail.
    :type failure_rate: float
    :param send_delay_mean: Mean delay in milliseconds between messages.
    :type send_delay_mean: int
    :return: Whether the message was sent successfully and the delay.
    :rtype: tuple(bool, int)
    """

    # Draw a random number from a normal distribution around the mean.
    delay = normal(size=1, loc=send_delay_mean)[0]
    if send_delay_mean > 0:
        time.sleep(delay/1000)

    # Calculate whether the message should fail based on a failure rate.
    return random.randint(0, 100) >= failure_rate, delay


def callback(ch, method, properties, body, args):
    """
    Callback function for the RabbitMQ consumer. This function is called when a
    message is received from the queue. It simulates sending an SMS message and
    then pushes the result to the appropriate results queue. Will send an
    ACK or NACK back to RabbitMQ when finished.

    :param ch: The channel object.
    :param method: The method object.
    :param properties: The properties object.
    :param body: The message body.
    :param args: A tuple containing the failure rate, send delay mean, and
                 whether to retry failed messages.
    """
    body_string = body.decode()
    sent_successfully, delay = send_sms(args[0], args[1])
    if sent_successfully:
        logging.info(f" [{os.getpid()}] Sent message: {body_string}")
        push_to_results_queue(True, body_string, delay)
        ch.basic_ack(delivery_tag=method.delivery_tag)
    else:
        logging.error(f" [{os.getpid()}] Fail message: {body_string}")
        push_to_results_queue(False, body_string, delay)
        ch.basic_nack(delivery_tag=method.delivery_tag,
                      requeue=args[2])


def push_to_results_queue(sent, body_string, delay):
    """
    Pushes the result of sending an SMS message to the appropriate results queue.
    :param sent: Whether the message was sent successfully.
    :param body_string: The message body.
    :param delay: The delay in milliseconds.
    """
    with pika.BlockingConnection(pika.ConnectionParameters(host=constants.RABBITMQ_HOST)) as mq:
        mq_channel = mq.channel()
        queue_name = constants.PASSED_QUEUE_NAME if sent else constants.FAILED_QUEUE_NAME
        mq_channel.queue_declare(queue=queue_name, durable=True)
        full_message = f"{body_string},{delay},{datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')},{os.getpid()}"

        # Use a default exchange identified by an empty string.
        mq_channel.basic_publish(
            exchange='',
            routing_key=queue_name,
            body=full_message,
            properties=pika.BasicProperties(delivery_mode=pika.spec.PERSISTENT_DELIVERY_MODE))

        # Also publish the delay time to a separate queue.
        mq_channel.queue_declare(queue=constants.DELAY_TIMES_QUEUE_NAME,durable=True)
        mq_channel.basic_publish(
            exchange='',
            routing_key=constants.DELAY_TIMES_QUEUE_NAME,
            body=str(delay),
            properties=pika.BasicProperties(delivery_mode=pika.spec.PERSISTENT_DELIVERY_MODE))

        logging.info(" [*] Queued result %r" % full_message)


def start_consuming(failure_rate, send_delay_mean, sim_name, retry_failed):
    """
    Starts the RabbitMQ consumer. This  will block until the consumer is stopped.
    :param failure_rate: Percentage of messages that should fail.
    :type failure_rate: float
    :param send_delay_mean: Mean delay in milliseconds between messages.
    :type send_delay_mean: int
    :param sim_name: The name of the simulation, used for log folder name.
    :type sim_name: str
    :param retry_failed: Whether to retry failed messages.
    :type retry_failed: bool
    """

    init_logging(sim_name)
    with pika.BlockingConnection(pika.ConnectionParameters(host=constants.RABBITMQ_HOST)) as conn:
        channel = conn.channel()
        channel.queue_declare(queue=constants.TASK_QUEUE_NAME, durable=True)
        logging.info(f" [*] Worker {os.getpid()} waiting for messages.")
        channel.basic_qos(prefetch_count=1)
        on_message_callback = functools.partial(callback, args=(failure_rate,
                                                                send_delay_mean,
                                                                retry_failed))
        channel.basic_consume(queue=constants.TASK_QUEUE_NAME, on_message_callback=on_message_callback)
        channel.start_consuming()
