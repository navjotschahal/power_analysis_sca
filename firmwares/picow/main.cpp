#include <stdio.h>
#include <string.h>
#include "pico/stdlib.h"
#include "mbedtls/aes.h"

// Hardware Config
const uint TRIGGER_PIN = 15; // Connect this to your Scope's Channel 2 (Trigger)

// Fixed Key for training (128-bit)
unsigned char key[16] = {
    0x2b, 0x7e, 0x15, 0x16, 0x28, 0xae, 0xd2, 0xa6, 
    0xab, 0xf7, 0x15, 0x88, 0x09, 0xcf, 0x4f, 0x3c
};

int main() {
    stdio_init_all();

    // Setup Trigger Pin
    gpio_init(TRIGGER_PIN);
    gpio_set_dir(TRIGGER_PIN, GPIO_OUT);
    gpio_put(TRIGGER_PIN, 0);

    // Initialize AES context
    mbedtls_aes_context aes;
    mbedtls_aes_init(&aes);
    mbedtls_aes_setkey_enc(&aes, key, 128);

    unsigned char input_buffer[16];
    unsigned char output_buffer[16];

    while (true) {
        // 1. Wait for 16 bytes from Laptop (Plaintext)
        for (int i = 0; i < 16; i++) {
            input_buffer[i] = getchar();
        }

        // 2. TRIGGER HIGH (Scope Start)
        gpio_put(TRIGGER_PIN, 1);
        
        // 3. Perform AES Encryption (S-Box leakage happens here)
        mbedtls_aes_crypt_ecb(&aes, MBEDTLS_AES_ENCRYPT, input_buffer, output_buffer);
        
        // 4. TRIGGER LOW (Scope Stop)
        gpio_put(TRIGGER_PIN, 0);

        // 5. Send Ciphertext back to laptop for verification
        for (int i = 0; i < 16; i++) {
            putchar(output_buffer[i]);
        }
    }
}