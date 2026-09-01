#include <WiFi.h>
#include <Wire.h>
#include <HardwareSerial.h>
#include <Adafruit_ADS1X15.h>
#include <EEPROM.h>
#include <math.h>

/*
  HAMS ESP32-WROOM Slave Code
  Features:
  - ESP32-WROOM
  - ADS1115 for PT1000 temperature and battery voltage
  - E220 LoRa UART module
  - LoRa M0/M1 control using GPIO18/GPIO19
  - LoRa Normal Mode before TX
  - LoRa Sleep/Config Mode after TX
  - ESP32 deep sleep for 15 minutes
  - EEPROM Device ID storage
  - Generation number stored in EEPROM
  - Sequence number stored in RTC memory
  - Detailed Serial Monitor output
*/

// ================= PIN DEFINITIONS =================

#define SDA_PIN 21
#define SCL_PIN 22

#define LORA_RX 16   // ESP32 RX2 <- E220 TXD
#define LORA_TX 17   // ESP32 TX2 -> E220 RXD
#define LORA_M0 18   // E220 M0
#define LORA_M1 19   // E220 M1

// ================= OBJECTS =================

HardwareSerial LoRaSerial(2);
Adafruit_ADS1115 ads;

// ================= EEPROM DEFINITIONS =================

#define EEPROM_SIZE 64
#define MAGIC_ADDR 0
#define ID_ADDR 4
#define MAGIC_VALUE 0x55
#define MAX_ID_LEN 20
#define GEN_ADDR 32

// ================= RTC MEMORY =================

RTC_DATA_ATTR uint32_t sequenceNo = 0;
RTC_DATA_ATTR bool rtcValid = false;

// ================= GLOBAL VARIABLES =================

String DEVICE_ID = "";
uint32_t generationNo = 0;

// ================= SENSOR CONSTANTS =================

const float VCC = 3.3;
const float R_FIXED = 10000.0;       // 10k fixed resistor
const float R0 = 1000.0;             // PT1000 resistance at 0°C
const float A = 3.9083e-3;
const float B = -5.775e-7;
const float TEMP_OFFSET = 0.0;

const float BAT_DIVIDER_FACTOR = 6.0;  // 100k + 20k divider = factor 6

// ================= TIMINGS =================

const unsigned long ID_WAIT_MS = 50000;
const int MAX_ID_ATTEMPTS = 10;
const unsigned long READ_WAIT_MS = 5000;
const unsigned long LORA_WAIT_MS = 3000;

const uint64_t SLEEP_TIME_US =  60ULL * 1000000ULL;  // 15 minutes

// ================= ID FUNCTIONS =================

bool isValidID(String id) {
  id.trim();

  if (id.length() != 7) return false;
  if (!id.startsWith("HAMS")) return false;

  for (int i = 4; i < 7; i++) {
    if (!isDigit(id[i])) return false;
  }

  return true;
}

void saveID(String id) {
  EEPROM.write(MAGIC_ADDR, MAGIC_VALUE);

  for (int i = 0; i < MAX_ID_LEN; i++) {
    if (i < id.length()) {
      EEPROM.write(ID_ADDR + i, id[i]);
    } else {
      EEPROM.write(ID_ADDR + i, '\0');
    }
  }

  EEPROM.commit();

  Serial.println("Device ID saved to EEPROM successfully.");
}

String readID() {
  if (EEPROM.read(MAGIC_ADDR) != MAGIC_VALUE) {
    return "";
  }

  char id[MAX_ID_LEN + 1];

  for (int i = 0; i < MAX_ID_LEN; i++) {
    id[i] = EEPROM.read(ID_ADDR + i);
  }

  id[MAX_ID_LEN] = '\0';

  String storedID = String(id);
  storedID.trim();

  if (isValidID(storedID)) {
    return storedID;
  }

  return "";
}

String askForID() {
  for (int attempt = 1; attempt <= MAX_ID_ATTEMPTS; attempt++) {
    Serial.println();
    Serial.print("Attempt ");
    Serial.print(attempt);
    Serial.println(" of 10");
    Serial.println("Please enter Device ID like HAMS001 within 50 seconds:");

    unsigned long startTime = millis();

    while (millis() - startTime < ID_WAIT_MS) {
      if (Serial.available()) {
        String inputID = Serial.readStringUntil('\n');
        inputID.trim();

        if (isValidID(inputID)) {
          Serial.println("Correct Device ID received: " + inputID);
          saveID(inputID);
          return inputID;
        } else {
          Serial.println("Invalid ID. Please enter like HAMS001");
        }
      }

      delay(100);
    }

    Serial.println("No valid ID received in this attempt.");
  }

  return "";
}

