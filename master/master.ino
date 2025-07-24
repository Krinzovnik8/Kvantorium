#include <SPI.h>
#include <nRF24L01.h>
#include <RF24.h>
#include <EEPROM.h>

#define CE_PIN  9
#define CSN_PIN 10
#define ADDR_SLAVE_COUNT 0

static const uint64_t BROADCAST_ADDR = 0xABCDABCD01LL;
static const uint64_t BASE_ADDR      = 0xF0F0F0F0E0LL;

const unsigned long REG_INTERVAL  = 10UL * 60UL * 1000UL;  // 10 min
const unsigned long REG_DURATION  =     20UL * 1000UL;    // 20 s
const unsigned long SLAVE_TIMEOUT =      3UL * 1000UL;    //  3 s

RF24 radio(CE_PIN, CSN_PIN);
uint8_t slaveCount;
unsigned long lastRegCheck;

void setup() {
  Serial.begin(9600);
  while (!Serial);
  Serial.println("DEBUG: Master starting...");

  radio.begin();
  radio.setDataRate(RF24_1MBPS);
  radio.setPALevel(RF24_PA_HIGH);
  radio.enableDynamicPayloads();
  radio.setRetries(5,15);

  slaveCount = EEPROM.read(ADDR_SLAVE_COUNT);
  Serial.print("DEBUG: Loaded slaveCount from EEPROM: "); Serial.println(slaveCount);

  lastRegCheck = millis();
  Serial.println("DEBUG: Setup complete.");
}

void loop() {
  unsigned long now = millis();

  if (now - lastRegCheck >= REG_INTERVAL) {
    registerNewSlaves();
    lastRegCheck = now;
  }

  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd.length()) {
      Serial.print("DEBUG: Received hub command: "); Serial.println(cmd);
      processHubCommand(cmd);
    }
  }
}

void registerNewSlaves() {
  Serial.println("DEBUG: -- Registration window open --");
  radio.openWritingPipe(BROADCAST_ADDR);
  radio.openReadingPipe(1, BROADCAST_ADDR);
  radio.startListening();

  unsigned long start = millis();
  while (millis() - start < REG_DURATION) {
    if (radio.available()) {
      uint8_t req;
      radio.read(&req, sizeof(req));
      Serial.println("DEBUG: Registration request received");
      if (req == 0x01) {
        uint8_t newId = ++slaveCount;
        EEPROM.write(ADDR_SLAVE_COUNT, slaveCount);
        Serial.print("DEBUG: Assigning new slave ID: "); Serial.println(newId);

        struct { uint8_t cmd; uint8_t id; } resp = {0x02, newId};
        radio.stopListening();
        radio.write(&resp, sizeof(resp));
        radio.startListening();
        Serial.println("DEBUG: ID assignment sent");
      }
    }
  }

  radio.stopListening();
  Serial.println("DEBUG: -- Registration window closed --");
}

void processHubCommand(const String &cmd) {
  char type = cmd.charAt(0);
  if (type == 'g') {
    int comma = cmd.indexOf(',');
    uint8_t id  = cmd.substring(1, comma).toInt();
    uint8_t pin = cmd.substring(comma + 1).toInt();
    handleGet(id, pin);
  }
  else if (type == 's') {
    int first  = cmd.indexOf(',');
    int second = cmd.indexOf(',', first + 1);
    uint8_t id   = cmd.substring(1, first).toInt();
    uint8_t pin  = cmd.substring(first + 1, second).toInt();
    int     val  = cmd.substring(second + 1).toInt();
    handleSet(id, pin, val);
  }
  else {
    Serial.print("ERROR: Unknown command "); Serial.println(cmd);
  }
}

void handleGet(uint8_t id, uint8_t pin) {
  char buf[16];
  snprintf(buf, sizeof(buf), "g%u,%u", id, pin);
  uint64_t addr = BASE_ADDR | id;

  radio.openWritingPipe(addr);
  radio.openReadingPipe(1, addr);

  Serial.print("DEBUG: Sending GET to slave "); Serial.print(id);
  Serial.print(" pin "); Serial.println(pin);

  radio.stopListening();
  radio.write(buf, strlen(buf) + 1);
  radio.startListening();

  unsigned long start = millis();
  while (millis() - start < SLAVE_TIMEOUT) {
    if (radio.available()) {
      int result;
      radio.read(&result, sizeof(result));
      Serial.print("DEBUG: Received response: "); Serial.println(result);
      Serial.println(result);
      return;
    }
  }
  Serial.print("ERROR: Timeout, no response from slave "); Serial.println(id);
}

void handleSet(uint8_t id, uint8_t pin, int value) {
  char buf[20];
  snprintf(buf, sizeof(buf), "s%u,%u,%d", id, pin, value);
  uint64_t addr = BASE_ADDR | id;

  radio.openWritingPipe(addr);
  radio.openReadingPipe(1, addr);

  Serial.print("DEBUG: Sending SET to slave "); Serial.print(id);
  Serial.print(" pin "); Serial.print(pin);
  Serial.print(" value "); Serial.println(value);

  radio.stopListening();
  radio.write(buf, strlen(buf) + 1);
  radio.startListening();

  unsigned long start = millis();
  while (millis() - start < SLAVE_TIMEOUT) {
    if (radio.available()) {
      uint8_t ack;
      radio.read(&ack, sizeof(ack));
      Serial.print("DEBUG: Received ACK: "); Serial.println(ack);
      if (ack == 0x06) {
        Serial.println("OK");
      } else {
        Serial.println("ERROR: Invalid ACK");
      }
      return;
    }
  }
  Serial.print("ERROR: Timeout, no ACK from slave "); Serial.println(id);
}