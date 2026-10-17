
#include <ESP8266WiFi.h>
#include <WiFiClientSecureBearSSL.h>
#include <PubSubClient.h>
#include <time.h>
#include <stdlib.h>

// =====================================================
// STM8 UART / ACK
// =====================================================
#define STM8_BAUD 9600
#define ACK_PIN   12       // GPIO12 / D6

// STM8 TX -> ESP8266 GPIO3 (UART0 RX)
// ESP8266 GPIO1 (UART0 TX) -> STM8 RX
// ESP8266 GPIO12 -> STM8 ACK input

// =====================================================
// WIFI
// =====================================================
const char* WIFI_SSID     = "SANIYA";
const char* WIFI_PASSWORD = "Saniya@1310";

// =====================================================
// AWS IOT CORE
// =====================================================
const char* AWS_ENDPOINT =
    "a1vddjuckiz90j-ats.iot.ap-south-1.amazonaws.com";

const uint16_t AWS_PORT = 8883;
const char* AWS_REGION = "ap-south-1";
const char* AWS_THING_NAME = "ACP_01_T";
const char* AWS_CLIENT_ID = "ACP_01_T";
const char* AWS_TOPIC = "Acp_trail";

// =====================================================
// CERTIFICATES
// Keep your verified Amazon Root CA certificate.
// =====================================================
// CA1 CERTIFICATE
static const char AWS_ROOT_CA[] PROGMEM = R"EOF(
-----BEGIN CERTIFICATE-----
MIIDQTCCAimgAwIBAgITBmyfz5m/jAo54vB4ikPmljZbyjANBgkqhkiG9w0BAQsF
ADA5MQswCQYDVQQGEwJVUzEPMA0GA1UEChMGQW1hem9uMRkwFwYDVQQDExBBbWF6
b24gUm9vdCBDQSAxMB4XDTE1MDUyNjAwMDAwMFoXDTM4MDExNzAwMDAwMFowOTEL
MAkGA1UEBhMCVVMxDzANBgNVBAoTBkFtYXpvbjEZMBcGA1UEAxMQQW1hem9uIFJv
b3QgQ0EgMTCCASIwDQYJKoZIhvcNAQEBBQADggEPADCCAQoCggEBALJ4gHHKeNXj
ca9HgFB0fW7Y14h29Jlo91ghYPl0hAEvrAIthtOgQ3pOsqTQNroBvo3bSMgHFzZM
9O6II8c+6zf1tRn4SWiw3te5djgdYZ6k/oI2peVKVuRF4fn9tBb6dNqcmzU5L/qw
IFAGbHrQgLKm+a/sRxmPUDgH3KKHOVj4utWp+UhnMJbulHheb4mjUcAwhmahRWa6
VOujw5H5SNz/0egwLX0tdHA114gk957EWW67c4cX8jJGKLhD+rcdqsq08p8kDi1L
93FcXmn/6pUCyziKrlA4b9v7LWIbxcceVOF34GfID5yHI9Y/QCB/IIDEgEw+OyQm
jgSubJrIqg0CAwEAAaNCMEAwDwYDVR0TAQH/BAUwAwEB/zAOBgNVHQ8BAf8EBAMC
AYYwHQYDVR0OBBYEFIQYzIU07LwMlJQuCFmcx7IQTgoIMA0GCSqGSIb3DQEBCwUA
A4IBAQCY8jdaQZChGsV2USggNiMOruYou6r4lK5IpDB/G/wkjUu0yKGX9rbxenDI
U5PMCCjjmCXPI6T53iHTfIUJrU6adTrCC2qJeHZERxhlbI1Bjjt/msv0tadQ1wUs
N+gDS63pYaACbvXy8MWy7Vu33PqUXHeeE6V/Uq2V8viTO96LXFvKWlJbYK8U90vv
o/ufQJVtMVT8QtPHRh8jrdkPSHCa2XV4cdFyQzR1bldZwgJcJmApzyMZFo6IQ6XU
5MsI+yMRQ+hDKXJioaldXgjUkK642M4UwtBV8ob2xJNDd2ZhwLnoQdeXeGADbkpy
rqXRfboQnoZsG4q5WTP468SQvvG5
-----END CERTIFICATE-----
)EOF";

