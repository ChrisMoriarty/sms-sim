# ChriSMS Simulator
Simulates sending a large number of SMS alerts, like for an emergency alert service.

## Installation
1. Install RabbitMQ or use the docker image, documentation found [here](https://www.rabbitmq.com/download.html).
2. Clone this repo locally
3. cd in `sms-sim/src` and run `pip install .`

## Usage
1. Start RabbitMQ server, by default the sms-sim package assumes it's running on localhost on port 5672
2. Start the streamlit app by running `streamlit run streamlit_gui.py` in the `sms-sim/src` directory
3. A browser window should pop up with the streamlit app. If not, navigate to http://localhost:8501 in your browser.
4. All fields have sensible defaults to enable you to easily click the "Start Simulation" button.
5. The "Sent Messages", "Failed Messages" and "Average Time per Message (ms)" fields will begin to update based on the 
"Monitoring Interval" field.
6. When the sim is done, a results table will be display below showing metadata for every message sent.
7. The logs will save into your home directory under `sms-sim_logs/<Simulation Name>/<timestamp>/`
8. Repeat until you are tired of simulating SMS messages ;)

## Workflow
1. Messages are randomly generated and sent to a RabbitMQ queue.
2. Workers on separate processes consume messages and simulate sending the message.
3. Messages fail sending based on the "Failure Rate" field, and can either be retried or discarded.
4. Workers push the results of the message attempt to either a "passed" or "failed" queue, and also push their delay
times to third queue.
5. During the sleep interval, the main thread consumes the delay times and calculates a running average delay time for 
the GUI.
6. When the simulation is over the results in both "passed" and "failed" queues are combined
into a pandas dataframe and displayed in the GUI. 
7. Each consecutive run will clear the queues before starting, also generating a new set of logs.
