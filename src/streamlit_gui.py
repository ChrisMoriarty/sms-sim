"""
Streamlit GUI for SMS Simulator.
"""

import time
import pika
import streamlit as st
import smssim as sim

# When using multiprocessing, Streamlit needs to only run on the main thread.
if __name__ == '__main__':

    # Field labels for GUI elements, also serves as the keys for session_state.
    field_labels = {
        "sim_name": "Simulation Name",
        "num_msgs": "Number of Messages",
        "fail_rate": "Failure Rate (%)",
        "delay_mean": "Delay Mean",
        "retry": "Retry Failures",
        "update_interval": "Monitoring Interval (seconds)",
        "num_processes": "Number of Workers",
        "avg_time": "Average Time per Message (ms)",
        "total_time": "Total Time of Simulation",
        "total_attempts": "Total Attempts",
        "sent_messages": "Sent Messages",
        "failed_messages": "Failed Messages",
    }

    # Other variables that need to persist between reruns.
    session_state_variables = {
        "results": None,
        "sms_pool": None,
    }

    # Initialize session_state with GUI input variables that need to persist.
    session_state_variables.update(field_labels)
    for key in session_state_variables.keys():
        if key not in st.session_state:
            st.session_state[key] = None

    # Create three columns so we can center the header.
    header_col1, header_col2, header_col3 = st.columns([1, 3, 1])
    with header_col2:
        st.header(":speech_balloon: ChriSMS Simulator :speech_balloon:")

    # Let the Simulation Name field take up the full width.
    st.session_state["sim_name"] = st.text_input(field_labels["sim_name"],
                                                 help="This name is used to create the folder where the logs will be "
                                                      "stored.",
                                                 value="analog_hw")

    # Create two columns for the input fields to make the GUI more compact.
    input_col1, input_col2 = st.columns(2)
    with input_col2:
        st.session_state["num_msgs"] = st.text_input(field_labels["num_msgs"],
                                                     help="The number of messages to send in the simulation.",
                                                     value="100")
        st.session_state["fail_rate"] = st.text_input(field_labels["fail_rate"],
                                                      help="Messages are randomly selected to fail based on this rate.",
                                                      value="10")
        st.session_state["retry"] = st.checkbox(field_labels["retry"],
                                                help="If checked, failed messages will be retried until they succeed.",
                                                value=True)
    with input_col1:
        st.session_state["delay_mean"] = st.text_input(field_labels["delay_mean"],
                                                       help="The mean delay in milliseconds between messages.",
                                                       value="100")
        st.session_state["update_interval"] = st.text_input(field_labels["update_interval"],
                                                            help="The interval in seconds at which the monitoring "
                                                                 "information will be updated.",
                                                            value="1")
        st.session_state["num_processes"] = st.text_input(field_labels["num_processes"],
                                                          help="The number of worker processes to use.",
                                                          value="3")

    # Create a new simulation when the button is pressed.
    if st.button("Start Simulation", use_container_width=True):

        # Reset the avg_time field.
        st.session_state["avg_time"] = None
        sim.queue_sms_messages(int(st.session_state["num_msgs"]))
        sms_pool = sim.SmsWorkerPool(num_workers=int(st.session_state["num_processes"]),
                                     failure_rate=float(st.session_state["fail_rate"]),
                                     send_delay_mean=int(st.session_state["delay_mean"]),
                                     sim_name=st.session_state["sim_name"],
                                     retry_failed=bool(st.session_state["retry"]))
        sms_pool.start()

    # Create three columns for the monitoring fields tos fit on one line.
    monitor_col1, monitor_col2, monitor_col3 = st.columns(3)

    with monitor_col1:
        st.text_input(field_labels["sent_messages"], value=st.session_state["sent_messages"],
                      key="sent_messages_key", disabled=True)
    with monitor_col2:
        st.text_input(field_labels["failed_messages"], value=st.session_state["failed_messages"],
                      key="failed_messages_key", disabled=True)
    with monitor_col3:
        st.text_input(field_labels["avg_time"], value=st.session_state["avg_time"],
                      key="avg_time_key", disabled=True)

    # This makes sure we update the fields even after the simulation finished.
    if st.session_state.sent_messages_key is not None and st.session_state["sent_messages"] is not None:
        fields_synced = st.session_state.sent_messages_key == st.session_state["num_msgs"]
    else:
        fields_synced = True

    if sim.tasks_remaining() or not fields_synced:
        update_interval = int(st.session_state["update_interval"])

        # Before sleeping, use the downtime to compute the average delay.
        avg_delay, time_left = sim.compute_avg_delay(int(st.session_state["update_interval"]))
        time.sleep(time_left)
        with pika.BlockingConnection(pika.ConnectionParameters(host=sim.constants.RABBITMQ_HOST)) as conn:
            channel = conn.channel()
            st.session_state["sent_messages"] = channel.queue_declare(queue=sim.constants.PASSED_QUEUE_NAME,
                                                                      durable=True).method.message_count
            st.session_state["failed_messages"] = channel.queue_declare(queue=sim.constants.FAILED_QUEUE_NAME,
                                                                        durable=True).method.message_count
            if "avg_time" in st.session_state and avg_delay:
                st.session_state["avg_time"] = avg_delay
            else:
                st.session_state["avg_time"] = None
        st.experimental_rerun()
    else:
        # Gather results and display them as a table.
        st.session_state["results"] = sim.gather_results()
        if st.session_state["results"] is not None:
            st.subheader("Results")
            st.dataframe(st.session_state["results"])
