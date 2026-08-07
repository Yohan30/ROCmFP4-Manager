#!/bin/bash
# Force GPU clock to max (3100 MHz) for Radeon Strix Halo
# Detects the AMD GPU card dynamically (card0/card1/etc.)

CARD=$(ls -d /sys/class/drm/card*/device/pp_od_clk_voltage 2>/dev/null | head -1 | sed 's|/device/pp_od_clk_voltage||')

if [ -z "$CARD" ]; then
    echo "ERREUR: Aucun GPU AMD trouvé"
    exit 1
fi

echo "GPU detecte: $CARD"

# Passer en mode manual
echo "manual" > "$CARD/device/power_dpm_force_performance_level"

# OverDrive: forcer min = max = 3100 MHz
echo "s 0 3100" > "$CARD/device/pp_od_clk_voltage"
echo "s 1 3100" >> "$CARD/device/pp_od_clk_voltage"
echo "c" >> "$CARD/device/pp_od_clk_voltage"

echo "GPU clock forced to:"
cat "$CARD/device/pp_dpm_sclk"
