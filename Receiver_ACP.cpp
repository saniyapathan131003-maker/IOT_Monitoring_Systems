#include <Arduino.h>
#include <ESP8266WiFi.h>
#include <WiFiClientSecureBearSSL.h>
#include <PubSubClient.h>
#include <SoftwareSerial.h>

/* =========================================================
   STM8 UART
   STM8 TX -> ESP8266 GPIO3 / RX
   STM8 RX <- ESP8266 GPIO1 / TX
   ========================================================= */

#define STM8_BAUD 9600


/* =========================================================
   A7672S UART
   A7672S TX -> ESP GPIO4
   A7672S RX <- ESP GPIO5
   ========================================================= */

#define GSM_RX 4
#define GSM_TX 5


/* =========================================================
   ACK
   ESP GPIO12 -> STM8 PB5
   ========================================================= */

#define ACK_PIN 12


/* =========================================================
   WIFI
   ========================================================= */

const char *WIFI_SSID = "SANIYA";
const char *WIFI_PASSWORD = "Saniya@1310";


/* =========================================================
   AWS IOT
   ========================================================= */

const char *AWS_ENDPOINT =
    "a1vddjuckiz90j-ats.iot.ap-south-1.amazonaws.com";

const int AWS_PORT = 8883;

const char *AWS_TOPIC = "Acp_trail";

const char *AWS_CLIENT_ID = "ACP_ESP8266";


/* =========================================================
   AWS CERTIFICATES FOR WIFI
   REPLACE THESE WITH YOUR REAL CERTIFICATES
   ========================================================= */
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
MIIDWTCCAkGgAwIBAgIUd7ZOCYKyOkBEU5fAQ5TyEtAl2vowDQYJKoZIhvcNAQEL
BQAwTTFLMEkGA1UECwxCQW1hem9uIFdlYiBTZXJ2aWNlcyBPPUFtYXpvbi5jb20g
SW5jLiBMPVNlYXR0bGUgU1Q9V2FzaGluZ3RvbiBDPVVTMB4XDTI2MTAwMjA2MTIw
NFoXDTQ5MTIzMTIzNTk1OVowHjEcMBoGA1UEAwwTQVdTIElvVCBDZXJ0aWZpY2F0
ZTCCASIwDQYJKoZIhvcNAQEBBQADggEPADCCAQoCggEBAMHYTmmy21RoPnE1RVdR
SKa389S9ZdVf+8G4dRj9MWBWege3JkU1WjSYVuJOMIEVZjqSxcYIYw3MmQNenWgT
5rwZZOzziZEeOzZPHHeGHE0GOIQ9a3WCWNvIDAsVauXQvDJsj5w0ZULLlk3exfDk
yILrmgrKSDawKssrU66Qyu2RP6n+xpjYpY5FnVqAUAd5/jkBulTDn2Tf3MxFH6d6
ih3jFoIyeBy11B/0sJ9efmuHxWzQT7l1tQQi6o3IUHPG8my2luqyq5Jom7VqMZVL
KGBfiCz3ad4PwKmx6LVejCmDs0PFnQ4T4NWHXqEXCgPOnkfK93GvVzogp7Ac1Ci2
n8UCAwEAAaNgMF4wHwYDVR0jBBgwFoAUCqpnCx1U9LB3/urWi2HLfKPlA4wwHQYD
VR0OBBYEFAJp3NR7S6buKqpzWFjsoZS+Cu0VMAwGA1UdEwEB/wQCMAAwDgYDVR0P
AQH/BAQDAgeAMA0GCSqGSIb3DQEBCwUAA4IBAQCS2qpU+DcAorVpK1Ofk/Zsxb+W
bIMyBbnKQxa9D/ZKlAK95SWpZeiUS7dj9P0VpPsQZgxlQJ1XnaZp7QoVTJfuS2Py
DWF5LpckzamRES6QCveT9p04GjOtQYtJwbLvVVhiu9F6gd4Kslh9cdnJ7xOCFFgN
TLgfmHZ5RamsRM1IBbsOb06oHb0/eiD/mxNMhf9L230PV/04JB2+yV4UIQbeNqvS
ST56TwtNx/6XkyWQDvD44ouNy2Q1tYe5LWPIcKlmlwm4cv8iWpiopPLuaiBPY79j
sErP0nHR0KS1t1snM6ekeMU2A/KKLBG+BU6+Cxv6iwvD8vg1AHysGmbLTS8j
-----END CERTIFICATE-----

)EOF";


