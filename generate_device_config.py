"""
generate_device_config.py

Generates scalable quantum dot array device configurations with realistic physical
capacitance parameters and charge sensor layouts (grouping every 3 gates with a charge sensor),
compatible with both QArray and falcon-core device configs.

Supports random generation of physical parameters via Gaussian distributions (mean & std),
seeded generation, saving, and loading from YAML/JSON for consumption by the QArray plugin
and Marimo notebook.
"""

from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union
import json
import numpy as np
import yaml

# Standard physical constants
ATTO_FARADS = 1e-18
ELECTRON_CHARGE = 1.6e-19

# Default nominal parameters (mean values)
DEFAULT_PARAMS = {
    "charging_energy": 0.013,  # Volts (13 mV)
    "dot_dot_cap": 2.0 * ATTO_FARADS / ELECTRON_CHARGE,  # ~12.5 F/e
    "dot_sensor_cap": 1.0 * ATTO_FARADS / ELECTRON_CHARGE,  # ~6.25 F/e
    "dot_dot_diag_cap": 30.0 * ATTO_FARADS / ELECTRON_CHARGE,  # ~187.5 F/e
    "sensor_gate_dot_cap": 0.1 * ATTO_FARADS / ELECTRON_CHARGE,  # ~0.625 F/e
    "noise_amplitude": 0.05,
    "temperature": 0.1,  # Kelvin
    "coulomb_peak_width": 0.0005,
    "charge_carrier": "electrons",
}

# Default standard deviations (0.0 for deterministic default)
DEFAULT_STDS = {
    "charging_energy_std": 0.0,
    "dot_dot_cap_std": 0.0,
    "dot_sensor_cap_std": 0.0,
    "dot_dot_diag_cap_std": 0.0,
    "sensor_gate_dot_cap_std": 0.0,
    "noise_amplitude_std": 0.0,
}


def sample_gaussian(
    rng: np.random.Generator,
    mean: float,
    std: float,
    min_val: float = 1e-12,
) -> float:
    """Sample a positive scalar from a Gaussian distribution with lower bound clipping."""
    if std <= 0.0:
        return float(mean)
    val = float(rng.normal(mean, std))
    return float(max(min_val, val))


def generate_device_config(
    n_dots: int,
    seed: Optional[int] = None,
    # Means
    charging_energy: float = DEFAULT_PARAMS["charging_energy"],
    dot_dot_cap: float = DEFAULT_PARAMS["dot_dot_cap"],
    dot_sensor_cap: float = DEFAULT_PARAMS["dot_sensor_cap"],
    dot_dot_diag_cap: float = DEFAULT_PARAMS["dot_dot_diag_cap"],
    sensor_gate_dot_cap: float = DEFAULT_PARAMS["sensor_gate_dot_cap"],
    noise_amplitude: float = DEFAULT_PARAMS["noise_amplitude"],
    temperature: float = DEFAULT_PARAMS["temperature"],
    coulomb_peak_width: float = DEFAULT_PARAMS["coulomb_peak_width"],
    charge_carrier: str = DEFAULT_PARAMS["charge_carrier"],
    # Standard deviations
    charging_energy_std: float = DEFAULT_STDS["charging_energy_std"],
    dot_dot_cap_std: float = DEFAULT_STDS["dot_dot_cap_std"],
    dot_sensor_cap_std: float = DEFAULT_STDS["dot_sensor_cap_std"],
    dot_dot_diag_cap_std: float = DEFAULT_STDS["dot_dot_diag_cap_std"],
    sensor_gate_dot_cap_std: float = DEFAULT_STDS["sensor_gate_dot_cap_std"],
    noise_amplitude_std: float = DEFAULT_STDS["noise_amplitude_std"],
) -> Dict[str, Any]:
    """
    Generates device configuration for n_dots following the scalable layout:
      - n_plungers = n_dots
      - 1 charge sensor per 3 gates: n_sensors = (n_dots - 1) // 3 + 1
      - n_gates = n_plungers + n_sensors
      - Physical parameters sampled from Gaussian(mean, std) if std > 0
    """
    rng = np.random.default_rng(seed)

    # Sample scalar parameters
    sampled_charging_energy = sample_gaussian(rng, charging_energy, charging_energy_std, min_val=0.001)
    sampled_noise_amplitude = sample_gaussian(rng, noise_amplitude, noise_amplitude_std, min_val=0.0)

    # Derived base gate-dot capacitance: C_g = 1 / E_c
    gate_dot_cap = 1.0 / sampled_charging_energy

    n_plungers = n_dots
    n_sensors = (n_dots - 1) // 3 + 1
    n_gates = n_plungers + n_sensors

    plunger_names = [f"P{i+1}" for i in range(n_plungers)]
    sensor_names = [f"S{i+1}" for i in range(n_sensors)]
    all_gate_names = plunger_names + sensor_names

    # 1. Cdd: strictly nearest-neighbor tridiagonal
    Cdd = np.zeros((n_dots, n_dots))
    for i in range(n_dots - 1):
        d_diag = sample_gaussian(rng, dot_dot_diag_cap, dot_dot_diag_cap_std)
        d_inter = sample_gaussian(rng, dot_dot_cap, dot_dot_cap_std)
        Cdd[i, i] = d_diag
        Cdd[i, i + 1] = d_inter
        Cdd[i + 1, i] = d_inter
    Cdd[n_dots - 1, n_dots - 1] = sample_gaussian(rng, dot_dot_diag_cap, dot_dot_diag_cap_std)

    # 2. Cgd: nearest-neighbor plungers and sensor gate cross-couplings
    Cgd = np.zeros((n_dots, n_gates))
    for i in range(n_dots):
        Cgd[i, i] = gate_dot_cap
        for j in range(n_plungers):
            if abs(i - j) == 1:
                Cgd[i, j] = gate_dot_cap / 4.0
        for k in range(n_sensors):
            if i // 3 == k:
                Cgd[i, n_plungers + k] = sample_gaussian(rng, sensor_gate_dot_cap, sensor_gate_dot_cap_std)

    # 3. Cds: Sensor placed adjacent to dots in group of 3
    Cds = np.zeros((n_sensors, n_dots))
    sensor_caps = [0.85, 0.95, 0.75]
    for j in range(n_sensors):
        for i in range(3):
            if i + 3 * j < n_dots:
                d_sens = sample_gaussian(rng, dot_sensor_cap, dot_sensor_cap_std)
                Cds[j, i + 3 * j] = d_sens * sensor_caps[i]

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

    physical_params = {
        "charging_energy": sampled_charging_energy,
        "gate_dot_cap": gate_dot_cap,
        "dot_dot_cap": dot_dot_cap,
        "dot_sensor_cap": dot_sensor_cap,
        "dot_dot_diag_cap": dot_dot_diag_cap,
        "sensor_gate_dot_cap": sensor_gate_dot_cap,
        "noise_amplitude": sampled_noise_amplitude,
        "temperature": temperature,
        "coulomb_peak_width": coulomb_peak_width,
        "charge_carrier": charge_carrier,
        "seed": seed,
        "stds": {
            "charging_energy_std": charging_energy_std,
            "dot_dot_cap_std": dot_dot_cap_std,
            "dot_sensor_cap_std": dot_sensor_cap_std,
            "dot_dot_diag_cap_std": dot_dot_diag_cap_std,
            "sensor_gate_dot_cap_std": sensor_gate_dot_cap_std,
            "noise_amplitude_std": noise_amplitude_std,
        },
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
        "physical_parameters": physical_params,
    }


