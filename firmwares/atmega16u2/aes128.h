#ifndef AES128_H
#define AES128_H

#include <stdint.h>

void aes128_init(const uint8_t *key);
void aes128_encrypt(const uint8_t *in, uint8_t *out);

#endif
