/*
 * ATmega16U2 AES-128 SCA target firmware.
 *
 * Protocol (matches Pico and UNO firmwares):
 *   host -> device : 16-byte plaintext
 *   device         : PB0 HIGH  (scope trigger rising edge)
 *   device         : AES-128 ECB encrypt
 *   device         : PB0 LOW
 *   device -> host : 16-byte ciphertext
 *
 * Pin assignments:
 *   PB0         – trigger output to oscilloscope EXT TRIG
 *   PD2 (RXD1) – USART1 RX  → USB-UART adapter TX
 *   PD3 (TXD1) – USART1 TX  → USB-UART adapter RX
 *
 * Build: F_CPU = 16000000, BAUD = 115200
 */

#define F_CPU 16000000UL
#define BAUD  115200UL

#include <avr/io.h>
#include <avr/pgmspace.h>
#include <util/setbaud.h>
#include <stdint.h>
#include "aes128.h"

/* Same 128-bit key used by the Pico and UNO firmwares */
static const uint8_t KEY[16] PROGMEM = {
    0x2b,0x7e,0x15,0x16,0x28,0xae,0xd2,0xa6,
    0xab,0xf7,0x15,0x88,0x09,0xcf,0x4f,0x3c
};

#define TRIGGER_DDR  DDRB
#define TRIGGER_PORT PORTB
#define TRIGGER_BIT  PB0

static void uart_init(void)
{
    UBRR1H = UBRRH_VALUE;
    UBRR1L = UBRRL_VALUE;
#if USE_2X
    UCSR1A |=  (1 << U2X1);
#else
    UCSR1A &= ~(1 << U2X1);
#endif
    /* 8-N-1 */
    UCSR1C = (1 << UCSZ11) | (1 << UCSZ10);
    /* Enable RX and TX */
    UCSR1B = (1 << RXEN1) | (1 << TXEN1);
}

static uint8_t uart_recv(void)
{
    while (!(UCSR1A & (1 << RXC1)));
    return UDR1;
}

static void uart_send(uint8_t b)
{
    while (!(UCSR1A & (1 << UDRE1)));
    UDR1 = b;
}

int main(void)
{
    /* Trigger pin as output, idle low */
    TRIGGER_DDR  |=  (1 << TRIGGER_BIT);
    TRIGGER_PORT &= ~(1 << TRIGGER_BIT);

    uart_init();

    /* Copy key from flash and expand round keys once */
    uint8_t key_ram[16];
    for (uint8_t i = 0; i < 16; i++) key_ram[i] = pgm_read_byte(&KEY[i]);
    aes128_init(key_ram);

    uint8_t plaintext[16];
    uint8_t ciphertext[16];

    while (1) {
        /* 1. Receive 16-byte plaintext */
        for (uint8_t i = 0; i < 16; i++) plaintext[i] = uart_recv();

        /* 2. Trigger HIGH – scope captures from this rising edge */
        TRIGGER_PORT |= (1 << TRIGGER_BIT);

        /* 3. AES-128 ECB encrypt (S-Box power leakage here) */
        aes128_encrypt(plaintext, ciphertext);

        /* 4. Trigger LOW */
        TRIGGER_PORT &= ~(1 << TRIGGER_BIT);

        /* 5. Send 16-byte ciphertext back */
        for (uint8_t i = 0; i < 16; i++) uart_send(ciphertext[i]);
    }
}
