# Raspberry Pi Real-Time Battery Monitoring System (RTBMS)

## Project Overview
This project monitors 4 sensor BP,BC,CR and FP using Raspberry Pi, stores data locally, and optionally uploads it to AWS IoT Core or Supabase. Data can be visualized on Grafana dashboards.

## Features
- Real-time pressure hat processing (BP,BC,CR,FP)
- Data storage in SQLite
- Web dashboard with Grafana
- Cloud upload to AWS IoT / Supabase
- Deep sleep mode for battery saving

## Raspberry Pi Setup :-(2-3 Days)
Go to raspi configure 

## SD Card Setup :
country=INDIA
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1

network={
    ssid="YOUR_WIFI_SSID"
    psk="YOUR_WIFI_PASSWORD"
    key_mgmt=WPA-PSK
}
then update and download and the flash drive 
set the username and Ip and set Password
get it hostname & IP address for it .

## INstall I2c :-(1-day)
sudo apt update
sudo apt upgrade -y
sudo reboot


## Folder Structure(2 Days)
RTBMS/
├── data/
├── src/pressure_project/
│   ├── aws_iot/
         ├──4 certificate file AWS
│   ├── db/
         ├── Database file
│   ├── logs/
│   ├── system_capture.py
│   ├── system_upload.py
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── requirements.txt