static const char AWS_PRIVATE_KEY[] PROGMEM = R"EOF(
-----BEGIN RSA PRIVATE KEY-----
MIIEogIBAAKCAQEAwdhOabLbVGg+cTVFV1FIprfz1L1l1V/7wbh1GP0xYFZ6B7cm
RTVaNJhW4k4wgRVmOpLFxghjDcyZA16daBPmvBlk7POJkR47Nk8cd4YcTQY4hD1r
dYJY28gMCxVq5dC8MmyPnDRlQsuWTd7F8OTIguuaCspINrAqyytTrpDK7ZE/qf7G
mNiljkWdWoBQB3n+OQG6VMOfZN/czEUfp3qKHeMWgjJ4HLXUH/Swn15+a4fFbNBP
uXW1BCLqjchQc8bybLaW6rKrkmibtWoxlUsoYF+ILPdp3g/AqbHotV6MKYOzQ8Wd
DhPg1YdeoRcKA86eR8r3ca9XOiCnsBzUKLafxQIDAQABAoIBABhQJSWkxVXE7XAN
mnDlRROEJxUb3FXzAATAOg+0UikfL5cgJbCwjGvkX6Fq5TKLmJLoLd401xe3/ckq
aNvRAzO8i6gcs7h77jlVmuBy9cHDcftEKOJIQxTt9nS9bvb8Q16ftzOEbt794hBK
TNF2IKArJNsNnBkf534sJQbUKl+5jDzj9B4sa8KY3cGDKaTzMYaMNTLjsIVjG9RL
MvE8G5bqhm1Bo3mAEvKywru0Na4gGTMgfrYoWtmP9F93Xl+MwxeYLsslTTNADXLH
Dhx2aBuAYz7FiwYavO7udxNSBOmA89Y4YKZozAI0wX4676RiAd4XDQRlcxJ+SIsw
2DzKK4ECgYEA333GhNqvyIB/OPah7uF5mIq/gV0zE0ExLFOGpwCj1x/WakhDgy8o
tpkVJg5Qk9/xBAYao8a05Ud7+dOfpqnEQbxG6Aa+/4/uOqMdUlMJk00geB8MV9VV
PGzZxqOu4Hr4hRkSHCVp1ABZongC4HdZ3kz4xkSMfT1UxB6xb1u/CE0CgYEA3gqU
KUKQsrqqGlGm+GDGRL0nUohqsfn2KDTBu+iE1AjyOKDUZlE5gxfTCg3JO5IC6Cr8
X2CIOTEKqfywhDONQk4rd3nPyKUCJLB+bMpGbEetObA2wXIQQOplFq1esK38wBGn
tEVtTqOTBfCiHluyODDbkB578Em9t6wI/3iOMVkCgYBk2hcpgJ3udr3ycKlmaO08
PvBoaixQNg0AmbibyBgnTcCuOWnt2uweajo28CLAeEAEttRyr4qWJIn3lN3okZd0
qoe80L6ECOlSIKVsrvgVNqq+ShSB1k0edWhY0ShrOFLJjSS0+tUky/um600xCerN
/CIPJoPXSEPmNIuRWu97yQKBgHgv3bbfsxcrdvu8CtcS+v8mK+y+rpIbrSRiOiOO
XqevF/2TAKVJfgn5kWA1yiEWjcBB1E2EIPhkFVOh1aIZjXLAgUKwisoelyRo7GXS
r3/Y5Gj/ewQGy8l3lrRJr6GO6+rDI7WuhtY0MFbcw8QO+k70E0TVW1zbbXfIBS7T
gJQxAoGAZShh5kWp1dXEIaaQYCXY8HvXgl8DqQu2u8EfPuFBR6tgQadP8D8OOO1x
W0vVKeqD+PBPjGCfun7vp/9ZmnTcrnVomWE81cpFpQB2SCHMZGyk4BJq/BoR3fj2
w3Zc1zEjy351hIOkGTDKXyr6xHQbKLh5l8d3EInszpjrBeg1J+8=
-----END RSA PRIVATE KEY-----

)EOF";


