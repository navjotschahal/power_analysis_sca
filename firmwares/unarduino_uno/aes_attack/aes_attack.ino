// AES-128 power analysis target for Arduino UNO R4 Minima.
// Protocol mirrors the Pico firmware: receive 16-byte plaintext, encrypt,
// return 16-byte ciphertext. Pin 7 pulses HIGH around the encryption call
// so the oscilloscope has a clean trigger edge.
//
// Requires: "Crypto" library by rweather (install via Arduino Library Manager)
// Trigger pin wiring: Digital pin 7 -> oscilloscope EXT TRIG input

#include <AES.h>

#define TRIGGER_PIN 7

// AES-128 key (same as Pico firmware for cross-board comparison)
static const uint8_t KEY[16] = {
  0x2b, 0x7e, 0x15, 0x16, 0x28, 0xae, 0xd2, 0xa6,
  0xab, 0xf7, 0x15, 0x88, 0x09, 0xcf, 0x4f, 0x3c
};

AES128 aes128;
uint8_t plaintext[16];
uint8_t ciphertext[16];

void setup() {
  Serial1.begin(115200);  // Hardware UART: D0 (RX), D1 (TX) -> USB-UART adapter
  pinMode(TRIGGER_PIN, OUTPUT);
  digitalWrite(TRIGGER_PIN, LOW);
  aes128.setKey(KEY, sizeof(KEY));
}

void loop() {
  // Block until a full 16-byte plaintext arrives
  uint8_t n = 0;
  while (n < 16) {
    int b = Serial1.read();
    if (b >= 0) {
      plaintext[n++] = (uint8_t)b;
    }
  }

  // Trigger HIGH -> encrypt -> trigger LOW
  digitalWrite(TRIGGER_PIN, HIGH);
  aes128.encryptBlock(ciphertext, plaintext);
  digitalWrite(TRIGGER_PIN, LOW);

  Serial1.write(ciphertext, 16);
}