// DEVICE CERTIFICATE
static const char AWS_DEVICE_CERT[] PROGMEM = R"EOF(
-----BEGIN CERTIFICATE-----
MIIDWTCCAkGgAwIBAgIUVbCyiIjjEVHNcVew2+07LGhyJyEwDQYJKoZIhvcNAQEL
BQAwTTFLMEkGA1UECwxCQW1hem9uIFdlYiBTZXJ2aWNlcyBPPUFtYXpvbi5jb20g
SW5jLiBMPVNlYXR0bGUgU1Q9V2FzaGluZ3RvbiBDPVVTMB4XDTI2MTAwOTA2NTU0
OFoXDTQ5MTIzMTIzNTk1OVowHjEcMBoGA1UEAwwTQVdTIElvVCBDZXJ0aWZpY2F0
ZTCCASIwDQYJKoZIhvcNAQEBBQADggEPADCCAQoCggEBAMX4B4MLPYvpdVlvpURR
s8xdImsxkZi2DJK80KbqWoGtzYfkHPai/u4ME77Onr/wL59M1Xr39AH20b64ByP0
BSVXEYqeJLhCWqyj5XuJF4DTl3JPvUC+yF+igLq2JVy1QmxVevvILD1RfUC80QpK
xlpXk640Zdl/bDLJpKlDTgcfhnkQ195IYWksO5mWGDmtqfkesO6Rzz7gseYIPO1b
h7mLhkWXtTqgfvS0NyejQrq7TeeyVbcLGbcE4qHn9v7jqqyBIU8G0g3kO82htI8Q
wH5JHprNly60kLQNZ/RESB418kfCIAyJNkv3tL8FZYYo6PWYWKDUI4r4AVcDNQcL
Ix8CAwEAAaNgMF4wHwYDVR0jBBgwFoAUlDXGTYcXtXAiFe87+JhZV50P1M0wHQYD
VR0OBBYEFEbInS11Crxzi+SHVou+ziHtVeynMAwGA1UdEwEB/wQCMAAwDgYDVR0P
AQH/BAQDAgeAMA0GCSqGSIb3DQEBCwUAA4IBAQAk0EXwCv3kcyHDTXRdNKkiP8c7
lmO6Zed/8ygZr88iTbAyLBdBfqu3iajNsZqsYeeyGKiZ9nZtFm5AwUgGxb8v5Gkc
+zgb0C1YVmSkVU6P3Wb+pyHxuSi4lWHt2bhTCJ0gonLJ8bZQqmoJj1aqWsZ+Yhcq
1wx5A7uGpMF87/VtzPiCDoNtL+3Kv/lZ9nBL3VCuYgO37HBb13ZoopO6ekKknljS
Rt1TNBKbxOWIy6OAnJSM3twHTpVeBBLkRKK2kywiQD5Mk5NfaSsLqyOc0tjTJhB9
Ebc0/0IzvB1x4Y6pdz5W1a4O9/D9btgNRrpHhiDDRbf5vTfJxGgJd0KhDvTP
-----END CERTIFICATE-----
)EOF";