/* =========================================================
   A7672S CERTIFICATE FILENAMES
   These files must already exist in A7672S storage.
   ========================================================= */

const char *GSM_CA_FILE   = "aws_ca.pem";
const char *GSM_CERT_FILE = "aws_cert.pem";
const char *GSM_KEY_FILE  = "aws_key.pem";


/* =========================================================
   GSM APN LIST
   ========================================================= */

const char *APN_LIST[] =
{
    "jionet",
    "airtelgprs.com",
    "www",
    "bsnlnet"
};

const uint8_t APN_COUNT = 4;


/* =========================================================
   OBJECTS
   ========================================================= */

SoftwareSerial gsmSerial(GSM_RX, GSM_TX);

BearSSL::WiFiClientSecure wifiClient;
PubSubClient wifiMqtt(wifiClient);


/* =========================================================
   GLOBALS
   ========================================================= */

uint32_t gsmBaud = 9600;

bool gsmAvailable = false;
bool wifiAvailable = false;

String stm8Packet = "";


/* =========================================================
   DEBUG
   ========================================================= */

void debugLine(const char *text)
{
    Serial.println(text);
}


/* =========================================================
   CLEAR GSM BUFFER
   ========================================================= */

void clearGSMBuffer()
{
    while (gsmSerial.available())
    {
        gsmSerial.read();
    }
}


/* =========================================================
   READ GSM RESPONSE
   ========================================================= */

String readGSMResponse(uint32_t timeout)
{
    String response = "";

    unsigned long start = millis();

    while ((millis() - start) < timeout)
    {
        while (gsmSerial.available())
        {
            char c = gsmSerial.read();

            response += c;

            Serial.write(c);
        }

        delay(2);
    }

    return response;
}


/* =========================================================
   SEND AT COMMAND
   ========================================================= */

bool sendAT(
    const String &command,
    const char *expected,
    uint32_t timeout
)
{
    clearGSMBuffer();

    Serial.print("\r\nGSM << ");
    Serial.println(command);

    gsmSerial.println(command);

    String response = readGSMResponse(timeout);

    if (response.indexOf(expected) >= 0)
    {
        return true;
    }

    return false;
}


/* =========================================================
   A7672S BAUD DETECTION
   ========================================================= */

bool detectGSMBaud()
{
    uint32_t baudList[] =
    {
        9600,
        115200
    };

    for (uint8_t i = 0; i < 2; i++)
    {
        gsmBaud = baudList[i];

        Serial.print("\r\nTrying A7672S baud = ");
        Serial.println(gsmBaud);

        gsmSerial.end();

        delay(100);

        gsmSerial.begin(gsmBaud);

        delay(500);

        clearGSMBuffer();

        for (uint8_t n = 0; n < 3; n++)
        {
            gsmSerial.println("AT");

            delay(500);

            String response = "";

            while (gsmSerial.available())
            {
                response += (char)gsmSerial.read();
            }

            if (response.indexOf("OK") >= 0)
            {
                Serial.print("A7672S AT OK at baud = ");
                Serial.println(gsmBaud);

                return true;
            }
        }
    }

    Serial.println("A7672S AT FAILED at 9600 and 115200");

    return false;
}