// ================= GENERATION / SEQUENCE =================

void loadGenerationAndSequence() {
  EEPROM.get(GEN_ADDR, generationNo);

  if (generationNo == 0xFFFFFFFF) {
    generationNo = 0;
  }

  esp_sleep_wakeup_cause_t wakeup_reason = esp_sleep_get_wakeup_cause();

  if (wakeup_reason == ESP_SLEEP_WAKEUP_TIMER && rtcValid == true) {
    Serial.println("Deep sleep wakeup detected.");
    sequenceNo++;
  } else {
    Serial.println("Power restart detected.");

    generationNo++;

    EEPROM.put(GEN_ADDR, generationNo);
    EEPROM.commit();

    sequenceNo = 0;
    rtcValid = true;
  }
}

// ================= TEMPERATURE LOGIC =================

String getTempStatus(float temp) {
  if (temp >= 28 && temp <= 50) return "Moderate";
  else if (temp > 50 && temp < 72) return "Warning Increasing Temp";
  else if (temp >= 72 && temp < 80) return "Critical";
  else if (temp >= 80 && temp < 100) return "High Temp";
  else if (temp >= 100) return "Very High Temp";
  else return "Low";
}

String getTempState(float temp) {
  if (temp >= 28 && temp <= 50) return "Normal";
  else if (temp > 50 && temp < 72) return "Increasing";
  else if (temp >= 72 && temp < 80) return "Critical";
  else if (temp >= 80 && temp < 100) return "High";
  else if (temp >= 100) return "Very High";
  else return "Normal";
}

// ================= ADS1115 =================

bool initADS1115() {
  for (int i = 1; i <= 2; i++) {
    Serial.print("Checking ADS1115 attempt ");
    Serial.println(i);

    if (ads.begin(0x48)) {
      Serial.println("ADS1115 found.");
      ads.setGain(GAIN_ONE);
      return true;
    }

    Serial.println("ADS1115 not found. Retrying...");
    delay(1000);
  }

  return false;
}

// ================= LORA MODE CONTROL =================

void loraNormalMode() {
  digitalWrite(LORA_M0, LOW);
  digitalWrite(LORA_M1, LOW);
  delay(200);
  Serial.println("LoRa Normal Mode active. M0=LOW, M1=LOW");
}

void loraSleepMode() {
  digitalWrite(LORA_M0, HIGH);
  digitalWrite(LORA_M1, HIGH);
  delay(200);
  Serial.println("LoRa Sleep / Configuration Mode active. M0=HIGH, M1=HIGH");
}

void sendLoRa(String packet) {
  loraNormalMode();

  Serial.println();
  Serial.println("LoRa TX Packet:");
  Serial.println(packet);

  LoRaSerial.println(packet);
  LoRaSerial.flush();

  delay(LORA_WAIT_MS);

  Serial.println("LoRa data sent.");

  loraSleepMode();
}

// ================= SERIAL PRINT =================

void printHAMSData(
  String deviceID,
  uint32_t genNo,
  uint32_t seqNo,
  unsigned long timeSec,
  float temp,
  String status,
  String tempState,
  float resistance,
  float ptVoltage,
  int16_t tempADC,
  float batAdsVoltage,
  float batteryVoltage,
  int16_t batteryADC,
  String packet
) {
  Serial.println();
  Serial.println("========== HAMS DATA ==========");
  Serial.println("Device ID           : " + deviceID);
  Serial.println("Generation No       : " + String(genNo));
  Serial.println("Sequence No         : " + String(seqNo));
  Serial.println("Wake Time           : " + String(timeSec) + " sec");
  Serial.println("Temperature         : " + String(temp, 2) + " C");
  Serial.println("Temperature Status  : " + status);
  Serial.println("Temperature State   : " + tempState);
  Serial.println("PT1000 Resistance   : " + String(resistance, 2) + " Ohm");
  Serial.println("PT1000 Voltage      : " + String(ptVoltage, 4) + " V");
  Serial.println("Temperature ADC     : " + String(tempADC));
  Serial.println("Battery ADS Voltage : " + String(batAdsVoltage, 4) + " V");
  Serial.println("Battery Voltage     : " + String(batteryVoltage, 2) + " V");
  Serial.println("Battery ADC         : " + String(batteryADC));
  Serial.println("--------------------------------");
  Serial.println("Final LoRa Packet:");
  Serial.println(packet);
  Serial.println("================================");
}

