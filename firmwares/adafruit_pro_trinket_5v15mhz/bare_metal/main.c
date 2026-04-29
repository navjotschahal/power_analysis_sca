/*
 * ATmega328P (Adafruit Pro Trinket 16 MHz) bare-metal AES-128 SCA target.
 *
 * Protocol (identical to all other firmwares in this project):
 *   host -> chip  : 16-byte plaintext  via UART
 *   chip -> scope : trigger pulse on PB0  (Arduino pin 8)
 *   chip -> host  : 16-byte ciphertext via UART
 *
 * The trigger position is controlled by TRIGGER_ROUND (set in Makefile):
 *   TRIGGER_ROUND=1  → pulse wraps round-1  SubBytes  (first-round CPA)
 *   TRIGGER_ROUND=10 → pulse wraps round-10 SubBytes  (last-round  CPA)
 *
 * Pin assignments:
 *   PB0 (Arduino pin 8) — trigger output → scope EXT TRIG
 *   PD0 (Arduino pin 0) — USART0 RX      → USB-UART adapter TX
 *   PD1 (Arduino pin 1) — USART0 TX      → USB-UART adapter RX
 */

#define F_CPU 16000000UL
#define BAUD  115200UL

#include <avr/io.h>
#include <avr/pgmspace.h>
#include <util/setbaud.h>
#include <stdint.h>
#include "aes128.h"

static const uint8_t KEY[16] PROGMEM = {
    0x2b,0x7e,0x15,0x16,0x28,0xae,0xd2,0xa6,
    0xab,0xf7,0x15,0x88,0x09,0xcf,0x4f,0x3c
};

static void uart_init(void)
{
    UBRR0H = UBRRH_VALUE;
    UBRR0L = UBRRL_VALUE;
#if USE_2X
    UCSR0A |=  (1 << U2X0);
#else
    UCSR0A &= ~(1 << U2X0);
#endif
    UCSR0C = (1 << UCSZ01) | (1 << UCSZ00); /* 8-N-1 */
    UCSR0B = (1 << RXEN0)  | (1 << TXEN0);
}

static uint8_t uart_recv(void)
{
    while (!(UCSR0A & (1 << RXC0)));
    return UDR0;
}

static void uart_send(uint8_t b)
{
    while (!(UCSR0A & (1 << UDRE0)));
    UDR0 = b;
}

int main(void)
{
    /* Trigger pin: output, idle low */
    DDRB  |=  (1 << PB0);
    PORTB &= ~(1 << PB0);

    uart_init();

    /* Expand key schedule once into SRAM */
    uint8_t key_ram[16];
    for (uint8_t i = 0; i < 16; i++) key_ram[i] = pgm_read_byte(&KEY[i]);
    aes128_init(key_ram);

    uint8_t plaintext[16];
    uint8_t ciphertext[16];

    while (1) {
        /* 1. Receive 16-byte plaintext */
        for (uint8_t i = 0; i < 16; i++) plaintext[i] = uart_recv();

        /* 2. Encrypt — trigger fires inside aes128_encrypt at TRIGGER_ROUND */
        aes128_encrypt(plaintext, ciphertext);

        /* 3. Send 16-byte ciphertext */
        for (uint8_t i = 0; i < 16; i++) uart_send(ciphertext[i]);
    }
}