/* =========================================================
   GSM BASIC CHECK
   ========================================================= */

bool gsmBasicCheck()
{
    Serial.println();
    Serial.println("========================================");
    Serial.println("A7672S / eSIM CHECK");
    Serial.println("========================================");

    if (!detectGSMBaud())
    {
        Serial.println("A7672S AT TEST FAILED");
        return false;
    }

    Serial.println("A7672S AT TEST = OK");


    /* SIM / eSIM */

    if (!sendAT(
            "AT+CPIN?",
            "READY",
            3000))
    {
        Serial.println("SIM/eSIM NOT READY");
        return false;
    }

    Serial.println("SIM/eSIM READY");


    /* Signal */

    sendAT(
        "AT+CSQ",
        "OK",
        3000);


    /* Network registration */

    bool registered = false;

    for (uint8_t i = 0; i < 10; i++)
    {
        clearGSMBuffer();

        gsmSerial.println("AT+CEREG?");

        String response =
            readGSMResponse(2000);

        if (response.indexOf(",1") >= 0 ||
            response.indexOf(",5") >= 0)
        {
            registered = true;
            break;
        }

        delay(1000);
    }


    if (!registered)
    {
        Serial.println("LTE NETWORK NOT REGISTERED");

        return false;
    }

    Serial.println("LTE NETWORK REGISTERED");

    return true;
}


/* =========================================================
   SET APN
   ========================================================= */

bool setupPDP(const char *apn)
{
    Serial.print("Trying APN: ");
    Serial.println(apn);

    sendAT(
        "AT+CGATT=0",
        "OK",
        5000);

    String cmd;

    cmd = "AT+CGDCONT=1,\"IP\",\"";
    cmd += apn;
    cmd += "\"";

    if (!sendAT(
            cmd,
            "OK",
            5000))
    {
        return false;
    }


    if (!sendAT(
            "AT+CGATT=1",
            "OK",
            15000))
    {
        return false;
    }


    /*
       Open PDP context.
    */

    if (!sendAT(
            "AT+NETOPEN",
            "OK",
            20000))
    {
        /*
           NETOPEN can return ERROR when already open.
           Check status.
        */
    }


    sendAT(
        "AT+NETOPEN?",
        "OK",
        5000);

    return true;
}


/* =========================================================
   SET TLS
   ========================================================= */

bool setupGSMTLS()
{
    Serial.println();
    Serial.println("Configuring A7672S TLS...");


    sendAT(
        "AT+CSSLCFG=\"sslversion\",0,3",
        "OK",
        5000);


    sendAT(
        "AT+CSSLCFG=\"authmode\",0,2",
        "OK",
        5000);


    String cmd;

    cmd = "AT+CSSLCFG=\"cacert\",0,\"";
    cmd += GSM_CA_FILE;
    cmd += "\"";

    if (!sendAT(cmd, "OK", 5000))
    {
        return false;
    }


    cmd = "AT+CSSLCFG=\"clientcert\",0,\"";
    cmd += GSM_CERT_FILE;
    cmd += "\"";

    if (!sendAT(cmd, "OK", 5000))
    {
        return false;
    }


    cmd = "AT+CSSLCFG=\"clientkey\",0,\"";
    cmd += GSM_KEY_FILE;
    cmd += "\"";

    if (!sendAT(cmd, "OK", 5000))
    {
        return false;
    }


    sendAT(
        "AT+CSSLCFG=\"enableSNI\",0,1",
        "OK",
        5000);

    return true;
}


/* =========================================================
   GSM MQTT CONNECT
   ========================================================= */