// PRIVATE KEY
static const char AWS_PRIVATE_KEY[] PROGMEM = R"EOF(
-----BEGIN RSA PRIVATE KEY-----
MIIEowIBAAKCAQEAxfgHgws9i+l1WW+lRFGzzF0iazGRmLYMkrzQpupaga3Nh+Qc
9qL+7gwTvs6ev/Avn0zVevf0AfbRvrgHI/QFJVcRip4kuEJarKPle4kXgNOXck+9
QL7IX6KAurYlXLVCbFV6+8gsPVF9QLzRCkrGWleTrjRl2X9sMsmkqUNOBx+GeRDX
3khhaSw7mZYYOa2p+R6w7pHPPuCx5gg87VuHuYuGRZe1OqB+9LQ3J6NCurtN57JV
twsZtwTioef2/uOqrIEhTwbSDeQ7zaG0jxDAfkkems2XLrSQtA1n9ERIHjXyR8Ig
DIk2S/e0vwVlhijo9ZhYoNQjivgBVwM1BwsjHwIDAQABAoIBAEdyMCPXFqs74iIY
7OgvJFiI9DcDeKxIZ1k903+p7GgItbhpVxqb0K1Qpn+iSiCzKjyvmgv7GJDs5t2R
xOHw2zqSpb4FPPNS3y6XJ+bhnx3bPzj+Fisbr2z0VMkNm4ZN1F8MqonbwDuRAUcv
3bF9MwC/woiIWImaNw5NP6Pmqm5fCnguCPJ5SPx4QRmxlM4naZwQoirgmxsX8i5b
vwTE6N8eRILIdBQmVkhQcQo8t1V2/c96/hbvqn8Mns7mx38MIxiDpb/GFqT9QPhj
iX9S8teTOjXS38ZM7842gt1Q+kVZIIjpOp1L8JP5swMsV4mxQ1R84WUkEvx5jJYi
GOgjR6ECgYEA/4lLCU84E9IRwTGb1Fk4SDZfW3vmj8NQA90IZ8SA46lkie7gKxEz
zgSNKitn6Ulvesx8kv+neXsSZO7CeT4/A5mx9I/XSt2RHuYNdzEaVQFEipB7zFWj
qPNQDHEYU5KuX+XTsRCTwfhlStrFUmKMrIkmqJh8ijnUMG6Z9smyq9UCgYEAxlP+
bH3O7zB7cNEnb/8m5EF9PgfrCuIYvY2LyeW/m32RD6L9xo0P7Zuy656cOa8jhn3e
jHKTRw/Az+vNOzBu8b/T03reaVNZ2HtLT7x4MXJNQBS94ZuqtSahNFUx2QckRvwg
h8O8J9N7eoHZWdw1h9LVSamkL3TD81+ogbYikSMCgYBX09tbdsPiZBhAG4ngoU2r
3CxIKDyles68lTK3X52hIe5xTg30H3R7waq3LLYJQ3kybqf+aiooobk/waRLwa4s
0Z2NXgb0L1Ualp1YMyNGxinFqkUyhNi8T+xaamCfENIoGbj5qaXvTC2cXbbmSwLo
pjcISWi8pYWdo9X9MXPchQKBgBONYk7V1FnWYMUNiaLL98yW/D7qTuzCv4eodbiQ
0uQEbBGrkvNJIuHc8LWz7FjvgEQZEqCsBwMBdZPJ/nCwZK+mpr55pYWitv/Vn+Yb
gYn2Z9FCejnMu/ah+VCMeZ6YyqXI43ge/uS6P7kjJgdq40ghq+9YLxySmWLb8mPf
TecbAoGBALPsCRqcsQQwVWRVVhQcN/VfNJLoMO5Kz1+MC5UaJ4c6Yd37kqik/MDh
HeWTCrrq6Qs33Ubfz6l2wRKW7P8MNhC0O/Q+mTuVBw2tV+NqPXHqksaJ7xRfE4UP
b5IbOPhJa8Nmp4EdzbY8A0tvyr4peNnxvG7TDICkWFWAN/zEzGFX
-----END RSA PRIVATE KEY-----

)EOF";

// =====================================================
// TLS / MQTT
// =====================================================
BearSSL::WiFiClientSecure secureClient;
PubSubClient mqtt(secureClient);

BearSSL::X509List* rootCA = nullptr;
BearSSL::X509List* deviceCert = nullptr;
BearSSL::PrivateKey* privateKey = nullptr;

String packet;
bool collecting = false;

// =====================================================
// WIFI CONNECTION
// =====================================================
bool connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) {
    return true;
  }

  Serial.println("Connecting to Wi-Fi...");
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  unsigned long start = millis();

  while (WiFi.status() != WL_CONNECTED &&
         millis() - start < 20000UL) {
    delay(250);
    yield();
  }

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Wi-Fi connection failed");
    return false;
  }

  Serial.print("Wi-Fi connected. IP: ");
  Serial.println(WiFi.localIP());
  return true;
}

