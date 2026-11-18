import marimo

__generated_with = "0.25.2"
app = marimo.App(width="full")


@app.cell
def _():
    import marimo as mo
    import matplotlib.pyplot as plt
    import numpy as np
    from qarray import ChargeSensedDotArray
    from scipy.signal import find_peaks

    get_static_reset, set_static_reset = mo.state(0)
    static_cache = {
        "v0": {},
        "x": {"P1": 1.0},
        "y": {"P2": 1.0},
        "x_min": None,
        "x_max": None,
        "y_min": None,
        "y_max": None,
    }

    return (
        ChargeSensedDotArray,
        find_peaks,
        mo,
        np,
        plt,
        static_cache,
        get_static_reset,
        set_static_reset,
    )


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
def _(ChargeSensedDotArray, device_selector: marimo.ui.radio, np):
    n_dots = device_selector.value
    n_plungers = n_dots
    # n_barriers = n_dots - 1
    # n_gates = n_plungers + n_barriers + 1
    n_sensors = (n_dots - 1) // 3 + 1

    n_gates = n_plungers + n_sensors

    plunger_names = [f"P{_i + 1}" for _i in range(n_plungers)]
    sensor_names = [f"S{_i + 1}" for _i in range(n_sensors)]
    # barrier_names = [f"B{_i+1}" for _i in range(n_barriers)]
    # all_gate_names = plunger_names + barrier_names + ["S1"]
    all_gate_names = plunger_names + sensor_names

    # QArray assumes e=1, which took time to determine

    attoFarads = 10**-18
    electron_charge = 1.6 * 10 ** (-19)  # Coulumbs
    wiggle_factor = 1

    interdot_cap = 3.0 * attoFarads / electron_charge  # atto Farads

    charging_energy = 0.013  # Volts, 13mV

    gate_dot_cap = 1 / charging_energy  # Coulumbs / Volts -> Farads

    dot_dot_cap = (
        (1 / wiggle_factor) * 2.0 * attoFarads / electron_charge
    )  # atto Farads (typically between 0-10)

    dot_sensor_cap = (
        (1 / wiggle_factor) * 1.0 * attoFarads / electron_charge
    )  # atto Farads (typically between 0-2) is just based on how far the sensor is from the dot, so derived from same as interdot

    dot_dot_diag_cap = (
        (1 / wiggle_factor) * 30 * attoFarads / electron_charge
    )  # Typically about 40-70 atto Farads

    sensor_gate_dot_cap = 0.1 * attoFarads / electron_charge
    # C_diag = electron_charge**2 / charging_energy # Typically about 40-70 atto Farads
    # C_dot_dot = 0 # Typically about 0 to 10 atto Farads

    # Cdd: strictly nearest-neighbor tridiagonal
    Cdd = np.zeros((n_dots, n_dots))
    for _i in range(n_dots - 1):
        Cdd[_i, _i] = dot_dot_diag_cap
        Cdd[_i, _i + 1] = dot_dot_cap  # was .1
        Cdd[_i + 1, _i] = dot_dot_cap
    Cdd[n_dots - 1, n_dots - 1] = dot_dot_diag_cap

    gate_to_sensor_caps = [gate_dot_cap / 6, gate_dot_cap / 4, gate_dot_cap / 6]

    Cgd = np.zeros((n_dots, n_gates))

    # plunger -> dot couplings
    for dot in range(n_dots):
        Cgd[dot, dot] = gate_dot_cap
        if dot > 0:
            Cgd[dot, dot - 1] = gate_dot_cap / 4
        if dot < n_plungers - 1:
            Cgd[dot, dot + 1] = gate_dot_cap / 4
    # sensor gate -> dot couplings
    for sensor in range(n_sensors):
        sensor_col = n_plungers + sensor
        for local_dot, cap in enumerate(gate_to_sensor_caps):
            dot = 3 * sensor + local_dot
            if dot < n_dots:
                Cgd[dot, sensor_col] = cap
    # Cgs: Pure sensor gate coupling
    Cgs = np.zeros((n_sensors, n_gates))
    for sensor in range(n_sensors):
        sensor_col = n_plungers + sensor
        for local_gate, cap in enumerate(gate_to_sensor_caps):
            gate = 3 * sensor + local_gate
            if gate < n_plungers:
                Cgs[sensor, gate] = cap
        Cgs[sensor, sensor_col] = gate_dot_cap

    # Cds: Sensor placed adjacent to Dot 1
    Cds = np.zeros((n_sensors, n_dots))

    sensor_caps = [0.85, 0.95, 0.75]

    for _j in range(n_sensors):
        for _i in range(3):
            if _i + 3 * _j < n_dots:
                Cds[_j, _i + 3 * _j] = dot_sensor_cap * sensor_caps[_i]
            else:
                break

    active_device = ChargeSensedDotArray(
        Cdd=Cdd,
        Cgd=Cgd,
        Cds=Cds,
        Cgs=Cgs,
        charge_carrier="electrons",
        coulomb_peak_width=0.0005,
        T=0.1,
    )
    return (
        Cdd,
        Cds,
        Cgd,
        Cgs,
        active_device,
        all_gate_names,
        charging_energy,
        n_dots,
        n_gates,
        n_plungers,
        n_sensors,
        plunger_names,
    )


