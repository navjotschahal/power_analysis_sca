## 3. Why Pi Pico (RP2040) Traces Failed

The RP2040 contains an on-chip **Switch-Mode Power Supply (SMPS)** — a buck converter that steps the 3.3V USB/external supply down to the core voltage of ~1.1V DVDD for the Cortex-M0+ cores.

**Why this kills SCA:**
- The SMPS switches at ~1 MHz, injecting broadband switching noise directly on the DVDD rail
- The data-dependent AES leakage signal is small (μA-level modulation) relative to the SMPS noise floor
- Variance analysis of our 100 captured Pico traces showed:
  - AES window: samples [3216–3710] out of 4000 — 80% of the trace is pre-trigger idle noise
  - SNR proxy (peak variance / noise floor): only 21× vs 78× for Arduino
  - Dynamic range at AES peak: only 4.6× vs 8.7× for Arduino

**What would be needed (invasive modification):**
- Remove or bypass the on-chip SMPS
- Supply 1.1V directly to the DVDD pin via an external, low-noise LDO regulator
- This is the standard approach used with ChipWhisperer's CW308 UFO target board for RP2040
- Not attempted in this project due to hardware risk

**Contrast with Pro Tinkrer 5V:**
The ATmega328P on the Trinket runs directly from the 5V USB rail with a simple linear regulator. No SMPS. The 5V supply is clean and the power consumption of the AVR core is directly measurable with a shunt resistor. This is why the Trinket produced usable traces.

---