// ================= DEEP SLEEP =================

void goToSleep() {
  Serial.println();
  Serial.println("ESP32 going to deep sleep for 15 minutes...");
  Serial.flush();

  delay(1000);

  esp_sleep_enable_timer_wakeup(SLEEP_TIME_US);
  esp_deep_sleep_start();
}

// ================= SETUP =================

void setup() {
  Serial.begin(115200);
  Serial.setTimeout(1000);
  delay(2000);

  EEPROM.begin(EEPROM_SIZE);

  WiFi.mode(WIFI_OFF);
  btStop();

  pinMode(LORA_M0, OUTPUT);
  pinMode(LORA_M1, OUTPUT);

  loraNormalMode();

  LoRaSerial.begin(9600, SERIAL_8N1, LORA_RX, LORA_TX);

  Serial.println();
  Serial.println("ESP32-WROOM Wake Up - HAMS GEN SEQ CODE");

  loadGenerationAndSequence();

  DEVICE_ID = readID();

  if (DEVICE_ID == "") {
    Serial.println("Device ID not found in EEPROM.");

    DEVICE_ID = askForID();

    if (DEVICE_ID == "") {
      DEVICE_ID = "NO_ID";
      Serial.println("ID not received after 10 attempts.");

      sendLoRa(DEVICE_ID + ",ID_ERROR");
      goToSleep();
    }
  } else {
    Serial.println("Device ID Found from EEPROM: " + DEVICE_ID);
  }

  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(100000);

  if (!initADS1115()) {
    Serial.println("ADS1115 failed.");

    sendLoRa(DEVICE_ID + ",ADS_ERROR");
    goToSleep();
  }

  delay(READ_WAIT_MS);

  int16_t temp_adc = ads.readADC_SingleEnded(0);
  int16_t battery_adc = ads.readADC_SingleEnded(1);

  float pt_voltage = ads.computeVolts(temp_adc);
  float bat_ads_voltage = ads.computeVolts(battery_adc);
  float battery_voltage = bat_ads_voltage * BAT_DIVIDER_FACTOR;

  float Rpt1000 = 0.0;
  float temp = 0.0;

  if (temp_adc > 0 && pt_voltage > 0.01 && pt_voltage < VCC) {
    Rpt1000 = (pt_voltage * R_FIXED) / (VCC - pt_voltage);

    float discriminant = (A * A) - (4.0 * B * (1.0 - (Rpt1000 / R0)));

    if (discriminant >= 0) {
      temp = (-A + sqrt(discriminant)) / (2.0 * B);
      temp += TEMP_OFFSET;
    }
  }

  if (temp < 0) temp = 0;
  if (temp > 800) temp = 800;

  String status = getTempStatus(temp);
  String tempState = getTempState(temp);

  String data = DEVICE_ID + "," +
                String(generationNo) + "," +
                String(sequenceNo) + "," +
                String(millis() / 1000) + "," +
                String(temp, 2) + "," +
                status + "," +
                tempState + "," +
                String(Rpt1000, 2) + "," +
                String(pt_voltage, 4) + "," +
                String(temp_adc) + "," +
                String(bat_ads_voltage, 4) + "," +
                String(battery_voltage, 2) + "," +
                String(battery_adc);

  printHAMSData(
    DEVICE_ID,
    generationNo,
    sequenceNo,
    millis() / 1000,
    temp,
    status,
    tempState,
    Rpt1000,
    pt_voltage,
    temp_adc,
    bat_ads_voltage,
    battery_voltage,
    battery_adc,
    data
  );

  sendLoRa(data);

  goToSleep();
}

void loop() {
  // Nothing here. ESP32 works in setup(), sends data, then goes to deep sleep.
}
