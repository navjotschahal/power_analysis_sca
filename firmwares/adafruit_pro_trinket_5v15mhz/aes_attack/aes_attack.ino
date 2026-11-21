// AES-128 SCA target for Adafruit Pro Tinkrer 16 MHz (ATmega328P).
// Protocol mirrors the Pico and UNO firmwares exactly:
//   receive 16-byte plaintext, trigger HIGH, AES-128 encrypt, trigger LOW, send 16-byte ciphertext.
//
// Requires: "Crypto" library by rweather  (Sketch > Include Library > Manage Libraries > search "Crypto")
//
// Wiring:
//   USB-UART adapter TX  ->  Pro Tinkrer pin 0  (RX)
//   USB-UART adapter RX  ->  Pro Tinkrer pin 1  (TX)
//   USB-UART adapter GND ->  GND
//   Pro Tinkrer pin 8    ->  Oscilloscope EXT TRIG (or Ch2)
//
// Upload:
//   1. Arduino IDE: Tools > Board > "Adafruit Pro Tinkrer 16MHz USB (ATmega328P)"
//   2. Click Upload, then immediately press the Pro Tinkrer reset button.
//      The red LED blinks fast (~10 s) while the bootloader is active.

#include <AES.h>

#define TRIGGER_PIN 8

static const uint8_t KEY[16] = {
  0x2b, 0x7e, 0x15, 0x16, 0x28, 0xae, 0xd2, 0xa6,
  0xab, 0xf7, 0x15, 0x88, 0x09, 0xcf, 0x4f, 0x3c
};

AES128  aes128;
uint8_t plaintext[16];
uint8_t ciphertext[16];

void setup() {
  pinMode(TRIGGER_PIN, OUTPUT);
  digitalWrite(TRIGGER_PIN, LOW);
  Serial.begin(115200);          // UART0: pin 0 (RX) / pin 1 (TX)
  aes128.setKey(KEY, sizeof(KEY));
}

void loop() {
  // Block until a full 16-byte plaintext arrives
  uint8_t n = 0;
  while (n < 16) {
    int b = Serial.read();
    if (b >= 0) plaintext[n++] = (uint8_t)b;
  }

  // Trigger HIGH -> encrypt -> trigger LOW
  digitalWrite(TRIGGER_PIN, HIGH);
  aes128.encryptBlock(ciphertext, plaintext);
  digitalWrite(TRIGGER_PIN, LOW);

  Serial.write(ciphertext, 16);
}