@app.cell
def _(Cdd, Cds, Cgd, Cgs, np):
    print("Cgd")
    with np.printoptions(precision=4, suppress=True):
        print(Cgd)
    print("Cdd")
    with np.printoptions(precision=4, suppress=True):
        print(Cdd)
    print("Cds")
    with np.printoptions(precision=4, suppress=True):
        print(Cds)
    print("Cgs")
    with np.printoptions(precision=4, suppress=True):
        print(Cgs)


@app.cell
def _(mo):
    resolution_slider = mo.ui.slider(
        start=40,
        stop=400,
        step=20,
        value=200,
        label="Resolution",
    )

    return (resolution_slider,)


@app.cell
def _(mo):
    view_mode = mo.ui.radio(
        options={
            "Ray Navigation": "ray",
            "Static 2D": "static",
        },
        value="Ray Navigation",
        label="Mode",
    )

    return (view_mode,)


@app.cell(hide_code=True)
def _(
    charging_energy,
    mo,
    n_sensors,
    plunger_names,
    set_history,
    set_state,
    resolution_slider,
):

    start_val = -4 * charging_energy
    end_val = 4 * charging_energy
    step_val = (end_val - start_val) / 50

    ray_dict = {}

    for _p in plunger_names:
        ray_dict[f"{_p}_start"] = mo.ui.slider(
            start=start_val,
            stop=end_val,
            step=step_val,
            value=0.0,
            label=f"{_p} Start (V)",
        )

        default_end = -charging_energy if _p in ("P1", "P2") else 0.0

        ray_dict[f"{_p}_end"] = mo.ui.slider(
            start=start_val,
            stop=end_val,
            step=step_val,
            value=default_end,
            label=f"{_p} End (V)",
        )

    for _i in range(n_sensors):
        ray_dict[f"S{_i + 1}_start"] = mo.ui.slider(
            start=start_val,
            stop=end_val,
            step=(end_val - start_val) / 1000,
            value=0.0,
            label=f"S{_i + 1} Start (V)",
        )

        ray_dict[f"S{_i + 1}_end"] = mo.ui.slider(
            start=start_val,
            stop=end_val,
            step=(end_val - start_val) / 1000,
            value=0.0,
            label=f"S{_i + 1} End (V)",
        )

    ray_controls = mo.ui.dictionary(ray_dict)

    commit_btn = mo.ui.button(
        label="Ray End is new start",
        kind="success",
    )

    reset_btn = mo.ui.button(
        label="Reset State",
        on_click=lambda _: (
            set_state([0, 0, 0, 0, 0]),
            set_history([]),
        ),
    )

    ray_axis = mo.ui.dropdown(
        options=plunger_names,
        value=plunger_names[0],
        label="Shared Axis",
    )

    rays_rows = []

    for _p in plunger_names:
        rays_rows.append(
            mo.hstack(
                [
                    ray_dict[f"{_p}_start"],
                    ray_dict[f"{_p}_end"],
                ]
            )
        )

    for _i in range(n_sensors):
        rays_rows.append(
            mo.hstack(
                [
                    ray_dict[f"S{_i + 1}_start"],
                    ray_dict[f"S{_i + 1}_end"],
                ]
            )
        )

    rays_rows.append(
        mo.hstack(
            [
                resolution_slider,
                commit_btn,
                reset_btn,
                ray_axis,
            ]
        )
    )

    ray_panel = mo.vstack(rays_rows)
    return (
        ray_panel,
        ray_controls,
        ray_axis,
        commit_btn,
    )


@app.cell(hide_code=True)
def _(mo, static_cache, set_static_reset):
    def _reset_static(_):
        static_cache.clear()
        static_cache.update(
            {
                "v0": {},
                "x": {"P1": 1.0},
                "y": {"P2": 1.0},
                "x_min": None,
                "x_max": None,
                "y_min": None,
                "y_max": None,
            }
        )
        set_static_reset(lambda n: n + 1)

    reset_static_btn = mo.ui.button(
        label="Reset",
        kind="danger",
        on_click=_reset_static,
    )
    return (reset_static_btn,)