bool gsmMQTTConnect()
{
    Serial.println();
    Serial.println("========================================");
    Serial.println("GSM AWS MQTT CONNECT");
    Serial.println("========================================");


    sendAT(
        "AT+CMQTTSTOP",
        "OK",
        5000);


    if (!sendAT(
            "AT+CMQTTSTART",
            "OK",
            10000))
    {
        Serial.println("CMQTTSTART FAILED");
        return false;
    }


    String cmd;

    cmd = "AT+CMQTTACCQ=0,\"";
    cmd += AWS_CLIENT_ID;
    cmd += "\",1";

    if (!sendAT(
            cmd,
            "OK",
            5000))
    {
        Serial.println("CMQTTACCQ FAILED");
        return false;
    }


    if (!sendAT(
            "AT+CMQTTSSLCFG=0,0",
            "OK",
            5000))
    {
        Serial.println("CMQTT SSL CONFIG FAILED");
        return false;
    }


    cmd = "AT+CMQTTCONNECT=0,\"tcp://";
    cmd += AWS_ENDPOINT;
    cmd += ":8883\",60,1";

    Serial.println("Connecting AWS MQTT over GSM...");

    if (!sendAT(
            cmd,
            "OK",
            30000))
    {
        Serial.println("AWS GSM MQTT CONNECT FAILED");
        return false;
    }


    Serial.println("AWS GSM MQTT CONNECTED");

    return true;
}


/* =========================================================
   GSM MQTT PUBLISH
   ========================================================= */

bool gsmPublish(String payload)
{
    Serial.println();
    Serial.println("========================================");
    Serial.println("AWS GSM PUBLISH");
    Serial.println("========================================");


    if (!gsmMQTTConnect())
    {
        return false;
    }


    /* TOPIC */

    String cmd;

    cmd = "AT+CMQTTTOPIC=0,";
    cmd += String(strlen(AWS_TOPIC));

    if (!sendAT(
            cmd,
            ">",
            5000))
    {
        Serial.println("TOPIC PROMPT FAILED");
        return false;
    }


    gsmSerial.print(AWS_TOPIC);

    delay(500);

    String response =
        readGSMResponse(3000);

    if (response.indexOf("OK") < 0)
    {
        Serial.println("TOPIC WRITE FAILED");
        return false;
    }


    /* PAYLOAD */

    cmd = "AT+CMQTTPAYLOAD=0,";
    cmd += String(payload.length());

    if (!sendAT(
            cmd,
            ">",
            5000))
    {
        Serial.println("PAYLOAD PROMPT FAILED");
        return false;
    }


    gsmSerial.print(payload);

    delay(500);

    response =
        readGSMResponse(3000);

    if (response.indexOf("OK") < 0)
    {
        Serial.println("PAYLOAD WRITE FAILED");
        return false;
    }


    /* PUBLISH */

    if (!sendAT(
            "AT+CMQTTPUB=0,1,60",
            "OK",
            30000))
    {
        Serial.println("GSM AWS PUBLISH FAILED");

        sendAT(
            "AT+CMQTTDISC=0,60",
            "OK",
            5000);

        sendAT(
            "AT+CMQTTSTOP",
            "OK",
            5000);

        return false;
    }


    Serial.println();
    Serial.println("************************************");
    Serial.println("AWS GSM PUBLISH SUCCESS");
    Serial.println("************************************");


    sendAT(
        "AT+CMQTTDISC=0,60",
        "OK",
        5000);

    sendAT(
        "AT+CMQTTSTOP",
        "OK",
        5000);


    return true;
}


/* =========================================================
   WIFI CONNECT
   ========================================================= */

bool connectWiFi()
{
    Serial.println();
    Serial.println("========================================");
    Serial.println("CHECKING SANIYA WIFI");
    Serial.println("========================================");


    WiFi.mode(WIFI_STA);

    WiFi.begin(
        WIFI_SSID,
        WIFI_PASSWORD);


    Serial.print("Connecting");

    unsigned long start = millis();

    while (
        WiFi.status() != WL_CONNECTED &&
        millis() - start < 20000UL)
    {
        Serial.print(".");
        delay(500);
    }

    Serial.println();


    if (WiFi.status() != WL_CONNECTED)
    {
        Serial.println("WIFI CONNECTION FAILED");

        wifiAvailable = false;

        return false;
    }


    Serial.println("WIFI CONNECTED");

    Serial.print("IP = ");
    Serial.println(WiFi.localIP());

    wifiAvailable = true;

    return true;
}


