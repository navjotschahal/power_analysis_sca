// Serial1 loopback test for Arduino UNO R4 Minima
// Wiring: USB-UART adapter TX -> Arduino D0 (RX)
//         USB-UART adapter RX -> Arduino D1 (TX)
//         USB-UART adapter GND -> Arduino GND
//
// Open a terminal at 115200 on the adapter's port.
// On boot you'll see "READY". Type any character and it echoes back with hex.

void setup() {
  Serial1.begin(115200);  // Hardware UART on D0/D1
  pinMode(LED_BUILTIN, OUTPUT);

  // Blink once to confirm sketch is running
  digitalWrite(LED_BUILTIN, HIGH);
  delay(200);
  digitalWrite(LED_BUILTIN, LOW);

  Serial1.println("READY - Serial1 OK");
}

void loop() {
  if (Serial1.available()) {
    uint8_t b = Serial1.read();
    Serial1.print("ECHO 0x");
    Serial1.println(b, HEX);
    digitalWrite(LED_BUILTIN, HIGH);
    delay(50);
    digitalWrite(LED_BUILTIN, LOW);
  }
}
