r"""
AFE4400 / AFE4490 register map (identical layout for both parts).

All registers are 24-bit. Data taken from the TI GUI's
`Config Files\Register Map_4490.xml`. Each entry is:
    name -> (address, mode, evm_default, group, description)

`evm_default` is the value the EVM/GUI programs at start-up (decimal in the XML,
shown here in hex for readability).

Use this table for:
  * populating the register dropdown in the live GUI,
  * knowing which registers are readable (mode contains "R"),
  * documenting what each register does.
"""

# group tags: TIMING, TX, RX, SYSTEM, DATA
REGISTERS = {
    # name            addr    mode    default   group      description
    "CONTROL0":      (0x00, "W",   0x000000, "SYSTEM", "Control 0: SPI_READ, TIM_COUNT_RST, DIAG_EN, SW_RST"),
    "LED2STC":       (0x01, "R/W", 0x0017C0, "TIMING", "Sample LED2 (Red) start count"),
    "LED2ENDC":      (0x02, "R/W", 0x001F3E, "TIMING", "Sample LED2 (Red) end count"),
    "LED2LEDSTC":    (0x03, "R/W", 0x001770, "TIMING", "LED2 (Red) drive start count"),
    "LED2LEDENDC":   (0x04, "R/W", 0x001F3F, "TIMING", "LED2 (Red) drive end count"),
    "ALED2STC":      (0x05, "R/W", 0x000050, "TIMING", "Sample Ambient-2 start count"),
    "ALED2ENDC":     (0x06, "R/W", 0x0007CE, "TIMING", "Sample Ambient-2 end count"),
    "LED1STC":       (0x07, "R/W", 0x000820, "TIMING", "Sample LED1 (IR) start count"),
    "LED1ENDC":      (0x08, "R/W", 0x000F9E, "TIMING", "Sample LED1 (IR) end count"),
    "LED1LEDSTC":    (0x09, "R/W", 0x0007D0, "TIMING", "LED1 (IR) drive start count"),
    "LED1LEDENDC":   (0x0A, "R/W", 0x000F9F, "TIMING", "LED1 (IR) drive end count"),
    "ALED1STC":      (0x0B, "R/W", 0x000FF0, "TIMING", "Sample Ambient-1 start count"),
    "ALED1ENDC":     (0x0C, "R/W", 0x00176E, "TIMING", "Sample Ambient-1 end count"),
    "LED2CONVST":    (0x0D, "R/W", 0x000006, "TIMING", "LED2 convert start count"),
    "LED2CONVEND":   (0x0E, "R/W", 0x0007CF, "TIMING", "LED2 convert end count"),
    "ALED2CONVST":   (0x0F, "R/W", 0x0007D6, "TIMING", "Ambient-2 convert start count"),
    "ALED2CONVEND":  (0x10, "R/W", 0x000F9F, "TIMING", "Ambient-2 convert end count"),
    "LED1CONVST":    (0x11, "R/W", 0x000FA6, "TIMING", "LED1 convert start count"),
    "LED1CONVEND":   (0x12, "R/W", 0x00176F, "TIMING", "LED1 convert end count"),
    "ALED1CONVST":   (0x13, "R/W", 0x001776, "TIMING", "Ambient-1 convert start count"),
    "ALED1CONVEND":  (0x14, "R/W", 0x001F3F, "TIMING", "Ambient-1 convert end count"),
    "ADCRSTSTCT0":   (0x15, "R/W", 0x000000, "TIMING", "ADC reset 0 start count"),
    "ADCRSTENDCT0":  (0x16, "R/W", 0x000005, "TIMING", "ADC reset 0 end count"),
    "ADCRSTSTCT1":   (0x17, "R/W", 0x0007D0, "TIMING", "ADC reset 1 start count"),
    "ADCRSTENDCT1":  (0x18, "R/W", 0x0007D5, "TIMING", "ADC reset 1 end count"),
    "ADCRSTSTCT2":   (0x19, "R/W", 0x000FA0, "TIMING", "ADC reset 2 start count"),
    "ADCRSTENDCT2":  (0x1A, "R/W", 0x000FA5, "TIMING", "ADC reset 2 end count"),
    "ADCRSTSTCT3":   (0x1B, "R/W", 0x001770, "TIMING", "ADC reset 3 start count"),
    "ADCRSTENDCT3":  (0x1C, "R/W", 0x001775, "TIMING", "ADC reset 3 end count"),
    "PRPCOUNT":      (0x1D, "R/W", 0x001F3F, "TIMING", "Pulse repetition period count (sets the sample rate)"),
    "CONTROL1":      (0x1E, "R/W", 0x000101, "SYSTEM", "Control 1: timer enable, number of averages, clock-out"),
    "SPARE1":        (0x1F, "R/W", 0x000000, "SYSTEM", "Spare / reserved"),
    "TIAGAIN":       (0x20, "R/W", 0x000000, "RX",     "Rx TIA gain: feedback R (gain) and C (bandwidth)"),
    "TIA_AMB_GAIN":  (0x21, "R/W", 0x000000, "RX",     "Rx ambient DAC + stage-2 gain + filter corner"),
    "LEDCNTRL":      (0x22, "R/W", 0x011414, "TX",     "LED drive: LED1[7:0], LED2[15:8] current codes"),
    "CONTROL2":      (0x23, "R/W", 0x000000, "SYSTEM", "Control 2: power-down AFE/TX/RX, Tx mode/reference"),
    "SPARE2":        (0x24, "R/W", 0x000000, "SYSTEM", "Spare / reserved"),
    "SPARE3":        (0x25, "R/W", 0x000000, "SYSTEM", "Spare / reserved"),
    "SPARE4":        (0x26, "R/W", 0x000000, "SYSTEM", "Spare / reserved"),
    "RESERVED1":     (0x27, "R/W", 0x000000, "SYSTEM", "Reserved"),
    "RESERVED2":     (0x28, "R/W", 0x000000, "SYSTEM", "Reserved"),
    "ALARM":         (0x29, "R/W", 0x000000, "SYSTEM", "Alarm configuration"),
    "LED2VAL":       (0x2A, "R",   0x000000, "DATA",   "Latest Red (LED2) ADC value"),
    "ALED2VAL":      (0x2B, "R",   0x000000, "DATA",   "Latest Ambient-2 ADC value"),
    "LED1VAL":       (0x2C, "R",   0x000000, "DATA",   "Latest IR (LED1) ADC value"),
    "ALED1VAL":      (0x2D, "R",   0x000000, "DATA",   "Latest Ambient-1 ADC value"),
    "LED2-ALED2VAL": (0x2E, "R",   0x000000, "DATA",   "Red minus Ambient-2 (Red PPG sample)"),
    "LED1-ALED1VAL": (0x2F, "R",   0x000000, "DATA",   "IR minus Ambient-1 (IR PPG sample)"),
    "DIAG":          (0x30, "R",   0x000000, "DATA",   "Diagnostics flags (LED/sensor fault detection)"),
}

# Convenience views ----------------------------------------------------------
READABLE = [n for n, v in REGISTERS.items() if "R" in v[1]]
WRITABLE = [n for n, v in REGISTERS.items() if "W" in v[1]]


def address(name):
    return REGISTERS[name][0]


def describe(name):
    a, mode, default, group, desc = REGISTERS[name]
    return "0x%02X  %-14s [%s]  default=0x%06X  (%s)  %s" % (
        a, name, mode, default, group, desc)


if __name__ == "__main__":
    for n in REGISTERS:
        print(describe(n))