// =====================================================
// TLS CONFIGURATION
// =====================================================
bool setupTLS() {
  if (rootCA == nullptr) {
    rootCA = new BearSSL::X509List(AWS_ROOT_CA);
    deviceCert = new BearSSL::X509List(AWS_DEVICE_CERT);
    privateKey = new BearSSL::PrivateKey(AWS_PRIVATE_KEY);
  }

  secureClient.setTrustAnchors(rootCA);
  secureClient.setClientRSACert(deviceCert, privateKey);
  secureClient.setTimeout(15000);

  mqtt.setServer(AWS_ENDPOINT, AWS_PORT);
  mqtt.setBufferSize(2048);
  mqtt.setKeepAlive(60);
  mqtt.setSocketTimeout(15);

  return true;
}

// =====================================================
// NTP TIME FOR TLS
// =====================================================
bool syncClock() {
  configTime(0, 0, "pool.ntp.org", "time.nist.gov");

  unsigned long start = millis();

  while (time(nullptr) < 1700000000 &&
         millis() - start < 20000UL) {
    delay(250);
    yield();
  }

  if (time(nullptr) < 1700000000) {
    Serial.println("NTP time synchronization failed");
    return false;
  }

  Serial.println("NTP time synchronized");
  return true;
}

// =====================================================
// AWS CONNECTION
// =====================================================
bool connectAWS() {
  if (mqtt.connected()) {
    return true;
  }

  if (!connectWiFi()) {
    return false;
  }

  Serial.println("Connecting to AWS IoT Core...");

  if (mqtt.connect(AWS_CLIENT_ID)) {
    Serial.println("AWS MQTT connected");
    Serial.print("Thing: ");
    Serial.println(AWS_THING_NAME);
    Serial.print("Region: ");
    Serial.println(AWS_REGION);
    Serial.print("Topic: ");
    Serial.println(AWS_TOPIC);
    return true;
  }

  Serial.print("AWS MQTT connection failed: ");
  Serial.println(mqtt.state());
  return false;
}

// =====================================================
// JSON STRING ESCAPING
// =====================================================
String jsonEscape(const String& value) {
  String result;
  result.reserve(value.length() + 8);

  for (size_t i = 0; i < value.length(); i++) {
    char c = value[i];

    if (c == '"' || c == '\\') {
      result += '\\';
      result += c;
    } else if (c == '\n') {
      result += "\\n";
    } else if (c == '\r') {
      result += "\\r";
    } else if (c == '\t') {
      result += "\\t";
    } else if ((uint8_t)c >= 32) {
      result += c;
    }
  }

  return result;
}

// =====================================================
// CONVERT STM8 KEY=VALUE PACKET INTO JSON
// Input:
// <START>,ID=ACP_01,S1_R1=70,...,STATUS=ACP TRIGGERED,...,END>
// =====================================================
bool convertToJSON(String data, String& json) {
  data.trim();

  if (!data.startsWith("<START>") ||
      !data.endsWith("END>")) {
    Serial.println("Invalid packet framing");
    return false;
  }

  // Remove packet framing markers.
  data.remove(0, 7);
  data.remove(data.length() - 4);

  data.trim();

  if (data.startsWith(",")) {
    data.remove(0, 1);
  }

  bool first = true;
  bool foundID = false;
  json = "{";

  while (data.length() > 0) {
    int comma = data.indexOf(',');

    String item;

    if (comma >= 0) {
      item = data.substring(0, comma);
      data.remove(0, comma + 1);
    } else {
      item = data;
      data = "";
    }

    item.trim();

    if (item.length() == 0) {
      continue;
    }

    int equal = item.indexOf('=');

    if (equal <= 0) {
      Serial.println("Invalid key=value field");
      return false;
    }

    String key = item.substring(0, equal);
    String value = item.substring(equal + 1);

    key.trim();
    value.trim();

    if (key.length() == 0 || value.length() == 0) {
      Serial.println("Empty JSON field");
      return false;
    }

    if (key == "ID") {
      if (value != "ACP_01") {
        Serial.println("Unexpected STM8 device ID");
        return false;
      }
      foundID = true;
    }

    if (!first) {
      json += ",";
    }
    first = false;

    json += "\"";
    json += jsonEscape(key);
    json += "\":";

    // ID and STATUS are strings.
    if (key == "ID" || key == "STATUS") {
      json += "\"";
      json += jsonEscape(value);
      json += "\"";
    } else {
      // All remaining fields must be unsigned integers.
      for (size_t i = 0; i < value.length(); i++) {
        if (value[i] < '0' || value[i] > '9') {
          Serial.print("Invalid numeric value for ");
          Serial.println(key);
          return false;
        }
      }

      json += value;
    }
  }

  json += "}";

  if (!foundID) {
    Serial.println("Device ID missing");
    return false;
  }

  Serial.println("Converted JSON:");
  Serial.println(json);

  return true;
}

