"""
generate_device_config.py

Generates scalable quantum dot array device configurations with realistic physical
capacitance parameters and charge sensor layouts (grouping every 3 gates with a charge sensor),
compatible with both QArray and falcon-core device configs.
"""

from pathlib import Path
from typing import Any, Dict
import numpy as np
import yaml


def generate_device_config(n_dots: int) -> Dict[str, Any]:
    """
    Generates device configuration for n_dots following the scalable layout:
      - n_plungers = n_dots
      - 1 charge sensor per 3 gates: n_sensors = (n_dots - 1) // 3 + 1
      - n_gates = n_plungers + n_sensors
      - Physical parameters:
          charging_energy = 13 meV (0.013 V)
          gate_dot_cap = 1 / charging_energy
          dot_dot_cap (nearest-neighbor) = 2 aF / e
          dot_sensor_cap = 1 aF / e
          dot_dot_diag_cap = 30 aF / e
          sensor_gate_dot_cap = 0.1 aF / e
    """
    n_plungers = n_dots
    n_sensors = (n_dots - 1) // 3 + 1
    n_gates = n_plungers + n_sensors

    plunger_names = [f"P{i+1}" for i in range(n_plungers)]
    sensor_names = [f"S{i+1}" for i in range(n_sensors)]
    all_gate_names = plunger_names + sensor_names

    attoFarads = 10**-18
    electron_charge = 1.6 * 10**-19
    wiggle_factor = 1.0

    charging_energy = 0.013
    gate_dot_cap = 1.0 / charging_energy
    dot_dot_cap = (1.0 / wiggle_factor) * 2.0 * attoFarads / electron_charge
    dot_sensor_cap = (1.0 / wiggle_factor) * 1.0 * attoFarads / electron_charge
    dot_dot_diag_cap = (1.0 / wiggle_factor) * 30.0 * attoFarads / electron_charge
    sensor_gate_dot_cap = 0.1 * attoFarads / electron_charge

    # 1. Cdd: strictly nearest-neighbor tridiagonal
    Cdd = np.zeros((n_dots, n_dots))
    for i in range(n_dots - 1):
        Cdd[i, i] = dot_dot_diag_cap
        Cdd[i, i + 1] = dot_dot_cap
        Cdd[i + 1, i] = dot_dot_cap
    Cdd[n_dots - 1, n_dots - 1] = dot_dot_diag_cap

    # 2. Cgd: nearest-neighbor plungers and sensor gate cross-couplings
    Cgd = np.zeros((n_dots, n_gates))
    for i in range(n_dots):
        Cgd[i, i] = gate_dot_cap
        for j in range(n_plungers):
            if abs(i - j) == 1:
                Cgd[i, j] = gate_dot_cap / 4.0
        for k in range(n_sensors):
            if i // 3 == k:
                Cgd[i, n_plungers + k] = sensor_gate_dot_cap

    # 3. Cds: Sensor placed adjacent to dots in group of 3
    Cds = np.zeros((n_sensors, n_dots))
    sensor_caps = [0.85, 0.95, 0.75]
    for j in range(n_sensors):
        for i in range(3):
            if i + 3 * j < n_dots:
                Cds[j, i + 3 * j] = dot_sensor_cap * sensor_caps[i]

    # 4. Cgs: Pure sensor gate coupling
    Cgs = np.zeros((n_sensors, n_gates))
    for s in range(n_sensors):
        Cgs[s, :n_plungers] = gate_dot_cap / 4.0
        Cgs[s, n_plungers + s] = gate_dot_cap

    sensor_config = {f"S{i+1}": True for i in range(n_sensors)}

    # Falcon core config sections
    groups: Dict[str, Any] = {}
    for j in range(n_sensors):
        g_dots = min(3, n_dots - 3 * j)
        p_in_group = [f"P{3 * j + i + 1}" for i in range(g_dots)]
        groups[f"group{j+1}"] = {
            "Name": f"S{j+1}",
            "NumDots": g_dots,
            "ScreeningGates": f"S{j+1}",
            "PlungerGates": ";".join(p_in_group),
        }

    return {
        "n_dots": n_dots,
        "gate_names": all_gate_names,
        "ScreeningGates": ";".join(sensor_names),
        "PlungerGates": ";".join(plunger_names),
        "sensor_config": sensor_config,
        "groups": groups,
        "capacitances": {
            "Cdd": Cdd.tolist(),
            "Cgd": Cgd.tolist(),
            "Cds": Cds.tolist(),
            "Cgs": Cgs.tolist(),
        },
    }


def write_device_config(n_dots: int, output_path: str | Path) -> Path:
    out = Path(output_path)
    cfg = generate_device_config(n_dots)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as f:
        yaml.dump(cfg, f, default_flow_style=None)
    return out


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate scalable device config")
    parser.add_argument("--n-dots", type=int, default=6, help="Number of dots")
    parser.add_argument("--output", type=str, default="device_config.yml", help="Output YAML file")
    args = parser.parse_args()

    out_file = write_device_config(args.n_dots, args.output)
    print(f"Generated {out_file} with {args.n_dots} dots.")