/* =========================================================
   WIFI AWS CONNECT
   ========================================================= */

bool connectAWSWiFi()
{
    if (WiFi.status() != WL_CONNECTED)
    {
        return false;
    }


    static BearSSL::X509List ca(
        AWS_ROOT_CA);

    static BearSSL::X509List cert(
        AWS_DEVICE_CERT);

    static BearSSL::PrivateKey key(
        AWS_PRIVATE_KEY);


    wifiClient.setTrustAnchors(
        &ca);

    wifiClient.setClientRSACert(
        &cert,
        &key);


    wifiMqtt.setServer(
        AWS_ENDPOINT,
        AWS_PORT);


    Serial.println(
        "Connecting AWS MQTT over WiFi...");


    if (wifiMqtt.connect(
            AWS_CLIENT_ID))
    {
        Serial.println(
            "AWS WIFI MQTT CONNECTED");

        return true;
    }


    Serial.print(
        "AWS WIFI MQTT FAILED, state = ");

    Serial.println(
        wifiMqtt.state());

    return false;
}


/* =========================================================
   WIFI PUBLISH
   ========================================================= */

bool wifiPublish(String payload)
{
    Serial.println();
    Serial.println("========================================");
    Serial.println("AWS WIFI PUBLISH");
    Serial.println("========================================");


    if (!connectWiFi())
    {
        return false;
    }


    if (!connectAWSWiFi())
    {
        return false;
    }


    Serial.println(
        "Publishing complete STM8 packet...");


    bool result =
        wifiMqtt.publish(
            AWS_TOPIC,
            payload.c_str());


    if (result)
    {
        Serial.println();
        Serial.println(
            "************************************");

        Serial.println(
            "AWS WIFI PUBLISH SUCCESS");

        Serial.println(
            "************************************");

        wifiMqtt.loop();

        delay(1000);

        wifiMqtt.disconnect();

        return true;
    }


    Serial.println(
        "AWS WIFI PUBLISH FAILED");

    wifiMqtt.disconnect();

    return false;
}


/* =========================================================
   SEND ACK
   ONLY AFTER AWS SUCCESS
   ========================================================= */

void sendACK()
{
    Serial.println();
    Serial.println("========================================");
    Serial.println("AWS DATA SUCCESS");
    Serial.println("SENDING ACK TO STM8");
    Serial.println("========================================");


    digitalWrite(
        ACK_PIN,
        HIGH);

    delay(1000);

    digitalWrite(
        ACK_PIN,
        LOW);


    Serial.println(
        "ACK COMPLETE");
}


/* =========================================================
   PROCESS COMPLETE STM8 PACKET
   ========================================================= */