def write_device_config(
    n_dots: int,
    output_path: Union[str, Path],
    seed: Optional[int] = None,
    **kwargs: Any,
) -> Path:
    """Generates and writes device configuration to YAML or JSON."""
    out = Path(output_path)
    cfg = generate_device_config(n_dots, seed=seed, **kwargs)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        if out.suffix.lower() == ".json":
            json.dump(cfg, f, indent=2)
        else:
            yaml.dump(cfg, f, default_flow_style=None)
    return out


def load_device_config(config_path: Union[str, Path]) -> Dict[str, Any]:
    """Loads device configuration from YAML or JSON."""
    p = Path(config_path)
    with p.open("r", encoding="utf-8") as f:
        if p.suffix.lower() == ".json":
            return json.load(f)
        return yaml.safe_load(f)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate scalable device config with Gaussian randomization")
    parser.add_argument("--n-dots", type=int, default=6, help="Number of dots")
    parser.add_argument("--seed", type=int, default=None, help="Random seed")
    parser.add_argument("--charging-energy", type=float, default=DEFAULT_PARAMS["charging_energy"], help="Charging energy mean (V)")
    parser.add_argument("--charging-energy-std", type=float, default=0.0, help="Charging energy std (V)")
    parser.add_argument("--dot-dot-cap", type=float, default=DEFAULT_PARAMS["dot_dot_cap"], help="Interdot capacitance mean")
    parser.add_argument("--dot-dot-cap-std", type=float, default=0.0, help="Interdot capacitance std")
    parser.add_argument("--noise-amplitude", type=float, default=DEFAULT_PARAMS["noise_amplitude"], help="White noise amplitude")
    parser.add_argument("--noise-amplitude-std", type=float, default=0.0, help="White noise amplitude std")
    parser.add_argument("--output", type=str, default="device_config.yml", help="Output YAML/JSON file")
    args = parser.parse_args()

    out_file = write_device_config(
        n_dots=args.n_dots,
        output_path=args.output,
        seed=args.seed,
        charging_energy=args.charging_energy,
        charging_energy_std=args.charging_energy_std,
        dot_dot_cap=args.dot_dot_cap,
        dot_dot_cap_std=args.dot_dot_cap_std,
        noise_amplitude=args.noise_amplitude,
        noise_amplitude_std=args.noise_amplitude_std,
    )
    print(f"Generated {out_file} with {args.n_dots} dots (seed={args.seed}).")
