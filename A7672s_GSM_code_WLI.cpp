
#define TINY_GSM_MODEM_SIM7600
#define TINY_GSM_RX_BUFFER 512

#include <Arduino.h>
#include <SoftwareSerial.h>
#include <TinyGsmClient.h>

// Existing PCB modem UART mapping:
// ESP8266 GPIO4 (RX) <- A7672S TX
// ESP8266 GPIO5 (TX) -> A7672S RX
#define GSM_RX_PIN 4
#define GSM_TX_PIN 5

#define DEBUG_BAUD 115200

SoftwareSerial gsmSerial(GSM_RX_PIN, GSM_TX_PIN);
TinyGsm modem(gsmSerial);

const uint32_t baudRates[] = {
  115200, 9600, 19200, 38400, 57600, 4800
};

uint32_t workingBaud = 0;

void clearModemInput() {
  unsigned long started = millis();

  while (millis() - started < 250) {
    while (gsmSerial.available()) {
      gsmSerial.read();
    }
    delay(1);
  }
}

bool testATAtBaud(uint32_t baud) {
  gsmSerial.end();
  delay(200);

  gsmSerial.begin(baud);
  delay(300);
  clearModemInput();

  Serial.print("\nTesting modem baud: ");
  Serial.println(baud);

  for (int attempt = 0; attempt < 3; attempt++) {
    gsmSerial.println("AT");

    unsigned long started = millis();
    String response;

    while (millis() - started < 1500) {
      while (gsmSerial.available()) {
        char c = (char)gsmSerial.read();
        response += c;
        if (response.length() > 250) {
          response.remove(0, 100);
        }
      }
      delay(1);
      yield();
    }

    Serial.print("Response: ");
    if (response.length()) {
      Serial.println(response);
    } else {
      Serial.println("[no response]");
    }

    if (response.indexOf("OK") >= 0) {
      workingBaud = baud;
      return true;
    }
  }

  return false;
}

void setup() {
  Serial.begin(DEBUG_BAUD);
  delay(1500);

  Serial.println();
  Serial.println("================================");
  Serial.println("ESP8266 + A7672S GSM AT TEST");
  Serial.println("================================");

  Serial.println("Searching for modem baud rate...");

  for (size_t i = 0;
       i < sizeof(baudRates) / sizeof(baudRates[0]);
       i++) {
    if (testATAtBaud(baudRates[i])) {
      break;
    }
  }

  if (workingBaud == 0) {
    Serial.println("\nERROR: No AT response at tested baud rates.");
    Serial.println("Check modem power, UART wiring, and baud rate.");
    return;
  }

  Serial.print("\nMODEM RESPONDS AT: ");
  Serial.println(workingBaud);

  // Reinitialize TinyGSM using the detected baud.
  gsmSerial.end();
  delay(200);
  gsmSerial.begin(workingBaud);
  delay(500);

  Serial.println("\nInitializing TinyGSM...");
  if (!modem.init()) {
    Serial.println("Modem initialization failed.");
    Serial.println("Check AT communication and modem startup.");
    return;
  }

  Serial.print("Modem information: ");
  Serial.println(modem.getModemInfo());

  Serial.println("\nChecking SIM status...");
  gsmSerial.println("AT+CPIN?");
  delay(1000);

  while (gsmSerial.available()) {
    Serial.write(gsmSerial.read());
  }

  Serial.println("\nChecking network registration...");
  if (modem.waitForNetwork(60000L)) {
    Serial.println("NETWORK REGISTERED");
    Serial.print("Signal quality: ");
    Serial.println(modem.getSignalQuality());
  } else {
    Serial.println("NETWORK REGISTRATION FAILED");
    Serial.println("Check SIM, antenna, coverage, and operator.");
  }

  Serial.println("\nGSM TEST FINISHED");
}

void loop() {
  // This test runs once at startup.
  delay(1000);
}
