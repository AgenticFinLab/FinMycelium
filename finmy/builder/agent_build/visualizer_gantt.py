"""
Present the event cascade as a Gantt chart.
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os


class EventCascadeGanttVisualizer:
    def __init__(self):
        # Distinct colors for participants (Tab20 hex codes) - copied from visualizer.py
        self.colors = [
            "#1f77b4",
            "#aec7e8",
            "#ff7f0e",
            "#ffbb78",
            "#2ca02c",
            "#98df8a",
            "#d62728",
            "#ff9896",
            "#9467bd",
            "#c5b0d5",
            "#8c564b",
            "#c49c94",
            "#e377c2",
            "#f7b6d2",
            "#7f7f7f",
            "#c7c7c7",
            "#bcbd22",
            "#dbdb8d",
            "#17becf",
            "#9edae5",
        ]
        # Plotly markers (different from Matplotlib)
        self.markers = [
            "circle",
            "square",
            "diamond",
            "cross",
            "x",
            "triangle-up",
            "triangle-down",
            "pentagon",
            "hexagon",
            "star",
            "diamond-tall",
            "diamond-wide",
            "hourglass",
            "bowtie",
        ]

        # Maps participant_id -> (color, marker)
        self.participant_style_map = {}
        # Maps participant_type -> assigned color
        self.type_color_map = {}
        # Tracks how many participants of a certain type have been seen
        self.type_participant_count = {}

        # Relation Styling
        self.relation_style_map = {}
        # Plotly dash styles corresponding to ["-", "--", "-.", ":"]
        self.dash_styles = ["solid", "dash", "dashdot", "dot"]
        self.relation_colors = [
            "#e41a1c",
            "#377eb8",
            "#4daf4a",
            "#984ea3",
            "#ff7f00",
            "#ffff33",
            "#a65628",
            "#f781bf",
            "#999999",
        ]

    def _get_participant_style(self, p_id, p_type):
        """
        Registers a participant and assigns a consistent style (color + marker).
        """
        if p_id not in self.participant_style_map:
            # Determine color based on Type
            if p_type not in self.type_color_map:
                type_idx = len(self.type_color_map)
                self.type_color_map[p_type] = self.colors[type_idx % len(self.colors)]

            color = self.type_color_map[p_type]

            # Determine marker based on count within this Type
            if p_type not in self.type_participant_count:
                self.type_participant_count[p_type] = 0

            count = self.type_participant_count[p_type]
            marker = self.markers[count % len(self.markers)]
            self.type_participant_count[p_type] += 1

            self.participant_style_map[p_id] = (color, marker)

        return self.participant_style_map[p_id]

    def _get_relation_style(self, rel_name):
        if rel_name not in self.relation_style_map:
            idx = len(self.relation_style_map)
            color = self.relation_colors[idx % len(self.relation_colors)]
            dash = self.dash_styles[idx % len(self.dash_styles)]
            self.relation_style_map[rel_name] = (color, dash)
        return self.relation_style_map[rel_name]

    def plot_cascade(self, cascade_data, output_path=None):
        """
        Generates an interactive Gantt chart from the event cascade data.

        Args:
            cascade_data (dict): The event cascade JSON object.
            output_path (str, optional): Path to save the output HTML file.

        Returns:
            fig: The Plotly figure object.
        """

        # --- Helpers ---

        def parse_date(d_obj):
            """Parse date from dict with 'value' or direct string; no silent defaults."""
            if d_obj is None:
                return None
            if isinstance(d_obj, dict):
                d_str = d_obj["value"]
            else:
                d_str = d_obj
            if isinstance(d_str, str) and d_str.lower() == "unknown":
                return None
            return pd.to_datetime(d_str)

        def gran_code_for(v):
            if v is None:
                return None
            if isinstance(v, dict):
                v = v.get("value")
            if not isinstance(v, str):
                return None
            s = v.strip()
            if not s:
                return None
            if s.lower() == "unknown":
                return None
            col = s.count(":")
            if col >= 2:
                return "YMDHMS"
            if col == 1:
                return "YMDHM"
            if " " in s and s.split(" ", 1)[1] and s.split(" ", 1)[1].count(":") == 0:
                return "YMDH"
            dash = s.count("-")
            if dash >= 2:
                return "YMD"
            if dash == 1:
                return "YM"
            if dash == 0 and s.isdigit() and len(s) == 4:
                return "Y"
            return "YMDHMS"

        # --- 1. Parse Data into DataFrame ---
        rows = []
        gran_levels = []
        stages = cascade_data["stages"]

        for stage in stages:
            stage_id = stage["stage_id"]
            stage_name = stage["name"]["value"]
            stage_start_raw = stage["start_time"]
            stage_end_raw = stage["end_time"]
            stage_descs = stage.get("descriptions", [])

            # Format descriptions
            desc_lines = []
            if isinstance(stage_descs, list):
                for d in stage_descs:
                    if isinstance(d, dict) and "value" in d:
                        desc_lines.append(f"- {d['value']}")
                    elif isinstance(d, str):
                        desc_lines.append(f"- {d}")
            desc_str = "<br>".join(desc_lines) if desc_lines else "None"

            stage_start = parse_date(stage_start_raw)
            stage_end = parse_date(stage_end_raw)
            gran_levels.append(gran_code_for(stage_start_raw))
            gran_levels.append(gran_code_for(stage_end_raw))

            stage_label = f"STAGE: {stage_id}"
            rows.append(
                {
                    "Task": stage_label,
                    "Start": stage_start,
                    "Finish": stage_end,
                    "Type": "Stage",
                    "Group": stage_id,
                    "StageName": stage_name,
                    "ID": stage_id,
                    "Description": f"Stage: {stage_name}<br>Descriptions:<br>{desc_str}",
                }
            )

            episodes = stage["episodes"]
            episodes.sort(key=lambda x: parse_date(x["start_time"]) or pd.Timestamp.min)

            for ep_i, ep in enumerate(episodes):
                ep_id = ep["episode_id"]
                ep_title = ep["name"]["value"]
                ep_start_raw = ep["start_time"]
                ep_end_raw = ep["end_time"]
                ep_descs = ep.get("descriptions", [])

                # Format episode descriptions
                ep_desc_lines = []
                if isinstance(ep_descs, list):
                    for d in ep_descs:
                        if isinstance(d, dict) and "value" in d:
                            ep_desc_lines.append(f"- {d['value']}")
                        elif isinstance(d, str):
                            ep_desc_lines.append(f"- {d}")
                ep_desc_str = "<br>".join(ep_desc_lines) if ep_desc_lines else "None"

                ep_index = ep.get("index_in_stage", ep_i)

                ep_start = parse_date(ep_start_raw)
                ep_end = parse_date(ep_end_raw)
                gran_levels.append(gran_code_for(ep_start_raw))
                gran_levels.append(gran_code_for(ep_end_raw))

                participants = ep["participants"]
                parsed_parts = []
                for p in participants:
                    p_id = p["participant_id"]
                    p_name = p["name"]["value"]
                    p_type = p["participant_type"]["value"]

                    # Extract Role
                    p_role = "unknown"
                    if (
                        "base_role" in p
                        and isinstance(p["base_role"], dict)
                        and "value" in p["base_role"]
                    ):
                        p_role = p["base_role"]["value"]

                    # Extract Attributes
                    attr_lines = []
                    raw_attrs = p.get("attributes", {})
                    if isinstance(raw_attrs, dict):
                        for k, v in raw_attrs.items():
                            val = (
                                v.get("value", "unknown")
                                if isinstance(v, dict)
                                else str(v)
                            )
                            attr_lines.append(f"{k}: {val}")
                    p_attr_str = "<br>".join(attr_lines) if attr_lines else "None"

                    # Extract Actions
                    act_lines = []
                    raw_acts = p.get("actions", [])
                    if isinstance(raw_acts, list):
                        for act in raw_acts:
                            if (
                                isinstance(act, dict)
                                and "name" in act
                                and isinstance(act["name"], dict)
                                and "value" in act["name"]
                            ):
                                act_lines.append(f"- {act['name']['value']}")
                    p_act_str = "<br>".join(act_lines) if act_lines else "None"

                    parsed_parts.append(
                        {
                            "id": p_id,
                            "name": p_name,
                            "type": p_type,
                            "role": p_role,
                            "attributes": p_attr_str,
                            "actions": p_act_str,
                        }
                    )

                p_names = [p["name"] for p in parsed_parts]
                p_str = ", ".join(p_names) if p_names else "None"

                # Parse Relations
                parsed_rels = []
                raw_rels = ep["participant_relations"]
                for r in raw_rels:
                    src = r["from_participant_id"]
                    dst = r["to_participant_id"]

                    rel_name = r["relation_name"]["value"]
                    rel_type = r["relation_type"]["value"]

                    full_rel_name = rel_name
                    if rel_type and rel_type.lower() != "unspecified":
                        full_rel_name = f"{rel_name} ({rel_type})"

                    if src and dst:
                        parsed_rels.append(
                            {"src": src, "dst": dst, "name": full_rel_name}
                        )

                rel_count = len(parsed_rels)

                ep_label = f"{ep_title} ({ep_id})"
                rows.append(
                    {
                        "Task": ep_label,
                        "Start": ep_start,
                        "Finish": ep_end,
                        "Type": "Episode",
                        "Group": stage_id,
                        "ID": ep_id,
                        "IndexInStage": ep_index,
                        "Description": f"Episode: {ep_title}<br>Descriptions:<br>{ep_desc_str}",
                        "Title": ep_title,
                        "Participants": parsed_parts,
                        "Relations": parsed_rels,
                    }
                )

        if not rows:
            print("No data found to plot.")
            return None

        # --- 2. Re-organize for custom layout ---
        fig = go.Figure()

        def get_colors(n):
            return px.colors.qualitative.Plotly * (n // 10 + 1)

        unique_stages = sorted(
            list(set(row["Group"] for row in rows if row["Type"] == "Stage"))
        )
        colors = get_colors(len(unique_stages))
        color_map = {sid: colors[i] for i, sid in enumerate(unique_stages)}

        stage_rows = [r for r in rows if r["Type"] == "Stage"]
        episode_rows = [r for r in rows if r["Type"] == "Episode"]

        # Sort Episodes globally
        episode_rows.sort(key=lambda x: x["Start"] or pd.Timestamp.min)

        # --- Adaptive Sizing Calculation ---
        # Calculate visual parameters based on data density
        max_eps_in_stage = 0
        for sid in unique_stages:
            count = len([r for r in episode_rows if r["Group"] == sid])
            if count > max_eps_in_stage:
                max_eps_in_stage = count

        y_stage = 2.0
        episode_y_step = 1.8
        episode_y_base = y_stage + y_stage

        # Estimate Y range
        est_max_y = episode_y_base
        if max_eps_in_stage > 0:
            est_max_y += (max_eps_in_stage - 1) * episode_y_step

        total_y_span = est_max_y + 2.0  # Add some margin

        # Calculate Plot Height
        # Using the same formula as in layout
        plot_height = max(600, 150 + len(episode_rows) * 25)

        # Pixels per Y unit
        px_per_unit = plot_height / total_y_span

        # Bar height in pixels (0.8 data units)
        bar_height_px = 0.8 * px_per_unit

        # Adaptive Marker Size & Line Width
        # Aim to fit ~7 tiers vertically within the bar (reduced size)
        calc_marker_size = bar_height_px / 7.0
        adaptive_marker_size = max(1.5, min(6, calc_marker_size))
        adaptive_line_width = max(0.5, adaptive_marker_size / 3.0)

        episode_y_positions_global = []

        # Calculate global time range
        valid_starts = [r["Start"] for r in rows if r["Start"] is not None]
        valid_ends = [r["Finish"] for r in rows if r["Finish"] is not None]

        default_start = pd.Timestamp.now()
        default_end = default_start + pd.Timedelta(days=1)

        if valid_starts and valid_ends:
            min_time = min(valid_starts)
            max_time = max(valid_ends)
            duration = max_time - min_time
            if duration.total_seconds() == 0:
                duration = pd.Timedelta(hours=1)
            buffer = min(duration * 0.05, pd.Timedelta(hours=1))
            range_x = [min_time - buffer, max_time + buffer]
        else:
            min_time = default_start
            max_time = default_end
            range_x = [min_time, max_time]

        use_real_time = len(valid_starts) > 0
        span_total = max_time - min_time
        if span_total.total_seconds() <= 0:
            span_total = pd.Timedelta(hours=1)
        default_dur_sec = max(span_total.total_seconds(), 3600) / 20.0
        end_buffer = min(span_total * 0.05, pd.Timedelta(hours=1))
        ep_durations_sec = []
        for r in episode_rows:
            s = r["Start"]
            f = r["Finish"]
            if s is not None and f is not None:
                d = (f - s).total_seconds()
                ep_durations_sec.append(d if d > 0 else default_dur_sec)
            else:
                ep_durations_sec.append(default_dur_sec)
        mdur = (
            pd.Series(ep_durations_sec).median()
            if ep_durations_sec
            else default_dur_sec
        )
        ep_starts_sorted = sorted(
            [s for s in (r["Start"] for r in episode_rows) if s is not None]
        )
        gap_secs = []
        for i in range(len(ep_starts_sorted) - 1):
            g = (ep_starts_sorted[i + 1] - ep_starts_sorted[i]).total_seconds()
            if g > 0:
                gap_secs.append(g)
        mgap = pd.Series(gap_secs).median() if gap_secs else mdur
        base_sec = max(mdur, mgap)
        window_sec = base_sec * 4.0
        min_sec = max(span_total.total_seconds() * 0.06, base_sec * 2.0)
        max_sec = span_total.total_seconds() * 0.22
        if window_sec < min_sec:
            window_sec = min_sec
        if window_sec > max_sec:
            window_sec = max_sec
        slider_min_sec = max(span_total.total_seconds() * 0.01, base_sec * 0.5)
        slider_max_sec = window_sec
        initial_start = ep_starts_sorted[0] if ep_starts_sorted else min_time
        initial_end_candidate = initial_start + pd.Timedelta(seconds=window_sec)
        max_end_allowed = max_time + end_buffer
        initial_end = (
            initial_end_candidate
            if initial_end_candidate <= max_end_allowed
            else max_end_allowed
        )
        if initial_end == max_end_allowed:
            initial_start = initial_end - pd.Timedelta(seconds=window_sec)
            if initial_start < min_time:
                initial_start = min_time
        range_x_initial = [initial_start, initial_end]

        # Coordinate Helper
        def get_viz_coords(row, ref_min_time):
            start = row["Start"]
            finish = row["Finish"]

            total_span = (max_time - min_time).total_seconds()
            if total_span <= 0:
                total_span = 3600  # 1 hour fallback
            default_dur_sec = total_span / 20.0

            if start is None:
                start_val = ref_min_time
                is_imputed = True
            else:
                start_val = start
                is_imputed = False

            if finish is None:
                finish_val = start_val + pd.Timedelta(seconds=default_dur_sec)
            else:
                finish_val = finish

            duration_ms = (finish_val - start_val).total_seconds() * 1000
            if duration_ms <= 0:
                duration_ms = default_dur_sec * 1000

            return start_val, duration_ms, is_imputed

        # Time label format aligned with x-axis granularity
        gran_levels_clean = [g for g in gran_levels if g is not None]
        order_map = {"Y": 0, "YM": 1, "YMD": 2, "YMDH": 3, "YMDHM": 4, "YMDHMS": 5}
        fmt_code = (
            max(gran_levels_clean, key=lambda c: order_map.get(c, 0))
            if gran_levels_clean
            else "YMDHM"
        )
        fmt_map = {
            "Y": "%Y",
            "YM": "%Y-%m",
            "YMD": "%Y-%m-%d",
            "YMDH": "%Y-%m-%d %H",
            "YMDHM": "%Y-%m-%d %H:%M",
            "YMDHMS": "%Y-%m-%d %H:%M:%S",
        }
        time_label_fmt = fmt_map.get(fmt_code, "%Y-%m-%d %H:%M")

        # --- Pre-calculate Time Label Tiers (Per-Episode Staggering) ---
        # Strategy: Assign one height tier per episode (so Start/End are aligned).
        # Check for overlap with already-placed episodes on each tier.
        # "Overlap" means the time points (start or end) are too close.

        # 7 tiers from 0.1 to 1.0
        label_tiers = [0.1 + i * 0.15 for i in range(7)]

        # Track occupied time points per tier: tier_index -> list of timestamps
        tier_occupancy = {i: [] for i in range(len(label_tiers))}

        total_span_sec = (max_time - min_time).total_seconds()
        if total_span_sec <= 0:
            total_span_sec = 3600

        # Buffer: 5% of total span. If a new point is within this distance
        # of an existing point on the same tier, it's a conflict.
        gap_thresh = pd.Timedelta(seconds=total_span_sec * 0.05)

        # Sort episodes by start time to process sequentially
        sorted_episodes = sorted(
            episode_rows, key=lambda x: get_viz_coords(x, min_time)[0]
        )

        tier_map = {}  # (ep_id, type) -> y_val

        for i, r in enumerate(sorted_episodes):
            s_val, dur_ms, _ = get_viz_coords(r, min_time)
            e_val = s_val + pd.to_timedelta(dur_ms, unit="ms")

            # Find best tier
            best_tier_idx = -1

            # Try to find a tier with no conflict for BOTH start and end
            for t_idx in range(len(label_tiers)):
                conflict = False
                existing_pts = tier_occupancy[t_idx]

                # Check against all existing points on this tier
                # (Optimization: could just check the last few, but N is small)
                for pt in existing_pts:
                    # Check distance to Start
                    if abs(pt - s_val) < gap_thresh:
                        conflict = True
                        break
                    # Check distance to End
                    if abs(pt - e_val) < gap_thresh:
                        conflict = True
                        break

                if not conflict:
                    best_tier_idx = t_idx
                    break

            # Fallback if all tiers busy
            if best_tier_idx == -1:
                best_tier_idx = i % len(label_tiers)

            # Assign and Record
            y_val = label_tiers[best_tier_idx]
            ep_id = r["ID"]
            tier_map[(ep_id, "start")] = y_val
            tier_map[(ep_id, "end")] = y_val

            tier_occupancy[best_tier_idx].append(s_val)
            tier_occupancy[best_tier_idx].append(e_val)

        # --- Plot Stages (Y=0) ---
        for sid in unique_stages:
            s_group_rows = [r for r in stage_rows if r["Group"] == sid]
            if not s_group_rows:
                continue

            x_durs, x_starts, hovers, texts = [], [], [], []

            total_span_ms = max((max_time - min_time).total_seconds() * 1000, 1)

            for r in s_group_rows:
                s_val, dur, _ = get_viz_coords(r, min_time)
                x_starts.append(s_val)
                x_durs.append(dur)
                hovers.append(r["Description"])

                # Wrap Stage Text
                lbl = r["StageName"]
                bar_frac = min(max(dur / total_span_ms, 0.0), 1.0)
                max_chars = max(10, int(70 * bar_frac))

                words = str(lbl).split(" ")
                lines = []
                buf = ""
                for w in words:
                    add = (buf + (" " if buf else "") + w).strip()
                    if len(add) <= max_chars:
                        buf = add
                    else:
                        if buf:
                            lines.append(buf)
                            buf = w
                        else:
                            lines.append(w[:max_chars])
                            rem = w[max_chars:]
                            while rem:
                                lines.append(rem[:max_chars])
                                rem = rem[max_chars:]
                if buf:
                    lines.append(buf)
                wrapped = "<br>".join(lines)

                texts.append(wrapped)

            fig.add_trace(
                go.Bar(
                    x=x_durs,
                    y=[y_stage] * len(x_durs),
                    base=x_starts,
                    orientation="h",
                    name=f"Stage: {sid}",
                    marker=dict(color="#ADD8E6", line=dict(color="black", width=1)),
                    hovertext=hovers,
                    text=texts,
                    textposition="inside",
                    insidetextanchor="middle",
                    textfont=dict(color="black", size=12),
                    legendgroup=sid,
                    showlegend=False,
                    width=1.4,
                )
            )
            for i in range(len(x_starts)):
                start_ts = x_starts[i]
                dur_ms = x_durs[i]
                end_ts = start_ts + pd.to_timedelta(dur_ms, unit="ms")
                fig.add_shape(
                    type="line",
                    x0=start_ts,
                    x1=start_ts,
                    y0=0,
                    y1=y_stage,
                    xref="x",
                    yref="y",
                    line=dict(color="#ADD8E6", width=1, dash="dash"),
                )
                fig.add_shape(
                    type="line",
                    x0=end_ts,
                    x1=end_ts,
                    y0=0,
                    y1=y_stage,
                    xref="x",
                    yref="y",
                    line=dict(color="#ADD8E6", width=1, dash="dash"),
                )
                mid_x = start_ts + pd.to_timedelta(dur_ms / 2.0, unit="ms")
                bottom_y = y_stage - (1.4 / 2.0) - 0.10
                fig.add_annotation(
                    x=mid_x,
                    y=bottom_y,
                    text=f"Stage: {sid}",
                    showarrow=False,
                    align="center",
                    yanchor="top",
                    font=dict(size=11, color="black"),
                )
            for i in range(len(x_starts)):
                start_ts = x_starts[i]
                dur_ms = x_durs[i]
                end_ts = start_ts + pd.to_timedelta(dur_ms, unit="ms")
                fig.add_shape(
                    type="line",
                    x0=start_ts,
                    x1=start_ts,
                    y0=0,
                    y1=y_stage,
                    xref="x",
                    yref="y",
                    line=dict(color="#ADD8E6", width=1, dash="dash"),
                )
                fig.add_shape(
                    type="line",
                    x0=end_ts,
                    x1=end_ts,
                    y0=0,
                    y1=y_stage,
                    xref="x",
                    yref="y",
                    line=dict(color="#ADD8E6", width=1, dash="dash"),
                )

        # --- Plot Episodes (Y > 0) ---
        for sid in unique_stages:
            local_eps = sorted(
                [r for r in episode_rows if r["Group"] == sid],
                key=lambda r: r.get("IndexInStage", 0),
            )
            if not local_eps:
                continue

            x_durs, x_starts, y_pos, hovers, texts = [], [], [], [], []

            # For participant markers
            part_xs = []
            part_ys = []
            part_colors = []
            part_symbols = []
            part_hovers = []

            # Store segments for relations: key=(color, dash, name) -> lists of x, y (with None breaks)
            relation_segments = {}

            for j, r in enumerate(local_eps):
                s_val, dur, is_imp = get_viz_coords(r, min_time)
                x_starts.append(s_val)
                x_durs.append(dur)
                y_val = episode_y_base + j * episode_y_step
                y_pos.append(y_val)
                episode_y_positions_global.append(y_val)
                hovers.append(r["Description"])
                lbl = r["Title"]
                if is_imp:
                    lbl += " (?)"
                texts.append(lbl)

                # --- Participants ---
                parts = r.get("Participants", [])
                # Store local coordinates for relations within this episode
                local_p_coords = {}

                if parts:
                    num_parts = len(parts)
                    start_ts = s_val
                    dur_ms = dur

                    # 1. Build Adjacency Graph for Reordering
                    rels = r.get("Relations", [])
                    adj = {p["id"]: [] for p in parts}
                    for rel in rels:
                        src = rel.get("src")
                        dst = rel.get("dst")
                        if src in adj and dst in adj:
                            adj[src].append(dst)
                            adj[dst].append(src)

                    # 2. BFS/Connected Components Reordering
                    ordered_parts = []
                    visited = set()

                    # Sort parts by ID first to have deterministic starting points
                    parts_sorted_by_id = sorted(parts, key=lambda x: x["id"])

                    for p in parts_sorted_by_id:
                        if p["id"] not in visited:
                            # Start BFS for this component
                            queue = [p]
                            visited.add(p["id"])
                            while queue:
                                curr = queue.pop(0)
                                ordered_parts.append(curr)
                                # Add unvisited neighbors
                                # Sort neighbors to be deterministic
                                neighbors = sorted(adj.get(curr["id"], []))
                                for n_id in neighbors:
                                    if n_id not in visited:
                                        # Find the participant object
                                        n_obj = next(
                                            (x for x in parts if x["id"] == n_id), None
                                        )
                                        if n_obj:
                                            visited.add(n_id)
                                            queue.append(n_obj)

                    # 3. Layout: Zig-Zag Vertical Positioning
                    # We have 3 tiers: -0.2, 0, +0.2 relative to y_val
                    # This utilizes the bar height (0.8) effectively
                    y_offsets = [0.2, 0, -0.2]

                    for p_idx, p in enumerate(ordered_parts):
                        # Horizontal: Even distribution
                        fraction = (p_idx + 1) / (num_parts + 1)
                        p_x = start_ts + pd.to_timedelta(dur_ms * fraction, unit="ms")

                        # Vertical: Zig-zag based on reordered index
                        y_offset = y_offsets[p_idx % len(y_offsets)]
                        p_y = y_val + y_offset

                        color, marker = self._get_participant_style(p["id"], p["type"])

                        part_xs.append(p_x)
                        part_ys.append(p_y)
                        part_colors.append(color)
                        part_symbols.append(marker)
                        hover_content = (
                            f"ID: {p['id']}<br>"
                            f"Name: {p['name']}<br>"
                            f"Type: {p['type']}<br>"
                            f"Role: {p['role']}<br>"
                            f"Attributes:<br>{p['attributes']}<br>"
                            f"Actions:<br>{p['actions']}"
                        )
                        part_hovers.append(hover_content)

                        local_p_coords[p["id"]] = (p_x, p_y)

                # --- Relations ---
                rels = r.get("Relations", [])
                for rel in rels:
                    src_id = rel.get("src")
                    dst_id = rel.get("dst")
                    rel_name = rel.get("name", "Relation")

                    if src_id in local_p_coords and dst_id in local_p_coords:
                        sx, sy = local_p_coords[src_id]
                        dx, dy = local_p_coords[dst_id]

                        r_color, r_dash = self._get_relation_style(rel_name)
                        key = (r_color, r_dash, rel_name)

                        if key not in relation_segments:
                            relation_segments[key] = {"x": [], "y": []}

                        # Add segment with None separator
                        relation_segments[key]["x"].extend([sx, dx, None])
                        relation_segments[key]["y"].extend([sy, dy, None])

            # Draw Episode Bars
            # Use fixed height 0.8 as defined in previous logic
            bar_height = 0.8

            fig.add_trace(
                go.Bar(
                    x=x_durs,
                    y=y_pos,
                    base=x_starts,
                    orientation="h",
                    name=f"Episodes ({sid})",
                    marker=dict(
                        color="#e6f5c9", line=dict(color="black", width=1), opacity=0.9
                    ),
                    hovertext=hovers,
                    text=None,
                    legendgroup=sid,
                    showlegend=False,
                    width=bar_height,
                )
            )

            # Draw Relations (BEFORE Participants so lines are below dots)
            for (r_color, r_dash, r_name), segs in relation_segments.items():
                fig.add_trace(
                    go.Scatter(
                        x=segs["x"],
                        y=segs["y"],
                        mode="lines",
                        line=dict(
                            color=r_color, width=adaptive_line_width, dash=r_dash
                        ),
                        name=r_name,
                        legendgroup="Relations",
                        showlegend=False,  # We will add a manual legend entry later
                        hoverinfo="name",
                    )
                )

            # Draw Participant Markers
            if part_xs:
                fig.add_trace(
                    go.Scatter(
                        x=part_xs,
                        y=part_ys,
                        mode="markers",
                        marker=dict(
                            color=part_colors,
                            symbol=part_symbols,
                            size=adaptive_marker_size,
                            line=dict(
                                color="black", width=max(0.5, adaptive_line_width * 0.5)
                            ),
                        ),
                        hovertext=part_hovers,
                        hoverinfo="text",
                        name=f"Participants ({sid})",
                        legendgroup=sid,
                        showlegend=False,  # To avoid clutter, rely on hover
                    )
                )

            for j, lbl in enumerate(texts):
                start_ts = x_starts[j]
                dur_ms = x_durs[j]
                end_ts = start_ts + pd.to_timedelta(dur_ms, unit="ms")
                mid_x = start_ts + pd.to_timedelta(dur_ms / 2.0, unit="ms")
                total_span_ms = max((max_time - min_time).total_seconds() * 1000, 1)
                bar_frac = min(max(dur_ms / total_span_ms, 0.0), 1.0)
                max_chars = max(10, int(70 * bar_frac))
                words = str(lbl).split(" ")
                lines = []
                buf = ""
                for w in words:
                    add = (buf + (" " if buf else "") + w).strip()
                    if len(add) <= max_chars:
                        buf = add
                    else:
                        if buf:
                            lines.append(buf)
                            buf = w
                        else:
                            lines.append(w[:max_chars])
                            rem = w[max_chars:]
                            while rem:
                                lines.append(rem[:max_chars])
                                rem = rem[max_chars:]
                if buf:
                    lines.append(buf)
                wrapped = "<br>".join(lines)
                top_y = y_pos[j] + (0.8 / 2.0)
                top_margin = 0.06
                line_h_base = 0.24
                lines_count = max(1, len(lines))
                block_h = line_h_base * lines_count
                y_bottom = top_y + top_margin
                safe_gap = 0.06
                min_h = 0.10
                next_bottom = None

                # Retrieve pre-assigned tiers and ID
                ep_id = local_eps[j]["ID"]
                start_label_y = tier_map.get((ep_id, "start"), 0.1)
                end_label_y = tier_map.get((ep_id, "end"), 0.1)

                start_label = (
                    pd.Timestamp(start_ts).strftime(time_label_fmt)
                    if isinstance(start_ts, (pd.Timestamp,))
                    else str(start_ts)
                )
                end_label = (
                    pd.Timestamp(end_ts).strftime(time_label_fmt)
                    if isinstance(end_ts, (pd.Timestamp,))
                    else str(end_ts)
                )

                # --- Start Time Line & Label ---
                fig.add_shape(
                    type="line",
                    x0=start_ts,
                    x1=start_ts,
                    y0=start_label_y,
                    y1=y_pos[j],
                    xref="x",
                    yref="y",
                    line=dict(color="#e6f5c9", width=1, dash="dash"),
                )
                fig.add_annotation(
                    x=start_ts,
                    y=start_label_y,
                    text="●",
                    showarrow=False,
                    align="center",
                    yanchor="middle",
                    font=dict(size=7, color="#e6f5c9"),
                )
                fig.add_annotation(
                    x=start_ts,
                    y=start_label_y,
                    text=start_label,
                    showarrow=False,
                    align="center",
                    yanchor="top",
                    font=dict(size=9, color="#222222"),
                )

                # --- End Time Line & Label ---
                fig.add_shape(
                    type="line",
                    x0=end_ts,
                    x1=end_ts,
                    y0=end_label_y,
                    y1=y_pos[j],
                    xref="x",
                    yref="y",
                    line=dict(color="#e6f5c9", width=1, dash="dash"),
                )
                fig.add_annotation(
                    x=end_ts,
                    y=end_label_y,
                    text="●",
                    showarrow=False,
                    align="center",
                    yanchor="middle",
                    font=dict(size=7, color="#e6f5c9"),
                )
                fig.add_annotation(
                    x=end_ts,
                    y=end_label_y,
                    text=end_label,
                    showarrow=False,
                    align="center",
                    yanchor="top",
                    font=dict(size=9, color="#222222"),
                )

                if j + 1 < len(y_pos):
                    next_bottom = y_pos[j + 1] - (0.8 / 2.0)
                    nearest_upper = None
                    for uy in episode_y_positions_global:
                        if uy > y_pos[j]:
                            if nearest_upper is None or uy < nearest_upper:
                                nearest_upper = uy
                upper_bar_bottom = None
                if nearest_upper is not None:
                    upper_bar_bottom = nearest_upper - (0.8 / 2.0)
                limits = []
                if next_bottom is not None:
                    limits.append(next_bottom - safe_gap)
                if upper_bar_bottom is not None:
                    limits.append(upper_bar_bottom - safe_gap)
                    id_line_h_base = 0.24
                    upper_id_top = upper_bar_bottom - safe_gap
                    upper_id_bottom = upper_id_top - id_line_h_base
                    limits.append(upper_id_bottom - safe_gap)
                font_size = 11
                if limits:
                    limit_top = min(limits)
                    avail = limit_top - y_bottom
                    if avail <= 0:
                        y_bottom = max(top_y + 0.02, limit_top - block_h)
                        avail = limit_top - y_bottom
                    if avail < block_h:
                        line_h = max(min_h, avail / lines_count)
                        block_h = line_h * lines_count
                        if block_h - avail > 1e-9 and line_h <= min_h + 1e-9:
                            max_lines = int(avail / min_h)
                            if max_lines <= 0:
                                max_lines = 1
                            if max_lines < lines_count:
                                if max_lines == 1:
                                    lines = [lines[0] if lines else ""]
                                else:
                                    lines = lines[: max_lines - 1] + ["..."]
                                lines_count = len(lines)
                                wrapped = "<br>".join(lines)
                                block_h = line_h * lines_count
                        font_size = max(
                            9,
                            int(
                                round(
                                    11
                                    * (
                                        block_h
                                        / max(1e-9, line_h_base * max(1, lines_count))
                                    )
                                )
                            ),
                        )
                fig.add_annotation(
                    x=mid_x,
                    y=y_bottom,
                    text=wrapped,
                    showarrow=False,
                    align="center",
                    yanchor="bottom",
                    font=dict(size=font_size, color="#222222"),
                )
                bottom_y = y_pos[j] - (0.8 / 2.0) - 0.06
                fig.add_annotation(
                    x=mid_x,
                    y=bottom_y,
                    text=f"Episode: {local_eps[j]['ID']}",
                    showarrow=False,
                    align="center",
                    yanchor="top",
                    font=dict(size=11, color="#333333"),
                )

        # --- 3. Configure Layout ---
        chart_title = cascade_data["title"]["value"]
        gran_levels_clean = [g for g in gran_levels if g is not None]
        order_map = {"Y": 0, "YM": 1, "YMD": 2, "YMDH": 3, "YMDHM": 4, "YMDHMS": 5}
        fmt_code = (
            max(gran_levels_clean, key=lambda c: order_map.get(c, 0))
            if gran_levels_clean
            else "YMDHM"
        )
        fmt_map = {
            "Y": "%Y",
            "YM": "%Y-%m",
            "YMD": "%Y-%m-%d",
            "YMDH": "%Y-%m-%d %H",
            "YMDHM": "%Y-%m-%d %H:%M",
            "YMDHMS": "%Y-%m-%d %H:%M:%S",
        }
        tickformat_str = fmt_map.get(fmt_code, "%Y-%m-%d %H:%M")

        # --- Add Legend for Participants ---
        unique_participants = {}
        for row in episode_rows:
            parts = row.get("Participants", [])
            for p in parts:
                p_id = p["id"]
                if p_id not in unique_participants:
                    unique_participants[p_id] = p

        sorted_parts = sorted(
            unique_participants.values(), key=lambda x: (x["type"], x["name"])
        )

        for p in sorted_parts:
            p_id = p["id"]
            if p_id in self.participant_style_map:
                color, marker = self.participant_style_map[p_id]
                fig.add_trace(
                    go.Scatter(
                        x=[None],
                        y=[None],
                        mode="markers",
                        marker=dict(
                            size=5,
                            color=color,
                            symbol=marker,
                            line=dict(color="black", width=0.5),
                        ),
                        name=f"{p['name']} ({p['type']})",
                        legendgroup="Participants",
                        legendrank=1000,
                        showlegend=True,
                    )
                )

        # --- Relations Legend ---
        if self.relation_style_map:
            # Add a header for relations (using a dummy empty trace with text or just separator)
            # Plotly legend doesn't support headers natively, but we can add a trace with name "--- Relations ---"
            fig.add_trace(
                go.Scatter(
                    x=[None],
                    y=[None],
                    mode="lines",
                    line=dict(width=0),
                    name="--- Relations ---",
                    legendgroup="Relations",
                    showlegend=True,
                    legendrank=2000,
                )
            )

            for rel_name, (r_color, r_dash) in self.relation_style_map.items():
                fig.add_trace(
                    go.Scatter(
                        x=[None],
                        y=[None],
                        mode="lines",
                        line=dict(color=r_color, width=1.5, dash=r_dash),
                        name=rel_name,
                        legendgroup="Relations",
                        legendrank=2001,
                        showlegend=True,
                    )
                )

        fig.update_layout(
            title=chart_title,
            dragmode="pan",
            xaxis=dict(
                type="date",
                range=range_x_initial,
                rangeslider=dict(visible=False),
                title="Time",
                tickformat=tickformat_str,
                hoverformat=tickformat_str,
            ),
            yaxis=dict(
                title="Episodes (Staggered)",
                tickmode="array",
                tickvals=[y_stage],
                ticktext=["STAGES"],
                showgrid=True,
                zeroline=False,
                fixedrange=False,
                range=[
                    -0.12,
                    (
                        max(episode_y_positions_global)
                        if episode_y_positions_global
                        else y_stage
                    )
                    + 0.8,
                ],
            ),
            height=plot_height,
            barmode="overlay",
            hovermode="closest",
            plot_bgcolor="white",
            margin=dict(l=50, r=50, t=80, b=90),
            showlegend=True,
            legend=dict(
                title="Participants",
                orientation="v",
                yanchor="top",
                y=1,
                xanchor="left",
                x=1.02,
            ),
        )

        # --- 4. Save Output ---
        if output_path:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            if output_path.endswith(".html"):
                html = fig.to_html(
                    full_html=True,
                    include_plotlyjs="cdn",
                    config={
                        "scrollZoom": False,
                        "doubleClick": "reset",
                        "modeBarButtonsToRemove": [
                            "zoom2d",
                            "zoomIn2d",
                            "zoomOut2d",
                            "autoScale2d",
                            "resetScale2d",
                            "lasso2d",
                            "select2d",
                        ],
                    },
                )
                dataset_min_ms = int(pd.Timestamp(min_time).value // 1_000_000)
                dataset_max_ms = int(
                    pd.Timestamp(max_time + end_buffer).value // 1_000_000
                )
                window_ms = int(window_sec * 1000)
                min_window_ms = int(slider_min_sec * 1000)
                max_window_ms = int((dataset_max_ms - dataset_min_ms) * 1.5)
                html += f"""
