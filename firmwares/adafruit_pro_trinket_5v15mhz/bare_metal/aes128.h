#ifndef AES128_H
#define AES128_H

#include <stdint.h>

/*
 * TRIGGER_ROUND controls where the scope trigger fires inside aes128_encrypt:
 *   0  — wrap the entire encrypt call (trigger in main, not here)
 *   1  — pulse around round-1  SubBytes  → target for first-round CPA
 *   10 — pulse around round-10 SubBytes  → target for last-round CPA
 *
 * Set via Makefile: -DTRIGGER_ROUND=1
 *
 * TRIGGER_PORT, TRIGGER_BIT must also be defined when TRIGGER_ROUND != 0.
 */

void aes128_init(const uint8_t *key);
void aes128_encrypt(const uint8_t *in, uint8_t *out);

#endif