void processPacket(String packet)
{
    Serial.println();
    Serial.println("========================================");
    Serial.println("COMPLETE STM8 PACKET RECEIVED");
    Serial.println("========================================");

    Serial.println(packet);


    if (!packet.startsWith("<START>"))
    {
        Serial.println(
            "INVALID PACKET: START MISSING");

        return;
    }


    if (packet.indexOf("END>") < 0)
    {
        Serial.println(
            "INVALID PACKET: END MISSING");

        return;
    }


    bool cloudSuccess = false;


    /* =====================================================
       1. GSM / eSIM FIRST
       ===================================================== */

    Serial.println();
    Serial.println(
        "========================================");

    Serial.println(
        "TRYING A7672S / eSIM FIRST");

    Serial.println(
        "========================================");


    if (gsmBasicCheck())
    {
        for (uint8_t i = 0;
             i < APN_COUNT;
             i++)
        {
            if (setupPDP(APN_LIST[i]))
            {
                if (setupGSMTLS())
                {
                    if (gsmPublish(packet))
                    {
                        cloudSuccess = true;
                        break;
                    }
                }
            }
        }
    }


    /* =====================================================
       2. WIFI FALLBACK
       ===================================================== */

    if (!cloudSuccess)
    {
        Serial.println();
        Serial.println(
            "========================================");

        Serial.println(
            "GSM FAILED - TRYING WIFI");

        Serial.println(
            "========================================");


        if (wifiPublish(packet))
        {
            cloudSuccess = true;
        }
    }


    /* =====================================================
       3. ACK ONLY AFTER AWS SUCCESS
       ===================================================== */

    if (cloudSuccess)
    {
        Serial.println();
        Serial.println(
            "========================================");

        Serial.println(
            "CLOUD PUBLISH SUCCESS");

        Serial.println(
            "ACK WILL BE SENT");

        Serial.println(
            "========================================");


        sendACK();
    }
    else
    {
        Serial.println();
        Serial.println(
            "========================================");

        Serial.println(
            "GSM + WIFI BOTH FAILED");

        Serial.println(
            "NO ACK SENT TO STM8");

        Serial.println(
            "STM8 MUST REMAIN AWAKE");

        Serial.println(
            "========================================");
    }
}


/* =========================================================
   READ STM8 PACKET
   ========================================================= */

void readSTM8()
{
    while (Serial.available())
    {
        char c = Serial.read();

        stm8Packet += c;


        /*
           Start collecting only after START marker.
        */

        int startIndex =
            stm8Packet.indexOf("<START>");

        if (startIndex >= 0)
        {
            if (startIndex > 0)
            {
                stm8Packet =
                    stm8Packet.substring(
                        startIndex);
            }
        }


        /*
           Complete packet detected.
        */

        if (stm8Packet.indexOf("END>") >= 0)
        {
            String completePacket =
                stm8Packet;

            stm8Packet = "";

            processPacket(
                completePacket);
        }


        /*
           Protection against runaway buffer.
        */

        if (stm8Packet.length() > 2500)
        {
            Serial.println(
                "STM8 BUFFER OVERFLOW");

            stm8Packet = "";
        }
    }
}


/* =========================================================
   SETUP
   ========================================================= */

void setup()
{
    pinMode(
        ACK_PIN,
        OUTPUT);

    digitalWrite(
        ACK_PIN,
        LOW);


    /*
       UART0 is used for:

       STM8 RX on GPIO3
       STM8 TX on GPIO1

       Therefore STM8 must use 9600 baud.
    */

    Serial.begin(
        STM8_BAUD);

    delay(1000);


    /*
       A7672S
    */

    gsmSerial.begin(9600);


    Serial.println();
    Serial.println(
        "========================================");

    Serial.println(
        "       ACP ESP8266 RECEIVER");

    Serial.println(
        "========================================");

    Serial.println(
        "STM8 TX -> ESP GPIO3 RX");

    Serial.println(
        "STM8 RX <- ESP GPIO1 TX");

    Serial.println(
        "A7672S TX -> ESP GPIO4");

    Serial.println(
        "A7672S RX <- ESP GPIO5");

    Serial.println(
        "ESP GPIO12 -> STM8 PB5 ACK");

    Serial.println();

    Serial.println(
        "COMMUNICATION PRIORITY:");

    Serial.println(
        "1. A7672S / eSIM");

    Serial.println(
        "2. WiFi SANIYA");

    Serial.println(
        "3. NO ACK if both fail");

    Serial.println();

    Serial.println(
        "STM8 BAUD = 9600");

    Serial.println(
        "A7672S BAUD = AUTO 9600 / 115200");

    Serial.println();

    Serial.println(
        "WAITING FOR STM8 PACKET...");
}


/* =========================================================
   LOOP
   ========================================================= */

void loop()
{
    readSTM8();


    /*
       Keep WiFi MQTT alive if connected.
    */

    if (wifiMqtt.connected())
    {
        wifiMqtt.loop();
    }


    delay(2);
}