## Installation (1 Day)
1. Enable I2C on Raspberry Pi (`sudo raspi-config`)
2. Install required Python libraries:
   ```bash
   pip3 install RPi.GPIO smbus2 adafruit-circuitpython-ina219 paho-mqtt flask requests
3.INstall all the files
4. Run all the files
5. Updated all the files configured and check the working the sensor reading i2c is on or not 
6. Docker install check it by docker --v
7. Git also install in it and pull toward all the code files .
8. Connect to AWS certificate

## AWS CERTIFICATION AND CONNECION :_(2-3 day)
Step-1: Create IAM User
Login to AWS Console, search IAM, 
open it, go to Users, and click Create user. Enter a user name like iot-admin-user and click Next. 
Choose Attach policies directly and add AWSIoTFullAccess (and optionally IAMReadOnlyAccess).
 Click Next and then Create user. After creation, open the user, go to Security credentials, create an Access Key (CLI), and download the CSV file. Save this file safely because the secret key will not be shown again.
Step 2 :-Open AWS IoT Core
From AWS Console, search IoT Core and open it. 
Make sure the AWS region is correct and fixed (for example ap-south-1). All IoT resources must be created in the same region.
Step-3: Create a New Thing
In IoT Core, go to Manage → Things, click Create things, select Create single thing, and click Next. 
Enter a Thing name such as pressure_device_01, skip Thing type, and click Next.
Step-4: Create Certificates
Choose Auto-generate a new certificate and click Next. Download all four files: device certificate, private key, public key, and AmazonRootCA1.pem. Keep these files safely in one folder. Make sure the certificate status is set to ACTIVE, then click Next.
Step-5: Create and Attach IoT Policy
Click Create policy, give a name like pressure_device_policy, and allow iot:Connect, iot:Publish, iot:Subscribe, and iot:Receive permissions. Create the policy and attach it to the certificate. Then finish by clicking Create thing.
Step-6: Verify Certificate Attachment
Go to Manage → Things, open your Thing, and check the Certificates section. Confirm that the certificate is attached and its status is ACTIVE.
Step-7: Get AWS IoT Endpoint
In IoT Core, go to Settings and copy the IoT endpoint URL. This endpoint will be used in your Python, Docker, or device code for MQTT connection.
Step-8: Use Certificates in Device Code
Copy the downloaded certificate files into your project folder (for example aws_iot/). Configure your device or Docker container to use the certificate, private key, Root CA, and endpoint. Do not use IAM access keys inside device code.

##AWS in S3 Creaated for Database :-
Step-1: Open Amazon S3
Login to the AWS Console, search for S3, and open the Amazon S3 service. Make sure your selected AWS region is correct and consistent with your project requirements.
Step-2: Create a New Bucket
Click Create bucket. Enter a unique bucket name (for example, pressure-data-bucket-01). Select the AWS region where your application is running, then proceed to the next settings.
Step-3: Configure Object Ownership
In the Object Ownership section, select ACLs disabled (recommended) and keep Bucket owner enforced enabled. This ensures that the bucket owner has full control over all objects.
Step-4: Configure Block Public Access
Keep Block all public access enabled to protect your data from public exposure. Acknowledge the warningAcknowledge the warning and continue unless public access is specifically required.
Step-5: Configure Bucket Versioning
Enable Versioning if you want to keep multiple versions of objects for recovery purposes. If not required, you may leave it disabled.
Step-6: Enable Default Encryption
Keep Server-side encryption (SSE-S3) enabled to ensure that all uploaded data is automatically encrypted at rest.
Step-7: Review and Create Bucket
Review all the bucket configuration settings carefully. Once verified, click Create bucket to finalize the setup
Step-8: Create Folder Structure (Optional)
Open the bucket, click Create folder, and add folders such as raw_data, processed_data, or logs to organize your files.
Step-9: Upload a Test File
Click Upload, select a test file from your system, and upload it to confirm that the bucket is working correctly.
Step-10: Create IAM Policy for S3 Access
Open IAM, create a new policy allowing s3:PutObject, s3:GetObject, and s3:ListBucket permissions for your bucket, and save the policy.
Step-11: Attach IAM Policy to User
Attach the created S3 policy to the required IAM user so applications or scripts can securely access the bucket.

## Dynamo DB IN AWS IOT CORE FOR DATA SENDING TO DATABASE :-(1 Day)
Step 1 : Open the Dynamo DB in AWS window .
Step-2: Create a New Table
Click Create table. Enter a Table name (for example, pressure_data_table). Set the Primary key—this can be a Partition key like device_id (type String). You may also add a Sort key like timestamp (type Number or String) if you want to store multiple records per device.
Step-3: Configure Table Settings
You can leave the default settings for now. By default, DynamoDB uses on-demand capacity mode, which is convenient for unpredictable workloads. You may enable Auto Scaling later if needed.
Step-4: Add Secondary Indexes (Optional)
If you need to query the table using attributes other than the primary key, you can add a Global Secondary Index (GSI). Otherwise, skip this step for simplicity.
Step-6: Insert Test Data via Console
Open your table, go to the Items tab, and click Create item. Add a test record with values for device_id, timestamp, and other attributes (like vibration, battery_voltage). Click Save to insert the item.
Step-7: Create IAM Policy for DynamoDB Access
Open IAM, create a policy with permissions for dynamodb:PutItem, dynamodb:GetItem, dynamodb:Query, dynamodb:Scan for your table. Save the policy with a name like DynamoDBPressurePolicy.
Step-8: Attach Policy to IAM User
Attach the created IAM policy to the IAM user your application or script will use. This allows programmatic access to your DynamoDB table.
Step-9: Connect to DynamoDB from Application
Use AWS SDK (Boto3 for Python, AWS SDK for Java, etc.) with the IAM user credentials. Provide the table name and region to perform operations like inserting, reading, or querying data.
Step-10: Query and Scan Data
Use Query to fetch items by Partition key or Scan to read all table items. This lets your application monitor device data or generate reports.
Step-11: Monitor Table
Go to the Metrics and Alarms tab in DynamoDB to monitor read/write usage and set alerts if needed. This helps prevent exceeding capacity limits.
Step-12: Optional – Enable Streams
If you want to react to new data in real-time (for example, trigger a Lambda function when new sensor data arrives), enable DynamoDB Streams.

## AWS Lambada interfacing AWS IOT data to :- (1 Day)
Step-1: Open AWS IoT Core
Login to AWS Console, search IoT Core, and open it. Make sure your AWS region is correct and consistent for all resources.
Step-2: Create or Use an Existing Thing
Go to Manage → Things, select your IoT Thing, or create a new one (e.g., pressure_device_01). Ensure the certificate is ACTIVE and the IoT policy is attached.
Step-3: Create an IoT Topic Rule
In IoT Core, go to Act → Rules → Create rule.
Enter a Rule name (example: send_to_supabase_rule).
In Rule query statement, write:
SELECT * FROM 'pressure/data'
Step-4: Add Action to Send Data to Lambda
In the Rule, click Add action → Send a message to a Lambda function.
Click Create a new Lambda function → Author from scratch.
Enter function name (example: iot_to_supabase).
Runtime: Python 3.11 (default, no need to edit code).
Permissions: create a new role with basic Lambda permissions.
At this step, AWS will auto-create Lambda and attach it to the IoT Rule. You do not need to write any code manually.
Step-5: Configure Lambda Environment Variables (Optional)

Open Lambda → Configuration → Environment variables.
Add key-value pairs if you want to use them in Lambda later:
SUPABASE_URL = your-supabase-url
SUPABASE_KEY = your-service-role-key
TABLE_NAME = pressure_data
This step is optional if you want to configure it later.

Step-6: Add Lambda Permissions
Open Lambda → Configuration → Permissions.
Attach AWSIoTDataAccess managed policy to the Lambda role.
This ensures IoT Core can trigger the Lambda function.
Step-7: Connect Lambda to IoT Rule
Go back to your IoT Rule → Add action → Send to Lambda.
Select the Lambda function (iot_to_supabase).
Click Add action → Create rule.
AWS now automatically triggers Lambda whenever IoT Core receives a m
step-8: Test the Flow
In IoT Core, go to MQTT test client.
Publish a test message to 'pressure/data', e.g.:

{
  "device_id": "pressure01",
  "vibration": 12.5,
  "battery": 3.7
}
Check Lambda logs in CloudWatch → confirm the trigger happened.
You do not need to modify any Lambda code; AWS handles the trigger automatically.
Step-9: Monitor and Debug
Check IoT Rule metrics → ensures rule triggered.

 ## Supabase Connected with AWS lamabada :- (1 Day)
Step-1: Create Supabase Table
Go to Supabase
 → log in → create a new project.
Open project → Database → Tables → New Table.
Table name: pressure_data. Add columns:
device_id (text)
timestamp (timestamp)
vibration (float)
battery (float)
Save the table.
Copy Project URL and Service Role Key (for Lambda access).

Step-2: Create AWS IoT Rule + Lambda Trigger
AWS Console → IoT Core → Act → Rules → Create rule.
Rule name: send_to_supabase.
SQL query: SELECT * FROM 'pressure/data'.
SQL query: SELECT * FROM 'pressure/data'.
Add action → Send to Lambda → Create new Lambda (Python runtime).
Add environment variables to Lambda:

SUPABASE_URL = your-project-url
SUPABASE_KEY = your-service-role-key
TABLE_NAME = pressure_data
Attach AWSIoTDataAccess policy to Lambda role.
Save rule → now all messages published to 'pressure/data' trigger Lambda automatically.

## Supbase to Grfana save process :-(1 Day)
Got it! You want Supabase → Grafana integration (so your Supabase PostgreSQL data can be visualized in Grafana). I’ll give it step-by-step, simple, point-to-point style.
Step-1: Open Supabase
Login to Supabase
Go to your project → Database → Tables.
Make sure your table exists (example: pressure_data).
Copy Database connection string / credentials: host, port (5432), database name, username, password.
Step-2: Open Grafana
Login to your Grafana instance (Cloud or local).
Go to Configuration → Data Sources → Add data source.
Step-3: Add PostgreSQL Data Source
Select PostgreSQL as the type.
Fill in the fields using Supabase credentials:
Host: <your-db-host>:5432
Database: <your-db-name>
User: <your-db-username>
Password: <your-db-password>
SSL Mode: require (Supabase requires SSL)
Click Save & Test → it should show Data source is working.
Step-4: Create a Dashboard in Grafana
Go to Dashboards → New Dashboard → Add Panel.
Select your PostgreSQL data source.
Write SQL queries to fetch your data. Example:
SELECT timestamp, vibration, battery 
FROM pressure_data 
ORDER BY timestamp DESC 
LIMIT 100;
Choose visualization type (Graph, Table, Gauge, etc.).
Step-5: Save & Monitor
Save the dashboard.
Now any new data inserted into Supabase (from AWS IoT → Lambda) will be automatically visible in Grafana.
## Without the SSH Directly on the code files
Step-2: Set Up Auto-Startup on Raspberry Pi (Without SSH) (1 Day)
Option 1: Using cron (simplest)
Open crontab:
crontab -e
Add these lines at the bottom:
@reboot python3 /home/pi/pressure_project/capture.py &
@reboot python3 /home/pi/pressure_project/upload.py &
Save and exit.
Reboot Raspberry Pi:
sudo reboot
Both scripts will now run automatically after boot, without SSH.
OR Methode:-
Option 2: Using systemd (more robust)
Create a service file for capture.py:
sudo nano /etc/systemd/system/capture.service
Add:
[Unit]
Description=Capture Script
After=network.target
[Service]
ExecStart=/usr/bin/python3 /home/pi/pressure_project/capture.py
WorkingDirectory=/home/pi/pressure_project
Restart=always
User=pi
[Install]
WantedBy=multi-user.target

Repeat for upload.py as upload.service.
Enable services:
sudo systemctl enable capture.service
sudo systemctl enable upload.service
sudo systemctl start capture.service
sudo systemctl start upload.service

Now scripts run continuously after Pi boots, even without SSH.

Step-3: Update Database / AWS Directly

capture.py reads sensor data continuously.
upload.py publishes data to:
AWS IoT Core MQTT topic, or
Supabase PostgreSQL (via REST API)
Since AWS IoT / Supabase is online, you can monitor data directly on AWS or Grafana:
IoT Core → MQTT test client shows live messages.
Supabase → PostgreSQL table shows live inserts.
Grafana → Dashboard updates automatically (refresh interval).
# Hardware Connection (2- Days)
Components Required
Raspberry Pi (any model with GPIO pins, e.g., Pi 3, Pi 4)
ADS1115 16-bit ADC module
Jumper wires (male-to-female)
Breadboard (optional, for prototyping)

Sensors or analog devices to read (optional, e.g., potentiometer, pressure sensor)
Step 1: Power Connections
Connect VCC on ADS1115 → 3.3V pin on Raspberry Pi (Pin 1)
Connect GND on ADS1115 → GND pin on Raspberry Pi (Pin 6)
⚠️ Note: ADS1115 can also work with 5V, but 3.3V is safer for Raspberry Pi.
Step 2: I2C Communication
Connect SCL on ADS1115 → SCL pin on Raspberry Pi (GPIO 3, Pin 5)
Connect SDA on ADS1115 → SDA pin on Raspberry Pi (GPIO 2, Pin 3)
🔹 Ensure I2C interface is enabled on Raspberry Pi:
sudo raspi-config
Interface Options → I2C → Enable
sudo reboot
Step 3: Alert/Other Pins (Optional)
ADDR: Sets I2C address (default to GND → 0x48, other options 0x49, 0x4A, 0x4B)
ALRT/RDY: Optional, used to detect conversion ready or alert signals.
Step 4: Analog Input Connections
ADS1115 has 4 analog input channels: A0, A1, A2, A3
Connect your analog sensor to one of the channels, e.g., A0
Example: Potentiometer middle pin → A0, ends → GND & VCC
Step 5: Final Check

Make sure all connections are snug.
Power on Raspberry Pi.
Run I2C scan to verify connection:
sudo apt-get install -y i2c-tools
i2cdetect -y 1
You should see 0x48 (or another address if you changed ADDR).
## Final setup :- (1 Day)
Checking with all correct raspberry pi with ADS1115 module working with the I2C and all pressure sensor .
## Final Workflow :-
Device → AWS IoT → Lambda → Supabase (PostgreSQL) → Grafana Dashboard
