#include <SPI.h>
#include <nRF24L01.h>
#include <RF24.h>
#include <EEPROM.h>

#define CE_PIN   9
#define CSN_PIN 10
#define ADDR_ID   0

static const uint64_t BROADCAST_ADDR = 0xABCDABCD01LL;
static const uint64_t BASE_ADDR      = 0xF0F0F0F0E0LL;

RF24 radio(CE_PIN, CSN_PIN);
uint8_t slaveId;

void setup() {
  Serial.begin(9600);
  while (!Serial);
  Serial.println("DEBUG: Slave starting...");

  radio.begin();
  radio.setDataRate(RF24_1MBPS);
  radio.setPALevel(RF24_PA_HIGH);
  radio.enableDynamicPayloads();

  slaveId = EEPROM.read(ADDR_ID);
  Serial.print("DEBUG: Read slaveId from EEPROM: "); Serial.println(slaveId);

  if (slaveId == 0) {
    Serial.println("DEBUG: No ID found, starting registration loop");
  }
  while (slaveId == 0) {
    registerSelf();
  }

  startNormalMode();
}

void registerSelf() {
  radio.openWritingPipe(BROADCAST_ADDR);
  radio.openReadingPipe(1, BROADCAST_ADDR);

  Serial.println("DEBUG: Sending registration request");
  radio.stopListening();
  uint8_t req = 0x01;
  radio.write(&req, sizeof(req));
  radio.startListening();

  unsigned long start = millis();
  while (millis() - start < 500) {
    if (radio.available()) {
      struct { uint8_t cmd; uint8_t newId; } resp;
      radio.read(&resp, sizeof(resp));
      if (resp.cmd == 0x02) {
        slaveId = resp.newId;
        Serial.print("DEBUG: Received assign cmd, newId: "); Serial.println(slaveId);
        EEPROM.write(ADDR_ID, slaveId);
        Serial.println("DEBUG: Saved newId to EEPROM");
        delay(100);
        return;
      }
    }
  }
  delay(1000);
}

void startNormalMode() {
  uint64_t pipe = BASE_ADDR | slaveId;
  radio.openWritingPipe(pipe);
  radio.openReadingPipe(1, pipe);
  radio.startListening();
  Serial.print("DEBUG: Entering normal mode with ID: "); Serial.println(slaveId);
}

void loop() {
  if (!radio.available()) return;

  Serial.println("DEBUG: Command received via RF");
  char buf[32]; radio.read(&buf, sizeof(buf));
  char cmd = buf[0]; int id, pin, val;

  Serial.print("DEBUG: Parsed command: "); Serial.println(cmd);

  if (cmd == 'g' && sscanf(buf+1, "%d,%d", &id, &pin) == 2 && id == slaveId) {
    Serial.print("DEBUG: GET request for pin: "); Serial.println(pin);
    int result = analogRead(pin);
    Serial.print("DEBUG: Sensor value: "); Serial.println(result);
    radio.stopListening();
    radio.write(&result, sizeof(result));
    radio.startListening();
    Serial.println("DEBUG: Sent sensor result back");
  }
  else if (cmd == 's' && sscanf(buf+1, "%d,%d,%d", &id, &pin, &val) == 3 && id == slaveId) {
    Serial.print("DEBUG: SET request pin: "); Serial.print(pin);
    Serial.print(" value: "); Serial.println(val);
    analogWrite(pin, val);
    Serial.println("DEBUG: Actuator updated, sending ACK");
    uint8_t ack = 0x06;
    radio.stopListening(); radio.write(&ack, sizeof(ack)); radio.startListening();
    Serial.println("DEBUG: ACK sent");
  }
}