@app.cell(hide_code=True)
def _(
    charging_energy,
    mo,
    all_gate_names,
    static_cache,
    get_static_reset,
):
    _ = get_static_reset()

    static_start_val = -50 * charging_energy
    static_end_val = 50 * charging_energy
    static_step_val = (static_end_val - static_start_val) / 50

    _v0_dict = {}
    _x_dict = {}
    _y_dict = {}

    for _i, _g in enumerate(all_gate_names):
        # Look up saved value in static_cache, falling back to default
        _v0_init = static_cache["v0"].get(_g, 0.0)
        _x_init = static_cache["x"].get(_g, 1.0 if _i == 0 else 0.0)
        _y_init = static_cache["y"].get(_g, 1.0 if _i == 1 else 0.0)

        _v0_dict[_g] = mo.ui.number(
            value=_v0_init,
            step=0.001,
            debounce=True,
            on_change=lambda val, g=_g: static_cache["v0"].update({g: val}),
        )
        _x_dict[_g] = mo.ui.number(
            value=_x_init,
            step=0.001,
            debounce=True,
            on_change=lambda val, g=_g: static_cache["x"].update({g: val}),
        )
        _y_dict[_g] = mo.ui.number(
            value=_y_init,
            step=0.001,
            debounce=True,
            on_change=lambda val, g=_g: static_cache["y"].update({g: val}),
        )

    v0_controls = mo.ui.dictionary(_v0_dict)
    x_controls = mo.ui.dictionary(_x_dict)
    y_controls = mo.ui.dictionary(_y_dict)

    equation = mo.md(
        r"""
        ### Virtual Gate Basis

        $\mathbf{V} = \mathbf{V}_0 + x\,\mathbf{X} + y\,\mathbf{Y}$
        """
    ).center()

    header = mo.hstack(
        [mo.md("**Axis**").center()]
        + [mo.md(f"**{_g}**").center() for _g in all_gate_names],
        widths="equal",
    )

    v0_row = mo.hstack(
        [mo.md(r"$\mathbf{V}_0$").center()]
        + [v0_controls[_g].center() for _g in all_gate_names],
        widths="equal",
    )
    x_row = mo.hstack(
        [mo.md(r"$\mathbf{X}$").center()]
        + [x_controls[_g].center() for _g in all_gate_names],
        widths="equal",
    )
    y_row = mo.hstack(
        [mo.md(r"$\mathbf{Y}$").center()]
        + [y_controls[_g].center() for _g in all_gate_names],
        widths="equal",
    )

    virtual_gate_matrix = mo.vstack([equation, header, v0_row, x_row, y_row])

    box_style = {"width": "85px", "min-width": "85px"}

    x_min = mo.ui.number(
        start=static_start_val,
        stop=static_end_val,
        step=static_step_val,
        value=static_cache["x_min"]
        if static_cache["x_min"] is not None
        else float(-charging_energy),
        debounce=True,
        full_width=False,
        on_change=lambda val: static_cache.update({"x_min": val}),
    )

    x_max = mo.ui.number(
        start=static_start_val,
        stop=static_end_val,
        step=static_step_val,
        value=static_cache["x_max"]
        if static_cache["x_max"] is not None
        else float(charging_energy),
        debounce=True,
        full_width=False,
        on_change=lambda val: static_cache.update({"x_max": val}),
    )

    y_min = mo.ui.number(
        start=static_start_val,
        stop=static_end_val,
        step=static_step_val,
        value=static_cache["y_min"]
        if static_cache["y_min"] is not None
        else float(-charging_energy),
        debounce=True,
        full_width=False,
        on_change=lambda val: static_cache.update({"y_min": val}),
    )

    y_max = mo.ui.number(
        start=static_start_val,
        stop=static_end_val,
        step=static_step_val,
        value=static_cache["y_max"]
        if static_cache["y_max"] is not None
        else float(charging_energy),
        debounce=True,
        full_width=False,
        on_change=lambda val: static_cache.update({"y_max": val}),
    )

    x_domain = mo.hstack(
        [
            mo.md(r"$x\text{ domain: }[$"),
            x_min.style(box_style),
            mo.md("$,$"),
            x_max.style(box_style),
            mo.md("$]$"),
        ],
        justify="start",
        align="center",
        gap=0.25,
    )

    y_domain = mo.hstack(
        [
            mo.md(r"$y\text{ domain: }[$"),
            y_min.style(box_style),
            mo.md("$,$"),
            y_max.style(box_style),
            mo.md("$]$"),
        ],
        justify="start",
        align="center",
        gap=0.25,
    )

    return (
        virtual_gate_matrix,
        x_domain,
        y_domain,
        v0_controls,
        x_controls,
        y_controls,
        x_min,
        x_max,
        y_min,
        y_max,
    )


