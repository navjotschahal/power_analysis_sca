MCU    = atmega328p
F_CPU  = 16000000UL
BAUD   = 115200UL
TARGET = aes_target

# ── Trigger round ──────────────────────────────────────────────────────────────
# 1  → round-1  SubBytes  (first-round CPA  — use with --round first)
# 10 → round-10 SubBytes  (last-round  CPA  — use with --round last)
TRIGGER_ROUND = 1

# ── Programmer ────────────────────────────────────────────────────────────────
# Pro Trinket uses its built-in USBtiny bootloader.
# Press the reset button, wait for the red LED to blink, then run 'make flash'.
PROGRAMMER = usbtiny

# ── Toolchain (Arduino IDE bundled) ───────────────────────────────────────────
AVR_GCC_DIR = $(HOME)/Library/Arduino15/packages/arduino/tools/avr-gcc/7.3.0-atmel3.6.1-arduino7/bin
AVRDUDE_DIR = $(HOME)/Library/Arduino15/packages/arduino/tools/avrdude/8.0.0-arduino1
AVRDUDE_CFG = $(AVRDUDE_DIR)/etc/avrdude.conf

CC      = $(AVR_GCC_DIR)/avr-gcc
OBJCOPY = $(AVR_GCC_DIR)/avr-objcopy
SIZE    = $(AVR_GCC_DIR)/avr-size
AVRDUDE = $(AVRDUDE_DIR)/bin/avrdude

SRCS  = main.c aes128.c
OBJS  = $(SRCS:.c=.o)

CFLAGS = -mmcu=$(MCU) \
          -DF_CPU=$(F_CPU) \
          -DBAUD=$(BAUD) \
          -DBAUD_TOL=3 \
          -DTRIGGER_ROUND=$(TRIGGER_ROUND) \
          -DTRIGGER_PORT=PORTB \
          -DTRIGGER_BIT=PB0 \
          -Os \
          -std=c99 \
          -Wall \
          -Wextra \
          -ffunction-sections \
          -fdata-sections

LDFLAGS = -mmcu=$(MCU) -Wl,--gc-sections

# ── Targets ───────────────────────────────────────────────────────────────────
all: $(TARGET).hex size

$(TARGET).elf: $(OBJS)
	$(CC) $(LDFLAGS) -o $@ $^

$(TARGET).hex: $(TARGET).elf
	$(OBJCOPY) -O ihex -R .eeprom $< $@

%.o: %.c
	$(CC) $(CFLAGS) -c -o $@ $<

size: $(TARGET).elf
	$(SIZE) --mcu=$(MCU) -C $<

# Press reset on Pro Trinket (red LED blinks), then immediately run this.
flash: $(TARGET).hex
	$(AVRDUDE) -C $(AVRDUDE_CFG) -c $(PROGRAMMER) -p $(MCU) \
	    -U flash:w:$<:i

clean:
	rm -f $(OBJS) $(TARGET).elf $(TARGET).hex

.PHONY: all flash size clean
