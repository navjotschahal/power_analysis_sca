MCU    = atmega16u2
F_CPU  = 16000000UL
BAUD   = 115200UL
TARGET = aes_target

# ── Programmer ───────────────────────────────────────────────────────────────
# Set PROGRAMMER to match your ISP hardware:
#   usbtiny      USBtinyISP / AdaFruit USBtinyISP
#   avrispmkii   Atmel AVRISP mkII (USB HID)
#   atmelice_isp Atmel-ICE (ISP mode)
#   arduino      Arduino as ISP (set PORT below)
#   stk500v1     Generic STK500 v1 (set PORT below)
PROGRAMMER = stk500v2
PORT       = /dev/tty.usbserial-130

# ── Toolchain (Arduino IDE bundled — no separate install needed) ──────────────
AVR_GCC_DIR = $(HOME)/Library/Arduino15/packages/arduino/tools/avr-gcc/7.3.0-atmel3.6.1-arduino7/bin
AVRDUDE_DIR = $(HOME)/Library/Arduino15/packages/arduino/tools/avrdude/8.0.0-arduino1
AVRDUDE_CFG = $(AVRDUDE_DIR)/etc/avrdude.conf

CC      = $(AVR_GCC_DIR)/avr-gcc
OBJCOPY = $(AVR_GCC_DIR)/avr-objcopy
SIZE    = $(AVR_GCC_DIR)/avr-size
AVRDUDE = $(AVRDUDE_DIR)/bin/avrdude

SRCS    = main.c aes128.c
OBJS    = $(SRCS:.c=.o)

CFLAGS  = -mmcu=$(MCU) \
           -DF_CPU=$(F_CPU) \
           -DBAUD=$(BAUD) \
           -DBAUD_TOL=3 \
           -Os \
           -std=c99 \
           -Wall \
           -Wextra \
           -ffunction-sections \
           -fdata-sections

LDFLAGS = -mmcu=$(MCU) -Wl,--gc-sections

# ── Default target ────────────────────────────────────────────────────────────
all: $(TARGET).hex size

$(TARGET).elf: $(OBJS)
	$(CC) $(LDFLAGS) -o $@ $^

$(TARGET).hex: $(TARGET).elf
	$(OBJCOPY) -O ihex -R .eeprom $< $@

%.o: %.c
	$(CC) $(CFLAGS) -c -o $@ $<

size: $(TARGET).elf
	$(SIZE) --mcu=$(MCU) -C $<

# ── Flash ─────────────────────────────────────────────────────────────────────
flash: $(TARGET).hex
ifdef PORT
	$(AVRDUDE) -C $(AVRDUDE_CFG) -c $(PROGRAMMER) -p $(MCU) -P $(PORT) -U flash:w:$<:i
else
	$(AVRDUDE) -C $(AVRDUDE_CFG) -c $(PROGRAMMER) -p $(MCU) -U flash:w:$<:i
endif

# ── Fuses (16 MHz crystal, no clock divide, BOD 2.6 V) ───────────────────────
# Only run 'make fuses' if your board has a 16 MHz crystal.
# NEVER run this with an internal-oscillator-only board without checking first.
fuses:
	$(AVRDUDE) -C $(AVRDUDE_CFG) -c $(PROGRAMMER) -p $(MCU) \
	    -U lfuse:w:0xFF:m \
	    -U hfuse:w:0xD9:m \
	    -U efuse:w:0xF4:m

# ── Utility ───────────────────────────────────────────────────────────────────
clean:
	rm -f $(OBJS) $(TARGET).elf $(TARGET).hex

.PHONY: all flash fuses size clean