@app.cell(hide_code=True)
def _(
    mo,
    virtual_gate_matrix,
    x_domain,
    y_domain,
    reset_static_btn,
    resolution_slider,
):
    static_panel = mo.vstack(
        [
            virtual_gate_matrix,
            mo.hstack(
                [
                    x_domain,
                    y_domain,
                    reset_static_btn,
                ]
            ),
            resolution_slider,
        ]
    )

    return (static_panel,)


@app.cell(hide_code=True)
def _(view_mode, ray_panel, static_panel):
    value = view_mode.value
    if value == "ray":
        panel = ray_panel
    else:
        panel = static_panel

    return (panel,)


@app.cell
def _(view_mode):
    view_mode


@app.cell
def _(panel):
    panel


@app.cell(hide_code=True)
def _(
    view_mode,
    active_device,
    all_gate_names,
    commit_btn,
    find_peaks,
    get_history,
    get_state,
    n_dots,
    n_gates,
    n_plungers,
    n_sensors,
    np,
    plunger_names,
    set_history,
    set_state,
    ray_controls,
    resolution_slider,
):
    charge_configs = []
    final_charges = np.array([])
    final_plungers = np.array([])
    ideal_final = np.array([])
    latched = False
    peaks = []
    persisted_start = np.array([])
    ray_lambda = np.array([])
    threshold = 0.0
    v_end = np.array([])
    v_start = np.array([])
    if view_mode.value == "ray":
        slider_vals = ray_controls.value
        num_pts = int(resolution_slider.value)

        v_start = np.zeros(n_gates)
        v_end = np.zeros(n_gates)

        # for _b in range(n_barriers):
        #     v_start[n_dots + _b] = -0.05
        #     v_end[n_dots + _b] = -0.05
        # assigns slider vals for sensor gates to be last n_sensors
        for _i in range(n_sensors):
            v_start[_i + n_plungers] = slider_vals[f"S{_i + 1}_start"]
            v_end[_i + n_plungers] = slider_vals[f"S{_i + 1}_end"]

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
    v0_controls,
    x_controls,
    y_controls,
    x_min,
    x_max,
    y_min,
    y_max,
    resolution_slider,
    n_gates,
    all_gate_names,
    np,
):

    v0_vector = np.array([v0_controls[_g].value for _g in all_gate_names])
    x_vector = np.array([x_controls[_g].value for _g in all_gate_names])
    y_vector = np.array([y_controls[_g].value for _g in all_gate_names])

    static_res_csd = int(resolution_slider.value)

    x_grid = np.linspace(
        x_min.value,
        x_max.value,
        static_res_csd,
    )
    y_grid = np.linspace(
        y_min.value,
        y_max.value,
        static_res_csd,
    )

    static_P_X, static_P_Y = np.meshgrid(x_grid, y_grid)
    vg = np.zeros((static_res_csd * static_res_csd, n_gates))

    vg[:, : len(all_gate_names)] = (
        v0_vector[None, :]
        + static_P_X.ravel()[:, None] * x_vector[None, :]
        + static_P_Y.ravel()[:, None] * y_vector[None, :]
    )
    sensor_response, charge_states = active_device.charge_sensor_open(vg)

    x_name = "Virtual X"
    y_name = "Virtual Y"

    return (
        sensor_response,
        charge_states,
        static_P_X,
        static_P_Y,
        x_name,
        y_name,
        static_res_csd,
    )


