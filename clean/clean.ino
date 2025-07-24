#include <EEPROM.h>

void setup() {
  Serial.begin(9600);
  while (!Serial) ; // дождаться подключения Serial (для плат с USB)
  
  Serial.println("Начинаю очистку EEPROM...");
  clearEEPROM();
  Serial.println("EEPROM успешно очищена.");
}

void loop() {
  // ничего не делаем
}

// Функция, проходящая по всем адресам EEPROM и затирающая их
void clearEEPROM() {
  int len = EEPROM.length();      // общее число байт EEPROM
  for (int i = 0; i < len; i++) {
    EEPROM.write(i, 0);           // записываем 0; можно заменить на 0xFF
  }
}