<div style="margin-top:12px;padding:8px 0;border-top:1px solid #eee;">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
    <label style="font-size:12px;color:#555;">紧凑度:</label>
    <input type="range" id="compactness-slider" min="0" max="1000" step="1" value="0" style="flex:1;">
    <span id="compactness-label" style="font-size:12px;color:#555;"></span>
  </div>
  <input type="range" id="time-window-slider" min="0" max="1000" step="1" value="0" style="width:100%;">
  <div id="time-window-label" style="font-size:12px;color:#555;text-align:center;margin-top:4px;"></div>
</div>
<script>
var gd = document.querySelectorAll('.plotly-graph-div')[0];
var minMs = {dataset_min_ms};
var maxMs = {dataset_max_ms};
var winMs = {window_ms};
var minWindowMs = {min_window_ms};
var maxWindowMs = {max_window_ms};
var timeFormatCode = "{fmt_code}";
var slider = document.getElementById('time-window-slider');
var label = document.getElementById('time-window-label');
var compact = document.getElementById('compactness-slider');
var compactLabel = document.getElementById('compactness-label');
function z2(n) {{ return (n<10?('0'+n):String(n)); }}
function fmt(ms) {{
  var d = new Date(ms);
  var Y = d.getUTCFullYear();
  var M = z2(d.getUTCMonth()+1);
  var D = z2(d.getUTCDate());
  var h = z2(d.getUTCHours());
  var m = z2(d.getUTCMinutes());
  var s = z2(d.getUTCSeconds());
  if (timeFormatCode === 'Y') return String(Y);
  if (timeFormatCode === 'YM') return Y + '-' + M;
  if (timeFormatCode === 'YMD') return Y + '-' + M + '-' + D;
  if (timeFormatCode === 'YMDH') return Y + '-' + M + '-' + D + ' ' + h;
  if (timeFormatCode === 'YMDHM') return Y + '-' + M + '-' + D + ' ' + h + ':' + m;
  return Y + '-' + M + '-' + D + ' ' + h + ':' + m + ':' + s;
}}
function fmtDuration(ms) {{
  var h = ms / 3600000.0;
  if (h >= 1) return h.toFixed(1) + 'h';
  var m = ms / 60000.0;
  if (m >= 1) return m.toFixed(0) + 'm';
  var s = ms / 1000.0;
  return s.toFixed(0) + 's';
}}
function updateCompactLabel() {{
  var frac = (winMs - minWindowMs) / Math.max(1, (maxWindowMs - minWindowMs));
  compactLabel.textContent = (Math.round(frac * 100)) + '% / ' + fmtDuration(winMs);
}}
function setRangeFromSlider() {{
  var frac = parseFloat(slider.value) / 1000.0;
  var dsSpan = maxMs - minMs;
  var overflow = Math.max(0, winMs - dsSpan);
  var startMin = minMs - overflow;
  var moveSpan = dsSpan + overflow;
  if (moveSpan < 1) moveSpan = 1;
  var startMs = Math.round(startMin + frac * moveSpan);
  var endMs = startMs + winMs;
  var r0 = new Date(startMs).toISOString();
  var r1 = new Date(endMs).toISOString();
  Plotly.relayout(gd, {{'xaxis.range': [r0, r1]}});
  label.textContent = fmt(startMs) + '  →  ' + fmt(endMs) + ' (' + fmtDuration(winMs) + ')';
}}
slider.addEventListener('input', setRangeFromSlider);
compact.addEventListener('input', function() {{
  var cfrac = parseFloat(compact.value) / 1000.0;
  winMs = Math.round(minWindowMs + cfrac * (maxWindowMs - minWindowMs));
  var r = gd.layout.xaxis && gd.layout.xaxis.range ? gd.layout.xaxis.range : null;
  var currentStart = r ? new Date(r[0]).getTime() : minMs;
  var dsSpan = maxMs - minMs;
  var overflow = Math.max(0, winMs - dsSpan);
  var startMin = minMs - overflow;
  var moveSpan = dsSpan + overflow;
  if (moveSpan < 1) moveSpan = 1;
  if (currentStart < startMin) currentStart = startMin;
  var startMax = startMin + moveSpan;
  if (currentStart > startMax) currentStart = startMax;
  var r0 = new Date(currentStart).toISOString();
  var r1 = new Date(currentStart + winMs).toISOString();
  Plotly.relayout(gd, {{'xaxis.range': [r0, r1]}});
  var frac = (currentStart - startMin) / moveSpan;
  var v = Math.max(0, Math.min(1000, Math.round(frac * 1000)));
  slider.value = String(v);
  label.textContent = fmt(currentStart) + '  →  ' + fmt(currentStart + winMs) + ' (' + fmtDuration(winMs) + ')';
  updateCompactLabel();
}});
// initialize compact slider position from current winMs
(function initControls() {{
  var fracWin = (winMs - minWindowMs) / Math.max(1, (maxWindowMs - minWindowMs));
  compact.value = String(Math.max(0, Math.min(1000, Math.round(fracWin * 1000))));
  updateCompactLabel();
}})();
gd.on('plotly_relayout', function(e) {{
  var r = gd.layout.xaxis && gd.layout.xaxis.range ? gd.layout.xaxis.range : null;
  if (!r) return;
  var r0ms = new Date(r[0]).getTime();
  var dsSpan = maxMs - minMs;
  var overflow = Math.max(0, winMs - dsSpan);
  var startMin = minMs - overflow;
  var moveSpan = dsSpan + overflow;
  if (moveSpan < 1) moveSpan = 1;
  var frac = (r0ms - startMin) / moveSpan;
  if (isFinite(frac)) {{
    var v = Math.max(0, Math.min(1000, Math.round(frac * 1000)));
    slider.value = String(v);
    var endMs = r0ms + winMs;
    label.textContent = fmt(r0ms) + '  →  ' + fmt(endMs) + ' (' + fmtDuration(winMs) + ')';
  }}
}});
</script>
"""
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(html)
            elif output_path.endswith(".png"):
                html_path = output_path.replace(".png", ".html")
                fig.write_html(html_path)
                print(f"Interactive HTML saved to {html_path}")
                try:
                    fig.write_image(output_path)
                except Exception as e:
                    print(f"Could not save static image: {e}")
            else:
                fig.write_html(output_path + ".html")

        return fig
