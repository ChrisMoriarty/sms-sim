import time
from multiprocessing import Process
import smssim as sim
import pika
import pytest


@pytest.fixture()
def test_mq():
    # Override constants.py queue names with test names.
    sim.constants.FAILED_QUEUE_NAME = "test_failed_queue"
    sim.constants.PASSED_QUEUE_NAME = "test_passed_queue"
    sim.constants.TASK_QUEUE_NAME = "test_sms_queue"
    sim.constants.DELAY_TIMES_QUEUE_NAME = "test_delay_times_queue"

    # Connect to rabbitmq and create test queues.
    conn = pika.BlockingConnection(pika.ConnectionParameters(host=sim.constants.RABBITMQ_HOST))
    channel = conn.channel()
    channel.queue_declare(queue=sim.constants.FAILED_QUEUE_NAME, durable=True)
    channel.queue_declare(queue=sim.constants.PASSED_QUEUE_NAME, durable=True)
    channel.queue_declare(queue=sim.constants.TASK_QUEUE_NAME, durable=True)
    channel.queue_declare(queue=sim.constants.DELAY_TIMES_QUEUE_NAME, durable=True)

    yield conn

    # Cleanup.
    channel.queue_delete(queue=sim.constants.PASSED_QUEUE_NAME)
    channel.queue_delete(queue=sim.constants.FAILED_QUEUE_NAME)
    channel.queue_delete(queue=sim.constants.TASK_QUEUE_NAME)
    channel.queue_delete(queue=sim.constants.DELAY_TIMES_QUEUE_NAME)
    conn.close()


def test_end_to_end_test():
    """
    The override trick in the fixture above doesn't work for this test. So
    it is using the operational queue names, which is 100% a bad idea that I
    would totally fix if this were a real project ;)

    I also had ambitions to parameterize this test, but I ran out of time.
    """
    num_msgs = 20
    num_workers = 2
    fail_rate = 50
    delay_mean = 50
    retry = True

    sim.queue_sms_messages(num_msgs)
    sms_pool = sim.SmsWorkerPool(num_workers=num_workers,
                                 failure_rate=fail_rate,
                                 send_delay_mean=delay_mean,
                                 sim_name="pytest_regression_test",
                                 retry_failed=retry)
    sms_pool.start()

    # Wait for all messages to be processed.
    while sim.tasks_remaining():
        time.sleep(1)

    # Check the avg time function, use a large monitoring interval to drain the
    # queue completely.
    delay, _ = sim.compute_avg_delay(monitoring_interval=1000)
    assert delay == pytest.approx(delay_mean, abs=5)

    # Gather the results into a pandas dataframe.
    df = sim.gather_results()

    # Check that the number of passed messages is == num_msgs.
    assert df.loc[df['Status'] == "Success"].shape[0] == num_msgs

    # Check that the number of failed messages meets the fail rate.
    assert df.loc[df['Status'] == "Failed"].shape[0] == pytest.approx(num_msgs * (fail_rate / 100), abs=30)

    # Check that the delay times are within 5% of the mean. {'Fee':'int'}
    assert df['Delay'].astype('float').mean() == pytest.approx(delay_mean, abs=5)

    # Cleanup.
    sms_pool.stop()


@pytest.mark.repeat(100)
def test_generate_phone_number():
    ten_digit_number = sim.producer.generate_phone_number()
    assert len(ten_digit_number) == 10
    assert isinstance(int(ten_digit_number), int)


@pytest.mark.repeat(100)
def test_generate_message():
    hundred_char_message = sim.producer.generate_message()
    assert len(hundred_char_message) <= 100

    ten_char_message = sim.producer.generate_message(max_length=10)
    assert len(ten_char_message) <= 10

    two_char_message = sim.producer.generate_message(max_length=2)
    assert len(two_char_message) <= 2


def test_queue_sms_messages(test_mq):
    sim.producer.queue_sms_messages(num_messages=1000)
    channel = test_mq.channel()
    assert channel.queue_declare(queue=sim.constants.TASK_QUEUE_NAME, durable=True).method.message_count == 1000


@pytest.mark.parametrize("failure_rate", range(5, 95, 10))
def test_send_sms(failure_rate):
    count_failed = 0
    num_tries = 10000
    for i in range(num_tries):
        passed, delay = sim.send_sms(failure_rate, 0)
        if not passed:
            count_failed += 1

    # Check that the failure rate is around 3% of the expected failure rate.
    assert (count_failed / num_tries) * 100 == pytest.approx(failure_rate, abs=3)
