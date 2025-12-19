import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.patches as patches
from matplotlib.lines import Line2D
from datetime import datetime
import pandas as pd
from textwrap import wrap


class EventCascadeVisualizer:
    def __init__(self):
        # Distinct colors for participants (Tab20 hex codes)
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
        # Distinct markers
        self.markers = ["o", "s", "^", "D", "v", "<", ">", "p", "*", "h", "X", "d"]
        self.participant_style_map = {}
        self.participant_info_map = {}

        # New: Type-based coloring
        self.type_color_map = {}
        self.type_participant_count = {}

    def _parse_time(self, time_val):
        """Helper to parse time strings. Returns None if unknown or invalid."""
        if not time_val or not isinstance(time_val, dict):
            return None
        val = time_val.get("value")
        if not val or not isinstance(val, str) or val.lower() == "unknown":
            return None
        try:
            return pd.to_datetime(val)
        except:
            return None

    def _register_participant(self, p_id, name, p_type="Participant"):
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

        # Always update info to ensure we have the latest (or at least some)
        if p_id not in self.participant_info_map:
            self.participant_info_map[p_id] = {"name": name, "type": p_type}

        return self.participant_style_map[p_id]

    def plot_cascade(self, cascade_data, output_path=None):
        """
        Generates a matplotlib visualization of the EventCascade.
        Handles both real timestamps and logical ordering (if times are unknown).
        """
        # Set a nice font
        try:
            plt.rcParams["font.family"] = "sans-serif"
            # Prioritize fonts that look good on macOS/Windows/Linux
            plt.rcParams["font.sans-serif"] = [
                "Arial",
                "Helvetica Neue",
                "Helvetica",
                "DejaVu Sans",
                "Bitstream Vera Sans",
                "sans-serif",
            ]
        except Exception:
            pass

        # --- 1. Data Parsing & Flattening ---

        # We'll build a list of "Drawable Items": Event, Stages, Episodes
        # And a set of "Participants" and "Relations"

        drawables = []

        # A. Event
        evt_title = cascade_data["title"]["value"]
        evt_start = self._parse_time(cascade_data["start_time"])
        evt_end = self._parse_time(cascade_data["end_time"])

        # We need to determine if we are using Real Time or Logical Time
        # Heuristic: If > 50% of items have times, use Real Time, else Logical.
        # For now, let's collect all potential timestamps to check.
        time_points = []
        if evt_start:
            time_points.append(evt_start)
        if evt_end:
            time_points.append(evt_end)

        stages = cascade_data["stages"]
        stage_objs = []

        for s_idx, stage in enumerate(stages):
            s_title = stage["name"]["value"]
            s_id = stage["stage_id"]
            s_start = self._parse_time(stage["start_time"])
            s_end = self._parse_time(stage["end_time"])
            if s_start:
                time_points.append(s_start)
            if s_end:
                time_points.append(s_end)

            episodes = stage["episodes"]
            ep_objs = []

            for e_idx, ep in enumerate(episodes):
                e_title = ep["name"]["value"]
                e_id = ep["episode_id"]
                e_start = self._parse_time(ep["start_time"])
                e_end = self._parse_time(ep["end_time"])
                if e_start:
                    time_points.append(e_start)
                if e_end:
                    time_points.append(e_end)

                # Participants
                # In structure.py: participants is a List[Participant] dicts
                # We need participant_id and name
                parts = []
                raw_parts = ep["participants"]
                for p in raw_parts:
                    p_id = p["participant_id"]
                    p_name = p["name"]["value"]
                    # Try to find role or type
                    # Priority: participant_type > role > type
                    # Note: We still use .get() here for optional fallback logic if strictly required,
                    # but user asked to be explicit.
                    # However, these fields might genuinely be optional/variable in some schemas.
                    # Assuming strict schema: participant_type SHOULD exist.
                    p_type = p["participant_type"]["value"]

                    if p_id:
                        parts.append({"id": p_id, "name": p_name, "type": p_type})

                # Relations
                # In structure.py: participant_relations is List[ParticipantRelation]
                rels = []
                raw_rels = ep["participant_relations"]
                for r in raw_rels:
                    src = r["from_participant_id"]
                    dst = r["to_participant_id"]
                    rel_name = r["relation_name"]["value"]
                    if src and dst:
                        rels.append({"src": src, "dst": dst, "name": rel_name})

                ep_objs.append(
                    {
                        "title": e_title,
                        "id": e_id,
                        "stage_id": s_id,
                        "start": e_start,
                        "end": e_end,
                        "participants": parts,
                        "relations": rels,
                        "type": "Episode",
                        "s_idx": s_idx,
                        "e_idx": e_idx,
                    }
                )

            stage_objs.append(
                {
                    "title": s_title,
                    "id": s_id,
                    "start": s_start,
                    "end": s_end,
                    "episodes": ep_objs,
                    "type": "Stage",
                    "s_idx": s_idx,
                }
            )

        # --- 2. Coordinate Assignment (Logical vs Real) ---

        use_real_time = len(time_points) > 0  # Use real time if ANY valid time exists?
        # Better: if we have enough structure. Often "unknown".
        # If total time span is 0 or undefined, switch to logical.

        if use_real_time:
            min_time = min(time_points)
            max_time = max(time_points)
            if min_time == max_time:
                # Add a default span if single point
                max_time = min_time + pd.Timedelta(hours=1)

            # Normalize times to float (hours since start) for plotting ease
            def to_coord(t):
                if t is None:
                    return None
                return (t - min_time).total_seconds() / 3600.0

            x_label = "Time (Hours from Start)"
        else:
            # Logical Layout
            # Stage i starts at i * 100
            # Episode j starts at i*100 + j*10
            def to_coord(t):
                return None  # Unused

            x_label = "Event Progression (Logical Steps)"
            min_time = 0

        # Assign Coordinates
        # Y-axis:
        # Stages: Y=0 (Bottom)
        # Episodes: Y>0, staggered upwards based on time/index.

        # We'll use a logical X-axis that maps to time strings.
        # This solves the "Unknown" time issue and the mix of real/logical.
        # We will collect all unique start/end time strings and sort them if possible,
        # or just use the logical flow sequence.

        # Since the hierarchy is strict (Stage -> Episode), we can sequence them linearly.
        # X-axis will be 0..N

        # Flatten for X-assignment
        # Sequence: Stage 1 Start -> Ep 1 Start -> Ep 1 End -> ... -> Stage 1 End

        # Actually, simpler:
        # Just assign X coordinates sequentially to Episodes.
        # Stage X covers min(Ep X) to max(Ep X).

        final_items = []

        # Configuration
        EPISODE_WIDTH = 4
        EPISODE_GAP = 2
        STAGE_GAP = 4

        current_x = 0

        # We need to collect tick labels
        x_ticks = []
        x_tick_labels = []

        def add_tick(x, label):
            # Only add if we haven't added a tick nearby or same label?
            # For now, just add.
            x_ticks.append(x)
            # If label is None/Empty, use "Unknown"
            if not label:
                label = "Unknown"
            # Format datetime if it is one
            if isinstance(label, pd.Timestamp):
                label = label.strftime("%Y-%m-%d")
            x_tick_labels.append(str(label))

        y_base_stage = 0

        # Track overall Y max to adjust plot limits
        max_y = 1

        for stage in stage_objs:
            # Stage Start X (will be updated)
            stage_start_x = current_x

            # Start Tick for Stage
            s_start_val = stage.get("start")
            s_end_val = stage.get("end")

            if use_real_time:
                # Try to use real coordinates
                sx = to_coord(s_start_val)
                ex = to_coord(s_end_val)
                if sx is not None:
                    stage_start_x = sx
                if ex is not None:
                    stage_end_x = ex
                else:
                    # Fallback if end is missing?
                    # We will update stage_end_x based on episodes if needed
                    stage_end_x = stage_start_x + (
                        EPISODE_WIDTH if not stage.get("episodes") else 0
                    )
            else:
                # Logical
                pass  # stage_start_x is already current_x

            episodes = stage.get("episodes", [])

            # If no episodes, stage has fixed width (Logical only or fallback)
            if not episodes:
                if not use_real_time:
                    current_x += EPISODE_WIDTH
                    stage_end_x = current_x

                add_tick(stage_start_x, s_start_val)
                add_tick(stage_end_x, s_end_val)
            else:
                # Episodes
                # Stagger logic:
                # Y = 1 + e_idx (within stage)

                min_ep_x = None
                max_ep_x = None

                for i, ep in enumerate(episodes):
                    if use_real_time:
                        esx = to_coord(ep.get("start"))
                        eex = to_coord(ep.get("end"))

                        # Fallback for unknown episode times in Real Time mode?
                        # If unknown, maybe place relative to stage start?
                        if esx is None:
                            esx = stage_start_x + (i * 0.5)  # Arbitrary small step?
                        if eex is None:
                            eex = esx + 1.0  # Default 1 hour?

                        ep_start_x = esx
                        ep_end_x = eex
                        width = max(ep_end_x - ep_start_x, 0.1)  # Ensure min width
                    else:
                        ep_start_x = current_x
                        width = EPISODE_WIDTH
                        ep_end_x = ep_start_x + width

                    # Y Level
                    ep_y = 1 + i * 1.5  # 1.5 spacing

                    ep["x"] = ep_start_x
                    ep["width"] = width
                    ep["y"] = ep_y
                    ep["type"] = "Episode"

                    final_items.append(ep)

                    # Ticks for Episode
                    add_tick(ep_start_x, ep.get("start"))
                    add_tick(ep_end_x, ep.get("end"))

                    max_y = max(max_y, ep_y)

                    # Update bounds
                    if min_ep_x is None or ep_start_x < min_ep_x:
                        min_ep_x = ep_start_x
                    if max_ep_x is None or ep_end_x > max_ep_x:
                        max_ep_x = ep_end_x

                    if not use_real_time:
                        current_x += width + EPISODE_GAP

                # Update Stage Width to cover episodes
                if use_real_time:
                    # If Stage has its own times, prefer them?
                    # Usually Stage contains episodes.
                    # Let's union them.
                    real_s_start = to_coord(s_start_val)
                    real_s_end = to_coord(s_end_val)

                    final_s_start = (
                        real_s_start if real_s_start is not None else min_ep_x
                    )
                    final_s_end = real_s_end if real_s_end is not None else max_ep_x

                    if final_s_start is not None and final_s_end is not None:
                        stage_start_x = final_s_start
                        stage_end_x = final_s_end
                    elif min_ep_x is not None:
                        stage_start_x = min_ep_x
                        stage_end_x = max_ep_x
                    else:
                        # Fallback
                        stage_end_x = stage_start_x + EPISODE_WIDTH
                else:
                    # Stage covers from first Ep start to last Ep end
                    # (minus the last gap)
                    stage_end_x = current_x - EPISODE_GAP

            stage["x"] = stage_start_x
            stage["width"] = max(stage_end_x - stage_start_x, 0.1)
            stage["y"] = y_base_stage
            stage["type"] = "Stage"

            final_items.append(stage)

            # Update global current_x for plot limits
            if use_real_time:
                current_x = max(current_x, stage_end_x)
            else:
                current_x += STAGE_GAP

        # --- 3. Plotting ---

        fig, ax = plt.subplots(figsize=(20, 12))  # Larger figure

        # Calculate character wrapping factor
        # Total X range visible
        x_min_limit = -2
        x_max_limit = current_x + 2
        total_x_range = x_max_limit - x_min_limit

        # Physical width in inches (approximate, excluding margins)
        # subplot takes most of the 20 inches, say 18 inches
        plot_width_inches = 18.0

        inches_per_unit = plot_width_inches / max(total_x_range, 1.0)

        # Font size 9 (points) -> inches
        font_size_points = 9
        font_size_inches = font_size_points / 72.0
        # Average character width ratio (approx 0.6 of height)
        avg_char_width_inches = font_size_inches * 0.6

        # Characters per unit of data width
        chars_per_unit = inches_per_unit / avg_char_width_inches

        # Constants
        STAGE_HEIGHT = 0.6
        EPISODE_HEIGHT = 1.0

        for item in final_items:
            # Colors
            if item["type"] == "Stage":
                color = "#ADD8E6"  # Light Blue
                edgecolor = "black"
                alpha = 0.8
                height = STAGE_HEIGHT
                y_pos = item["y"]

                # Draw Stage Bar
                rect = patches.Rectangle(
                    (item["x"], y_pos),
                    item["width"],
                    height,
                    linewidth=1,
                    edgecolor=edgecolor,
                    facecolor=color,
                    alpha=alpha,
                )
                ax.add_patch(rect)

                # Label Stage (Inside or below?)
                # User said: "Stage at bottom... long rectangle"
                ax.text(
                    item["x"] + item["width"] / 2,
                    y_pos + height / 2,
                    item["title"],
                    ha="center",
                    va="center",
                    fontsize=10,
                    fontweight="bold",
                    color="black",
                )

                # Stage ID (Bottom Center)
                ax.text(
                    item["x"] + item["width"] / 2,
                    y_pos + 0.05,
                    f"Stage: {item.get('id', '')}",
                    ha="center",
                    va="bottom",
                    fontsize=9,
                    fontweight="bold",
                    color="black",
                    alpha=0.9,
                )

                # Vertical Dashed Lines for Stage (Start and End)
                # User request: "stage 的框前后也应该和x轴有一个虚线连接"
                # Start Line
                ax.plot(
                    [item["x"], item["x"]],
                    [y_pos, -1],
                    color="gray",
                    linestyle="--",
                    linewidth=0.8,
                    zorder=0,
                )
                # End Line
                ax.plot(
                    [item["x"] + item["width"], item["x"] + item["width"]],
                    [y_pos, -1],
                    color="gray",
                    linestyle="--",
                    linewidth=0.8,
                    zorder=0,
                )

            elif item["type"] == "Episode":
                color = "#e6f5c9"  # Light green
                edgecolor = "black"
                alpha = 0.9
                height = EPISODE_HEIGHT
                y_pos = item["y"]

                # Draw Episode Bar
                rect = patches.Rectangle(
                    (item["x"], y_pos),
                    item["width"],
                    height,
                    linewidth=1,
                    edgecolor=edgecolor,
                    facecolor=color,
                    alpha=alpha,
                    zorder=2,
                )
                ax.add_patch(rect)

                # Label Episode Name (Above box)
                # Dynamic wrap width based on physical size
                # Reduce by small margin to ensure it fits inside visual box
                wrap_width = max(5, int(item["width"] * chars_per_unit * 0.9))

                wrapped_title = "\n".join(wrap(item["title"], width=wrap_width))

                ax.text(
                    item["x"],
                    y_pos + height + 0.1,
                    wrapped_title,
                    ha="left",
                    va="bottom",
                    fontsize=9,
                    fontweight="bold",
                    color="black",
                    rotation=0,
                    wrap=True,
                )

                # Episode ID info (Bottom Center Inside Box)
                # User request: "在框的内部紧邻下边地方 写 框所属的 Stage ID episode ID" -> REVISED: "Episode: ID 部分只在episode 相关的框写"
                ep_id_str = f"Episode: {item.get('id', '')}"
                ax.text(
                    item["x"] + item["width"] / 2,
                    y_pos + 0.05,
                    ep_id_str,
                    ha="center",
                    va="bottom",
                    fontsize=9,
                    fontweight="bold",
                    color="#333333",
                    zorder=15,  # Above participants if they overlap?
                )

                # Vertical Dashed Lines to X-axis
                # User request: "episode框的前后都应该有一个虚线连接到x轴"
                # Start Line
                ax.plot(
                    [item["x"], item["x"]],
                    [y_pos, -1],  # Drop to -1 (the bottom limit of our plot)
                    color="gray",
                    linestyle="--",
                    linewidth=0.8,
                    zorder=0,
                )
                # End Line
                ax.plot(
                    [item["x"] + item["width"], item["x"] + item["width"]],
                    [y_pos, -1],
                    color="gray",
                    linestyle="--",
                    linewidth=0.8,
                    zorder=0,
                )

                # Participants (Inside Box)
                parts = item.get("participants", [])
                rels = item.get("relations", [])

                if parts:
                    # Group participants by type
                    type_groups = {}
                    for p in parts:
                        p_type = p.get("type", "Participant")
                        if p_type not in type_groups:
                            type_groups[p_type] = []
                        type_groups[p_type].append(p)

                    # Sort types to ensure consistent ordering (e.g., alphabetical)
                    sorted_types = sorted(type_groups.keys())
                    num_groups = len(sorted_types)

                    # Calculate vertical spacing
                    # We have 'height' available (e.g. 1.0).
                    # Use margins to avoid edge crowding.
                    margin_v = 0.2 * height  # 10% top, 10% bottom
                    available_h = height - 2 * margin_v

                    if num_groups > 0:
                        row_height = available_h / num_groups
                    else:
                        row_height = available_h

                    p_coords = {}

                    for g_idx, p_type in enumerate(sorted_types):
                        group_parts = type_groups[p_type]

                        # Y-coordinate for this row
                        # Start from bottom or top? Let's go bottom-up
                        row_cy = (
                            y_pos + margin_v + (g_idx * row_height) + (row_height / 2)
                        )

                        # Distribute horizontally in this row
                        cx_start = item["x"] + (item["width"] * 0.1)
                        row_width = item["width"] * 0.8

                        if len(group_parts) > 1:
                            cx_step = row_width / (len(group_parts) - 1)
                        else:
                            cx_step = 0  # Center it if only one
                            cx_start = item["x"] + (item["width"] / 2)

                        for i, p in enumerate(group_parts):
                            if len(group_parts) > 1:
                                px = cx_start + i * cx_step
                            else:
                                px = cx_start  # Centered

                            py = row_cy

                            # Register & Get Style
                            p_color, p_marker = self._register_participant(
                                p["id"], p["name"], p.get("type", "Participant")
                            )

                            # Draw Marker
                            ax.scatter(
                                [px],
                                [py],
                                color=p_color,
                                marker=p_marker,
                                s=100,
                                zorder=10,
                                edgecolor="white",
                            )

                            p_coords[p["id"]] = (px, py)

                    # Relations
                    for rel in rels:
                        src_id = rel["src"]
                        dst_id = rel["dst"]
                        if src_id in p_coords and dst_id in p_coords:
                            sx, sy = p_coords[src_id]
                            dx, dy = p_coords[dst_id]

                            # Draw line
                            ax.plot(
                                [sx, dx],
                                [sy, dy],
                                color="red",
                                alpha=0.6,
                                linestyle="-",
                                linewidth=1,
                                zorder=5,
                            )

        # Axis Formatting
        ax.set_ylim(-1, max_y + 2)
        ax.set_xlim(-2, current_x + 2)

        # Set X-ticks
        # Filter ticks to avoid overlapping?
        # For now, show all but rotate them
        ax.set_xticks(x_ticks)
        ax.set_xticklabels(x_tick_labels, rotation=45, ha="right", fontsize=8)

        ax.set_yticks([])  # Hide Y axis ticks

        # Hide spines
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_visible(False)

        # Legend
        handles = []
        labels = []
        for p_id, (color, marker) in self.participant_style_map.items():
            info = self.participant_info_map.get(
                p_id, {"name": p_id, "type": "Unknown"}
            )
            label_str = f"{info['name']} ({info['type']})"
            handle = Line2D(
                [0],
                [0],
                marker=marker,
                color="w",
                label=label_str,
                markerfacecolor=color,
                markersize=10,
            )
            handles.append(handle)
            labels.append(label_str)

        if handles:
            ax.legend(
                handles,
                labels,
                title="Participants",
                loc="upper left",
                bbox_to_anchor=(1, 1),
            )

        plt.title(f"Event Cascade: {evt_title}", fontsize=18, fontweight="bold", pad=20)
        plt.tight_layout()

        if output_path:
            plt.savefig(output_path)
            plt.close()
            return output_path
        else:
            return fig
