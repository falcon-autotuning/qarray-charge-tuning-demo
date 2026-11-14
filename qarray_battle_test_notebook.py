import marimo

__generated_with = "0.25.2"
app = marimo.App(width="full")


@app.cell
def _():
    import marimo as mo
    import numpy as np
    import matplotlib.pyplot as plt
    from scipy.signal import find_peaks
    from qarray import ChargeSensedDotArray

    return ChargeSensedDotArray, find_peaks, mo, np, plt


@app.cell(hide_code=True)
def _(mo):
    device_selector = mo.ui.radio(
        options={"2-Dot": 2, "3-Dot": 3, "5-Dot": 5, "6-Dot": 6},
        value="2-Dot",
        label="Device",
    )
    # State tracking: persistent electron configuration vector in dots and full step history
    get_state, set_state = mo.state([0, 0, 0, 0, 0])
    get_history, set_history = mo.state([])

    mo.hstack([device_selector], justify="start")
    return device_selector, get_history, get_state, set_history, set_state


@app.cell
def _(ChargeSensedDotArray, device_selector, np):
    n_dots = device_selector.value
    n_plungers = n_dots
    # n_barriers = n_dots - 1
    # n_gates = n_plungers + n_barriers + 1
    n_sensors = (n_dots-1)//3 + 1


    n_gates = n_plungers + n_sensors

    plunger_names = [f"P{_i+1}" for _i in range(n_plungers)]
    # barrier_names = [f"B{_i+1}" for _i in range(n_barriers)]
    # all_gate_names = plunger_names + barrier_names + ["S1"]
    all_gate_names = plunger_names + [f"S{_i}" for _i in range(n_sensors)]

    # QArray assumes e=1, which took time to determine

    attoFarads = 10**-18
    electron_charge = 1.6*10**(-19) # Coulumbs
    wiggle_factor = 1

    interdot_cap = 3.0*attoFarads/electron_charge  # atto Farads

    charging_energy = .013 # Volts, 13mV



    gate_dot_cap = (1/charging_energy) # Coulumbs / Volts -> Farads 

    dot_dot_cap = (1/wiggle_factor)*2.0*attoFarads/electron_charge # atto Farads (typically between 0-10)

    dot_sensor_cap = (1/wiggle_factor)*1.0*attoFarads/electron_charge # atto Farads (typically between 0-2) is just based on how far the sensor is from the dot, so derived from same as interdot

    dot_dot_diag_cap = (1/wiggle_factor)*30*attoFarads/electron_charge # Typically about 40-70 atto Farads

    sensor_gate_dot_cap = .1*attoFarads/electron_charge
    # C_diag = electron_charge**2 / charging_energy # Typically about 40-70 atto Farads
    # C_dot_dot = 0 # Typically about 0 to 10 atto Farads

    # 1. Cdd: strictly nearest-neighbor tridiagonal
    Cdd = np.zeros((n_dots, n_dots))
    for _i in range(n_dots - 1):
        Cdd[_i,_i] = dot_dot_diag_cap
        Cdd[_i, _i + 1] = dot_dot_cap # was .1
        Cdd[_i + 1, _i] = dot_dot_cap
    Cdd[n_dots-1,n_dots-1] = dot_dot_diag_cap 

    # 2. Cgd: nearest-neighbor plungers only, non-adjacent are 0.0
    Cgd = np.zeros((n_dots, n_gates))
    for _i in range(n_dots):
        Cgd[_i, _i] = gate_dot_cap
        for _j in range(n_plungers):
            if abs(_i - _j) == 1:
                Cgd[_i, _j] = gate_dot_cap/4 # was .1, is now .012
        for _k in range(n_sensors):
            if (_i//3 == _k): 
                Cgd[_i,_k+n_plungers-1] = sensor_gate_dot_cap
            # else get 0.0

    # 3. Cds: Sensor placed adjacent to Dot 1
    Cds = np.zeros((n_sensors, n_dots))

    sensor_caps = [.85,.95,.75]

    for _j in range(n_sensors):
        for _i in range(3):
            if (_i + 3*_j < n_dots): 
                Cds[_j,_i + 3*_j] = dot_sensor_cap*sensor_caps[_i]
            else: 
                break


    # 4. Cgs: Pure sensor gate coupling
    Cgs = np.zeros((n_sensors, n_gates))

    active_device = ChargeSensedDotArray(
        Cdd=Cdd,
        Cgd=Cgd,
        Cds=Cds,
        Cgs=Cgs,
        charge_carrier="electrons",
        T=0.01,
    )

    # Calibrate sensor gate S1 bias to steepest transconductance flank
    _vs = np.linspace(-1.5, 0.5, 150)
    _vg = np.zeros((150, n_gates))
    _vg[:, -1] = _vs
    _s, _ = active_device.charge_sensor_open(_vg)
    _grad = np.gradient(_s[:, 0], _vs)
    optimal_s1_bias = float(_vs[np.argmax(np.abs(_grad))])
    return (
        Cdd,
        Cds,
        Cgd,
        active_device,
        all_gate_names,
        charging_energy,
        n_dots,
        n_gates,
        n_sensors,
        optimal_s1_bias,
        plunger_names,
    )


@app.cell
def _(Cdd, Cds, Cgd, np):
    print("Cgd")
    with np.printoptions(precision=4, suppress=True):
        print(Cgd)
    print("Cdd")
    with np.printoptions(precision=4, suppress=True):
        print(Cdd)
    print("Cds")
    with np.printoptions(precision=4, suppress=True):
        print(Cds)

    return


@app.cell(hide_code=True)
def _(charging_energy, mo, plunger_names, set_history, set_state):
    # Reactive sliders for all plunger gates with full [-2.0, 2.0] V range
    start_val = -4*charging_energy
    end_val = 4*charging_energy
    step_val = (end_val - start_val)/20

    raw_dict = {}
    for _p in plunger_names:
        raw_dict[f"{_p}_start"] = mo.ui.slider(
            start=start_val,
            stop=end_val,
            step=step_val,
            value=0.0,
            label=f"{_p} Start (V)",
        )
        def_end = -charging_energy if _p == "P1" else (-charging_energy if _p == "P2" else 0.0)
        raw_dict[f"{_p}_end"] = mo.ui.slider(
            start=start_val,
            stop=end_val,
            step=step_val,
            value=def_end,
            label=f"{_p} End (V)",
        )

    resolution_slider = mo.ui.slider(
        start=40, stop=200, step=20, value=100, label="Resolution"
    )
    raw_dict["resolution"] = resolution_slider

    slider_dict = mo.ui.dictionary(raw_dict)

    # Reset button placed directly in the control panel
    reset_btn = mo.ui.button(
        label="Reset Electron State & History to Vacuum (0...0)",
        on_click=lambda _: (set_state([0, 0, 0, 0, 0]), set_history([])),
    )

    commit_btn = mo.ui.button(
        label="Commit Ray End as Starting State for Next Step",
        kind="success",
    )



    dropdown = mo.ui.dropdown(options=[_p for _p in plunger_names],value=plunger_names[0],label="Select Axis")


    rows = []
    for _p in plunger_names:
        rows.append(mo.hstack([slider_dict[f"{_p}_start"], slider_dict[f"{_p}_end"]], justify="start"))
    rows.append(mo.hstack([slider_dict["resolution"], commit_btn, reset_btn, dropdown], justify="start"))


    panel = mo.vstack(rows)
    return commit_btn, dropdown, panel, slider_dict


@app.cell
def _(panel):
    panel
    return


@app.cell(hide_code=True)
def _(
    active_device,
    all_gate_names,
    commit_btn,
    find_peaks,
    get_history,
    get_state,
    n_dots,
    n_gates,
    np,
    optimal_s1_bias,
    plunger_names,
    set_history,
    set_state,
    slider_dict,
):
    slider_vals = slider_dict.value
    num_pts = int(slider_vals["resolution"])

    v_start = np.zeros(n_gates)
    v_end = np.zeros(n_gates)

    # for _b in range(n_barriers):
    #     v_start[n_dots + _b] = -0.05
    #     v_end[n_dots + _b] = -0.05

    v_start[-1] = optimal_s1_bias
    v_end[-1] = optimal_s1_bias

    for _p in plunger_names:
        _idx = all_gate_names.index(_p)
        v_start[_idx] = slider_vals[f"{_p}_start"]
        v_end[_idx] = slider_vals[f"{_p}_end"]

    vg_ray = np.linspace(v_start, v_end, num_pts)

    # Native qarray simulation of sensor response and ideal ground state
    raw_sensor, ideal_charges = active_device.charge_sensor_open(vg_ray)

    final_charges = ideal_charges[-1].astype(int)
    ideal_final = ideal_charges[-1].astype(int)
    final_plungers = np.array([slider_vals[f"{_p}_end"] for _p in plunger_names])
    latched = False

    # Native qarray sensor signal directly based on potentials
    sens_signal = raw_sensor[:, 0]

    ray_lambda = np.linspace(0.0, 1.0, num_pts)
    d_sens = np.gradient(sens_signal, ray_lambda)
    blip_signal = np.abs(d_sens)

    # Physical threshold ignoring flat background noise
    noise_floor = float(np.median(blip_signal))
    dynamic_thresh = noise_floor + 2.0 * float(np.std(blip_signal))
    min_physical_blip_height = 0.18
    threshold = float(max(min_physical_blip_height, dynamic_thresh))

    peaks, _ = find_peaks(
        blip_signal,
        height=threshold,
        prominence=0.12,
        distance=max(5, num_pts // 20),
    )

    # Traversed charge configurations
    charge_configs = []
    for _q in ideal_charges:
        _q_tuple = tuple(_q.astype(int))
        if not charge_configs or charge_configs[-1] != _q_tuple:
            charge_configs.append(_q_tuple)

    # Handle commit button click: persist final state and append to history log
    persisted_start = np.array(get_state()[:n_dots], dtype=float)
    if commit_btn.value:
        new_hist = list(get_history())
        hist_entry = {
            "step": len(new_hist) + 1,
            "start": persisted_start.astype(int).tolist(),
            "end": final_charges.tolist(),
            "plungers_end": [float(f"{v:.2f}") for v in final_plungers],
            "blips": len(peaks),
        }
        new_hist.append(hist_entry)
        set_history(new_hist)
        set_state(final_charges.tolist())
    return (
        charge_configs,
        final_charges,
        final_plungers,
        ideal_final,
        latched,
        peaks,
        persisted_start,
        ray_lambda,
        threshold,
        v_end,
        v_start,
    )


@app.cell(hide_code=True)
def _(
    active_device,
    charging_energy,
    dropdown,
    final_charges,
    final_plungers,
    latched,
    n_dots,
    n_gates,
    n_sensors,
    np,
    optimal_s1_bias,
    plt,
    plunger_names,
    ray_lambda,
    threshold,
    v_end,
    v_start,
):
    import matplotlib.gridspec as gridspec

    n_csd_pairs = max(1, n_dots - 1)
    _selected_shared_axis = dropdown.value
    idx = plunger_names.index(_selected_shared_axis)

    # Evaluate all sensor responses along the ray and differentiate them.
    ray_vg = (
        v_start[None, :]
        + ray_lambda[:, None] * (v_end - v_start)[None, :]
    )
    ray_vg[:, -1] = optimal_s1_bias

    ray_sensor_readings, _ = active_device.charge_sensor_open(ray_vg)
    blip_signals = abs(np.gradient(ray_sensor_readings, ray_lambda, axis=0))

    # One CSD row and one blip row per sensor, plus one potential row.
    n_rows = 2 * n_sensors + 1
    fig = plt.figure(figsize=(11, 3.2 * n_rows))
    gs = gridspec.GridSpec(
        n_rows,
        3,
        width_ratios=[1, 1, 0.05],
        height_ratios=n_sensors * [1.2] + n_sensors * [0.9] + [1.0],
        figure=fig,
    )

    res_csd = 141

    .013
    p_span = (-2.5*charging_energy, 0.5*charging_energy)
    p_grid = np.linspace(p_span[0], p_span[1], res_csd)
    P_X, P_Y = np.meshgrid(p_grid, p_grid)

    a, b = idx - 1, idx

    # CSD plots: one row and one colorbar per sensor.
    for _j in range(n_sensors):
        row_data = []

        for _i in range(n_csd_pairs):
            if _i in (a, b):
                p_x_idx, p_y_idx = _i, _i + 1

                vg_slice = np.tile(v_end, (res_csd, res_csd, 1))
                vg_slice[:, :, p_x_idx] = P_X
                vg_slice[:, :, p_y_idx] = P_Y
                vg_slice[:, :, -1] = optimal_s1_bias

                sens_2d, _ = active_device.charge_sensor_open(
                    vg_slice.reshape(-1, n_gates)
                )
                csd_img = sens_2d[:, _j].reshape(res_csd, res_csd)
                d_csd = np.hypot(
                    np.gradient(csd_img, axis=0),
                    np.gradient(csd_img, axis=1),
                )
                row_data.append((p_x_idx, p_y_idx, d_csd))

        if not row_data:
            continue

        row_vmin = min(float(np.min(data)) for _, _, data in row_data)
        row_vmax = max(float(np.max(data)) for _, _, data in row_data)
        row_norm = plt.Normalize(vmin=row_vmin, vmax=row_vmax)

        row_images = []
        for col, (p_x_idx, p_y_idx, d_csd) in enumerate(row_data):
            ax_csd = fig.add_subplot(gs[_j, col])
            p_x_name = plunger_names[p_x_idx]
            p_y_name = plunger_names[p_y_idx]

            im = ax_csd.imshow(
                d_csd,
                origin="lower",
                extent=[p_span[0], p_span[1], p_span[0], p_span[1]],
                cmap="viridis",
                norm=row_norm,
                aspect="auto",
            )
            row_images.append(im)

            r_start_x, r_start_y = v_start[p_x_idx], v_start[p_y_idx]
            r_end_x, r_end_y = v_end[p_x_idx], v_end[p_y_idx]

            ax_csd.plot(
                [r_start_x, r_end_x],
                [r_start_y, r_end_y],
                color="#ff4444",
                lw=2.5,
                label="Ray Path",
                zorder=4,
            )
            ax_csd.scatter(
                [r_start_x],
                [r_start_y],
                color="#00ff00",
                edgecolors="black",
                s=80,
                marker="o",
                label="Start",
                zorder=5,
            )
            ax_csd.scatter(
                [r_end_x],
                [r_end_y],
                color="#ff0000",
                edgecolors="black",
                s=80,
                marker="X",
                label="End",
                zorder=5,
            )

            ax_csd.set_xlabel(f"{p_x_name} (V)", fontsize=10)
            ax_csd.set_ylabel(f"{p_y_name} (V)", fontsize=10)
            ax_csd.set_title(
                f"CSD S{_j + 1}: {p_x_name} vs {p_y_name} (Ray Overlay)",
                fontsize=11,
            )
            ax_csd.grid(True, alpha=0.3, color="white", linestyle=":")
            ax_csd.legend(
                loc="upper right",
                frameon=True,
                facecolor="white",
                framealpha=0.8,
                fontsize=8,
            )

        cbar_ax = fig.add_subplot(gs[_j, 2])
        fig.colorbar(row_images[0], cax=cbar_ax, label="|∇CSD|")

    # Blip plots: one plot per sensor.
    for _j in range(n_sensors):
        ax_blip = fig.add_subplot(gs[n_sensors + _j, :])
        signal = blip_signals[:, _j]
        sensor_peaks = np.flatnonzero(signal > threshold)

        ax_blip.plot(
            ray_lambda,
            signal,
            color="#ff7f0e",
            lw=2.0,
            label="|dI/dλ|",
        )
        ax_blip.axhline(
            threshold,
            color="#d62728",
            linestyle=":",
            alpha=0.6,
            label=f"Threshold ({threshold:.2f})",
        )

        if len(sensor_peaks) > 0:
            ax_blip.scatter(
                ray_lambda[sensor_peaks],
                signal[sensor_peaks],
                color="#d62728",
                s=35,
                zorder=5,
                label="Above threshold",
            )

        ax_blip.set_xlabel("Ray Progress λ")
        ax_blip.set_ylabel("Differentiated Signal (a.u.)")
        ax_blip.set_title(f"Ray Blip Measurement — Sensor S{_j + 1}", fontsize=11)
        ax_blip.grid(True, alpha=0.25)
        ax_blip.legend(loc="upper right", frameon=False)

    # Conduction band potential profile.
    ax_pot = fig.add_subplot(gs[2 * n_sensors, :])

    cdd_inv_dots = active_device.cdd_inv_full[:n_dots, :n_dots]
    cgd_dots = active_device.cgd_full[:n_dots, :]
    induced_charge = cgd_dots @ v_end

    barrier_height_meV = 50.0
    gate_potentials_meV = (cdd_inv_dots @ induced_charge) * 90.0
    dot_bottoms_meV = barrier_height_meV - gate_potentials_meV

    x = np.linspace(0, n_dots, 600)
    U_x = np.full_like(x, barrier_height_meV)
    U_x += 100.0 * (
        np.exp(-(x / 0.18) ** 2)
        + np.exp(-((x - n_dots) / 0.18) ** 2)
    )

    for _i in range(n_dots):
        _well_c = _i + 0.5
        _depth = barrier_height_meV - dot_bottoms_meV[_i]
        if _depth > 0:
            U_x -= _depth * np.exp(-((x - _well_c) / 0.28) ** 2)
        else:
            U_x += (-_depth) * np.exp(-((x - _well_c) / 0.28) ** 2)

    ax_pot.plot(x, U_x, "k-", lw=2, label="Conduction Band $E_c(x)$")
    ax_pot.axhline(
        0.0,
        color="#888888",
        linestyle="--",
        lw=1.2,
        alpha=0.7,
        label=r"Fermi Level $E_F = 0$ meV",
    )
    ax_pot.text(
        0.08,
        15.0,
        "◄ Lead L (Reservoir)",
        color="#2ca02c",
        fontsize=9,
        fontweight="bold",
    )

    y_min_plot = min(float(np.min(U_x)) - 25.0, -90.0)
    y_max_plot = max(float(np.max(U_x)) + 30.0, 95.0)
    u_charging_meV = 25.0

    for _i in range(n_dots):
        _well_c = _i + 0.5
        _q = final_charges[_i]
        _p_name = plunger_names[_i]
        _v_p = final_plungers[_i]
        _bottom_meV = dot_bottoms_meV[_i]

        ax_pot.text(
            _well_c,
            y_min_plot + 8.0,
            f"{_p_name} ({_v_p:+.2f}V)\n(n={_q})",
            ha="center",
            va="bottom",
            fontsize=9,
            fontweight="bold",
        )

        for _e in range(_q):
            _e_level = _bottom_meV + 8.0 + _e * u_charging_meV
            ax_pot.hlines(
                _e_level,
                _well_c - 0.18,
                _well_c + 0.18,
                colors="#1f77b4",
                linestyles="-",
                lw=1.5,
                zorder=5,
            )
            ax_pot.scatter(
                [_well_c],
                [_e_level],
                color="#1f77b4",
                s=120,
                edgecolors="#0d3d59",
                linewidth=1.5,
                zorder=6,
            )

    ax_pot.set_xlabel("1D Dot Position (a.u.)", fontsize=10)
    ax_pot.set_ylabel("Potential Energy U(x) (meV)", fontsize=10)
    ax_pot.set_xlim(0, n_dots)
    ax_pot.set_ylim(y_min_plot, y_max_plot)

    title_suffix = " [Isolated Interior Dot Latched Empty]" if latched else ""
    ax_pot.set_title(
        f"Conduction Band Potential & Dot Occupancy at Ray End: "
        f"{final_charges.tolist()}{title_suffix}",
        fontsize=11,
    )
    ax_pot.grid(True, alpha=0.25)
    ax_pot.legend(loc="upper right", frameon=False, fontsize=9)

    fig.tight_layout()

    return (fig,)


@app.cell
def _(fig, mo):
    mo.as_html(fig)
    return


@app.cell(hide_code=True)
def _(
    charge_configs,
    get_history,
    ideal_final,
    latched,
    mo,
    peaks,
    persisted_start,
):
    configs_str = " -> ".join([str(list(_c)) for _c in charge_configs])
    latch_msg = (
        f"  \n⚠️ **Kinetic Blockade:** Interior well was plunged directly without sequential shuttling from left reservoir. Target `{ideal_final.tolist()}` cannot load directly."
        if latched
        else ""
    )

    # Format history table
    history_list = get_history()
    if len(history_list) == 0:
        history_table = "*No steps committed to history yet. Click 'Commit Ray End as Starting State' to record navigation steps.*"
    else:
        hist_rows = [
            f"| Step {h['step']} | `{h['start']}` -> `{h['end']}` | {h['plungers_end']} | {h['blips']} blips |"
            for h in history_list
        ]
        history_table = (
            "| Step | State Transition | Plunger Voltages (V) | Detected Blips |\n"
            "| :--- | :--- | :--- | :--- |\n"
            + "\n".join(hist_rows)
        )

    mo.md(
        f"""
        **Initial Start State:** `{persisted_start.astype(int).tolist()}`  
        **Ray Trajectory States:** {configs_str}  
        **Detected Blips:** `{len(peaks)}`{latch_msg}

        ---
        ### Navigation History Log
        {history_table}
        """
    )
    return


if __name__ == "__main__":
    app.run()
