## 8. TODOs

Search this document and the report directory for `TODO` to find every gap.

### Report content TODOs

- **TODO-KEY:** `report/sections/04_methodology.tex` line 20 has wrong hardcoded key  
  (`00 11 22 33 44 55 66 77 88 99 AA BB CC DD EE FF`) — must be updated to `2B 7E 15 16 28 AE D2 A6 AB F7 15 88 09 CF 4F 3C`

- **TODO-TRIGPIN:** same section references GPIO 22 as trigger — actual firmware uses GPIO 15. Fix in report.

- **TODO-GE-CURVES:** `report/sections/05_results.tex` §Guessing Entropy has a placeholder figure.  
  Must run `attacks/classical/guessing_entropy.py` on actual converging dataset and insert real GE vs N curves for both CPA and DPA.

- **TODO-TRINKET-CAPTURE:** Capture 50,000 traces from Pro Tinkrer 5V, save to `data/set_004_trinket_*`. Then run CPA/DPA/GE analysis and populate the results section with real hardware GE curves.

- **TODO-DL-RESULTS:** Deep learning (hettwer_sca.py) has not been run to convergence on any dataset yet. Need to train on reference or Trinket data and report GE curves for GASF+GADF combination.

- **TODO-GITHUB:** `report/appendix/B_repository.tex` and `appendix/A_hardware_setup.tex` have `PLACEHOLDER` GitHub URL. Replace with actual repo link.

- **TODO-SCHEMATIC-FIGURE:** Insert Pro Tinkrer schematic as a proper figure (LaTeX `\includegraphics`) in Appendix A. Currently text-only placeholder.

- **TODO-VIDEO-EMBED:** Appendix A §Video Evidence references video files — confirm paths and include frame captures as figures in the appendix. Videos show: scope trigger firing, AES power trace, Python acquisition running, representative scope display.

- **TODO-ARDUINO-DISCUSSION:** Add a subsection in Discussion explaining why Arduino R4 Minima also failed (Renesas RA4M1 also has internal power regulation; only 2000 traces captured vs recommended 5000+ for AVR-class devices).

- **TODO-PICO-HARDWARE-NOTE:** Add a hardware limitations box in Discussion §Limitations explaining the RP2040 SMPS issue and what would be required for a successful Pico attack (bypass SMPS, supply DVDD directly).

- **TODO-ASCAD-MENTION:** Proposal mentions ASCAD dataset. The `data/ascad2/` directory exists in the project. Clarify in report whether ASCAD data was used or just referenced; if used, document it.

- **TODO-REPORT-FLOW:** The report abstract still says "RP2040" as the primary target but results are on the reference ChipWhisperer dataset. Update abstract to accurately reflect that (a) reference dataset was primary analysis vehicle, (b) Trinket was the successful real hardware target.

---