@app.cell(hide_code=True)
def _(
    view_mode,
    sensor_response,
    static_P_X,
    static_P_Y,
    x_name,
    y_name,
    static_res_csd,
    n_sensors,
    np,
    plt,
):

    static_fig = None
    if view_mode.value == "static":
        static_fig, axs = plt.subplots(
            n_sensors,
            1,
            figsize=(12, 4 * n_sensors),
        )

        if n_sensors == 1:
            axs = [axs]

        static_x_min = float(static_P_X.min())
        static_x_max = float(static_P_X.max())
        static_y_min = float(static_P_Y.min())
        static_y_max = float(static_P_Y.max())

        for sensor_idx, ax in enumerate(axs):
            image = sensor_response[:, sensor_idx].reshape(
                static_res_csd,
                static_res_csd,
            )

            gradient = np.gradient(image, axis=0) + np.gradient(image, axis=1)

            static_im = ax.imshow(
                gradient,
                origin="lower",
                extent=[
                    static_x_min,
                    static_x_max,
                    static_y_min,
                    static_y_max,
                ],
                cmap="viridis",
                aspect="equal",
            )

            ax.set_xlabel(f"{x_name} (V)")
            ax.set_ylabel(f"{y_name} (V)")
            ax.set_title(f"Sensor S{sensor_idx + 1}: {x_name} vs {y_name}")

            static_fig.colorbar(
                static_im,
                ax=ax,
                label="|∇Sensor|",
            )

        static_fig.tight_layout()

    return (static_fig,)


@app.cell(hide_code=True)
def _(
    view_mode,
    active_device,
    charging_energy,
    ray_axis,
    final_charges,
    final_plungers,
    latched,
    n_dots,
    n_gates,
    n_sensors,
    np,
    plt,
    plunger_names,
    ray_lambda,
    threshold,
    v_end,
    v_start,
):
    ray_fig = None

    if view_mode.value == "ray":
        from matplotlib import gridspec

        n_csd_pairs = max(1, n_dots - 1)
        _selected_shared_axis = ray_axis.value
        idx = plunger_names.index(_selected_shared_axis)

        # Evaluate all sensor responses along the ray and differentiate them.
        ray_vg = v_start[None, :] + ray_lambda[:, None] * (v_end - v_start)[None, :]

        ray_sensor_readings, _ = active_device.charge_sensor_open(ray_vg)
        # blip_signals = abs(np.gradient(ray_sensor_readings, ray_lambda, axis=0))
        blip_signals = np.gradient(ray_sensor_readings, ray_lambda, axis=0)

        # One CSD row and one blip row per sensor, plus one potential row.
        n_rows = 2 * n_sensors + 1
        ray_fig = plt.figure(figsize=(15, 3.2 * n_rows))
        gs = gridspec.GridSpec(
            n_rows,
            3,
            width_ratios=[1, 1, 0.05],
            height_ratios=n_sensors * [1.2] + n_sensors * [0.9] + [1.0],
            figure=ray_fig,
        )

        res_csd = 255

        p_span = (-5 * charging_energy, 2 * charging_energy)
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
                ax_csd = ray_fig.add_subplot(gs[_j, col])
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

            cbar_ax = ray_fig.add_subplot(gs[_j, 2])
            ray_fig.colorbar(row_images[0], cax=cbar_ax, label="|∇CSD|")

        # Blip plots: one plot per sensor.
        for _j in range(n_sensors):
            ax_blip = ray_fig.add_subplot(gs[n_sensors + _j, :])
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
        ax_pot = ray_fig.add_subplot(gs[2 * n_sensors, :])

        cdd_inv_dots = active_device.cdd_inv_full[:n_dots, :n_dots]
        cgd_dots = active_device.cgd_full[:n_dots, :]
        induced_charge = cgd_dots @ v_end

        barrier_height_meV = 50.0
        gate_potentials_meV = (cdd_inv_dots @ induced_charge) * 90.0
        dot_bottoms_meV = barrier_height_meV - gate_potentials_meV

        x = np.linspace(0, n_dots, 600)
        U_x = np.full_like(x, barrier_height_meV)
        U_x += 100.0 * (
            np.exp(-((x / 0.18) ** 2)) + np.exp(-(((x - n_dots) / 0.18) ** 2))
        )

        for _i in range(n_dots):
            _well_c = _i + 0.5
            _depth = barrier_height_meV - dot_bottoms_meV[_i]
            if _depth > 0:
                U_x -= _depth * np.exp(-(((x - _well_c) / 0.28) ** 2))
            else:
                U_x += (-_depth) * np.exp(-(((x - _well_c) / 0.28) ** 2))

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

        ray_fig.tight_layout()
    return (ray_fig,)


@app.cell
def _(view_mode, static_fig, ray_fig, mo):
    fig = ray_fig
    if view_mode.value == "static":
        fig = static_fig

    mo.as_html(fig)


@app.cell(hide_code=True)
def _(
    view_mode,
    charge_configs,
    get_history,
    ideal_final,
    latched,
    mo,
    peaks,
    persisted_start,
):
    if view_mode.value != "ray":
        mo.md("### Static 2D Mode")
    else:
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
                "| :--- | :--- | :--- | :--- |\n" + "\n".join(hist_rows)
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


if __name__ == "__main__":
    app.run()
