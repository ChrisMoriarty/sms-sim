"""
Class to manage the "pool" of SMS workers.
"""

import time
from multiprocessing import Process
import numpy as np
import pandas as pd
import pika
from smssim.worker import start_consuming
from smssim import constants


class SmsWorkerPool:

    def __init__(self, num_workers=3,
                 failure_rate=.1,
                 send_delay_mean=100,
                 sim_name=None,
                 retry_failed=True):
        """
        Create an object to manage the pool of SMS workers.
        :param num_workers: The number of worker processes to use.
        :type num_workers: int
        :param failure_rate: The rate at which messages will fail (as percentage).
        :type failure_rate: float
        :param send_delay_mean: The mean delay in milliseconds between messages.
        :type send_delay_mean: int
        :param sim_name: The name of the simulation, used for log folder name.
        :type sim_name: str
        :param retry_failed: Whether to retry failed messages.
        :type retry_failed: bool
        """
        self.processes = []
        self.num_workers = num_workers

        for i in range(num_workers):
            p = Process(target=start_consuming, args=(failure_rate,
                                                      send_delay_mean,
                                                      sim_name,
                                                      retry_failed))
            self.processes.append(p)

    def start(self):
        """
        Start the worker processes.
        """
        for p in self.processes:
            p.start()

    def stop(self):
        """
        Stop the worker processes.
        """
        for p in self.processes:
            p.kill()


def gather_results():
    """
    Static method to gather results from the results queues.
    :return: A pandas DataFrame with the results.
    :rtype: pandas.DataFrame
    """
    with pika.BlockingConnection(pika.ConnectionParameters(host=constants.RABBITMQ_HOST)) as conn:
        channel = conn.channel()
        passed = []
        failed = []
        pass_body = ""

        # Declare queues if they don't exist.
        channel.queue_declare(queue=constants.FAILED_QUEUE_NAME, durable=True)
        channel.queue_declare(queue=constants.PASSED_QUEUE_NAME, durable=True)

        # Consume messages until passed queue is empty, and append to a list.
        while pass_body is not None:
            _, _, pass_body = channel.basic_get(queue=constants.PASSED_QUEUE_NAME, auto_ack=True)
            if pass_body is not None:
                passed.append(pass_body.decode())

        # Consume messages until failed queue is empty, and append to a list.
        fail_body = ""
        while fail_body is not None:
            _, _, fail_body = channel.basic_get(queue=constants.FAILED_QUEUE_NAME, auto_ack=True)
            if fail_body is not None:
                failed.append(fail_body.decode())

    # Return if no results were found.
    if not passed and not failed:
        return None

    # Otherwise parse the data, which are strings delimited by commas.
    data = []
    for p in passed:
        row = p.split(",")
        row.append("Success")
        data.append(row)

    for f in failed:
        row = f.split(",")
        row.append("Failed")
        data.append(row)

    # Convert to a pandas DataFrame and return.
    return pd.DataFrame(data, columns=["Phone Number", "Message", "Delay",
                                       "Timestamp", "Process ID", "Status"])


def tasks_remaining():
    """
    Static method to check if there are tasks remaining in the task queue.
    :return: True if there are tasks remaining, False otherwise.
    :rtype: bool
    """
    with pika.BlockingConnection(pika.ConnectionParameters(host=constants.RABBITMQ_HOST)) as mq:
        return mq.channel().queue_declare(queue=constants.TASK_QUEUE_NAME,
                                          durable=True).method.message_count > 0


def compute_avg_delay(monitoring_interval):
    """
    Hack to compute the average delay during the monitoring interval downtime.
    :param monitoring_interval: The monitoring interval entered by the user.
    :type monitoring_interval: int
    :return: Tuple of the average delay in milliseconds, and the time left in the monitoring interval.
    :rtype: tuple(float, float)
    """
    start = time.time()
    times = []

    # Consume messages until delay times queue is empty or if the monitoring interval has passed.
    with pika.BlockingConnection(pika.ConnectionParameters(host=constants.RABBITMQ_HOST)) as mq:
        while time.time() - start < monitoring_interval:
            mq_channel = mq.channel()
            mq_channel.queue_declare(queue=constants.DELAY_TIMES_QUEUE_NAME, durable=True)
            mq_channel.basic_qos(prefetch_count=1)
            _, _, body = mq_channel.basic_get(queue=constants.DELAY_TIMES_QUEUE_NAME,
                                              auto_ack=True)
            if body is not None:
                times.append(float(body))
            else:
                break
    # Return an empty string if no times were found, otherwise compute the average delay.
    if not times:
        return None, monitoring_interval
    else:
        avg_delay = np.array(times).mean()
        time_left = monitoring_interval - (time.time() - start)
        return avg_delay, time_left