// =====================================================
// ACK TO STM8
// ACK is sent only when the MQTT publish call succeeds.
// GPIO12 must connect to the STM8 ACK input.
// =====================================================
void sendACK() {
  digitalWrite(ACK_PIN, HIGH);
  delay(100);
  digitalWrite(ACK_PIN, LOW);

  Serial.println("ACK pulse sent to STM8");
}

// =====================================================
// PUBLISH JSON TO AWS
// =====================================================
bool publishToAWS(const String& json) {
  if (!connectAWS()) {
    Serial.println("AWS unavailable; no ACK");
    return false;
  }

  Serial.println("Publishing JSON to AWS...");
  Serial.print("Topic: ");
  Serial.println(AWS_TOPIC);
  Serial.println(json);

  bool ok = mqtt.publish(
      AWS_TOPIC,
      (const uint8_t*)json.c_str(),
      json.length(),
      false
  );

  if (!ok) {
    Serial.println("MQTT publish failed");
    return false;
  }

  Serial.println("MQTT publish accepted by client");

  // Process pending MQTT traffic.
  unsigned long start = millis();

  while (millis() - start < 300) {
    mqtt.loop();
    delay(10);
    yield();
  }

  return true;
}

// =====================================================
// PROCESS COMPLETE STM8 PACKET
// =====================================================
void processPacket(String data) {
  Serial.println();
  Serial.println("========== STM8 PACKET ==========");
  Serial.println(data);

  String json;

  if (!convertToJSON(data, json)) {
    Serial.println("Packet rejected; no ACK");
    return;
  }

  if (publishToAWS(json)) {
    Serial.println("Publish call succeeded");
    sendACK();
  } else {
    Serial.println("Publish unsuccessful; no ACK");
  }

  Serial.println("=================================");
}

// =====================================================
// UART RECEIVER
// =====================================================
void readSTM8() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();

    if (c == '<') {
      packet = "<";
      collecting = true;
      continue;
    }

    if (!collecting) {
      continue;
    }

    packet += c;

    if (packet.length() > 1200) {
      Serial.println("Packet overflow; buffer cleared");
      packet = "";
      collecting = false;
      continue;
    }

    if (packet.endsWith("END>")) {
      String completed = packet;
      packet = "";
      collecting = false;

      processPacket(completed);
    }
  }
}

// =====================================================
// SETUP
// =====================================================
void setup() {
  pinMode(ACK_PIN, OUTPUT);
  digitalWrite(ACK_PIN, LOW);

  // Hardware UART0, 9600 baud.
  Serial.begin(STM8_BAUD);
  delay(1500);

  Serial.println();
  Serial.println("ACP_01_T ESP8266 RECEIVER");
  Serial.println("UART0: 9600 baud");
  Serial.println("AWS Region: ap-south-1");
  Serial.println("Thing: ACP_01_T");
  Serial.println("Topic: Acp_trail");

  if (connectWiFi()) {
    if (syncClock()) {
      setupTLS();
      connectAWS();
    }
  }

  Serial.println("Waiting for STM8 packets...");
}

// =====================================================
// MAIN LOOP
// =====================================================
void loop() {
  readSTM8();

  if (mqtt.connected()) {
    mqtt.loop();
  }

  yield();
}
