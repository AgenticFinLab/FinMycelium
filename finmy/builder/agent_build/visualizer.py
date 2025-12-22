"""
Event Cascade Visualizer
========================

This module provides the `EventCascadeVisualizer` class, which is responsible for rendering
visual representations of financial event cascades. It transforms hierarchical event data
(Event -> Stages -> Episodes) into a structured timeline visualization using Matplotlib.

Key Features:
- **Hierarchical Layout**: Displays Stages as the foundational layer with Episodes staggered above.
- **Time-Aware Rendering**: Supports both real-time (timestamp-based) and logical (sequence-based) layouts.
- **Participant Visualization**: Uses distinct markers and colors to represent different participant types.
- **Relation Mapping**: Visualizes relationships between participants within episodes using styled connection lines.
- **Rich Legend**: Automatically generates a legend for participant types and relation styles.

Usage:
    visualizer = EventCascadeVisualizer()
    visualizer.plot_cascade("path/to/event_cascade.json", "output_plot.png")
"""

import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.lines import Line2D
import platform
import pandas as pd
import json
from textwrap import wrap


class EventCascadeVisualizer:
    """
    Visualizer for EventCascade structures.

    This class handles the rendering of hierarchical event data (Event -> Stages -> Episodes)
    using Matplotlib. It supports:
    1.  Hierarchical Timeline: Stages at the bottom, Episodes staggered above.
    2.  Time Handling: Renders based on real timestamps if available, or logical steps if not.
    3.  Participant Visualization: Distinct markers and colors for different participant types.
    4.  Relation Mapping: Visualizes relationships between participants within episodes.
    """

    def __init__(self):
        """
        Initialize the visualizer with color palettes and style maps.

        Sets up:
        - colors: A list of distinct hex colors (Tab20) for differentiating types.
        - markers: A list of matplotlib markers for differentiating participants within a type.
        - mappings: Dictionaries to track assigned styles for consistency across the plot.
        """
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
        # Distinct markers to differentiate participants of the same type
        self.markers = ["o", "s", "^", "D", "v", "<", ">", "p", "*", "h", "X", "d"]

        # Maps participant_id -> (color, marker)
        self.participant_style_map = {}
        # Maps participant_id -> info dict (name, type)
        self.participant_info_map = {}

        # New: Type-based coloring
        # Maps participant_type -> assigned color
        self.type_color_map = {}
        # Tracks how many participants of a certain type have been seen (for marker rotation)
        self.type_participant_count = {}

        # New: Relation-based styling
        # Maps relation_name -> (color, linestyle)
        self.relation_style_map = {}
        # Predefined linestyles
        self.linestyles = ["-", "--", "-.", ":"]
        # Predefined relation colors (using a different palette or subset)
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

    def _parse_time(self, time_val):
        """
        Helper to parse time strings from the EventCascade JSON structure.

        Args:
            time_val (dict): A dictionary containing a 'value' key with the time string.

        Returns:
            pd.Timestamp or None: The parsed datetime object, or None if invalid/unknown.
        """
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
        """
        Registers a participant and assigns a consistent style (color + marker).

        Logic:
        1.  If participant ID is already known, return existing style.
        2.  If new, determine color based on `p_type`. All participants of same type share a color.
        3.  Determine marker based on count of participants within that type.

        Args:
            p_id (str): Unique participant ID.
            name (str): Participant name.
            p_type (str): Participant type/role (e.g., "Analyst", "Manager").

        Returns:
            tuple: (color, marker)
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

        # Always update info to ensure we have the latest (or at least some)
        if p_id not in self.participant_info_map:
            self.participant_info_map[p_id] = {"name": name, "type": p_type}

        return self.participant_style_map[p_id]

    def _get_relation_style(self, rel_name):
        """
        Assigns a consistent style (color + linestyle) to a relation type/name.

        Args:
            rel_name (str): The name/type of the relation.

        Returns:
            tuple: (color, linestyle)
        """
        if rel_name not in self.relation_style_map:
            idx = len(self.relation_style_map)
            color = self.relation_colors[idx % len(self.relation_colors)]
            linestyle = self.linestyles[idx % len(self.linestyles)]
            self.relation_style_map[rel_name] = (color, linestyle)

        return self.relation_style_map[rel_name]

    def plot_cascade(self, jsondata, output_path=None):
        """
        Generates a matplotlib visualization of the EventCascade.

        This method performs three main steps:
        1.  **Data Loading**: Reads the JSON file from the provided path.
        2.  **Data Flattening**: Parses the hierarchical JSON structure into a flat list of
            drawable objects (Stages, Episodes) and extracts relationships.
        3.  **Coordinate Assignment**: Calculates the X/Y coordinates for each object.
            -   Supports 'Real Time' mode (based on timestamps) and 'Logical' mode (sequential).
            -   Implements a 'Waterfall' layout where episodes are staggered vertically.
        4.  **Plotting**: Renders the objects using Matplotlib patches, lines, and text.

        Args:
            json_path (str): Path to the EventCascade JSON file.
            output_path (str, optional): Path to save the resulting image. If None, shows plot.
        """
        # --- 0. Load Data ---
        try:
            cascade_data = jsondata
        except Exception as e:
            print(f"Error processing JSON data: {e}")
            return

        # Set a nice font
        try:
            # Set basic parameters first
            plt.rcParams['axes.unicode_minus'] = False
            
            # Select fonts based on operating system
            import platform
            system = platform.system()
            
            if system == "Windows":
                # Windows system
                font_list = ["SimHei", "Microsoft YaHei", "Arial", "DejaVu Sans", "sans-serif"]
            elif system == "Darwin":
                # macOS system
                font_list = ["PingFang SC", "STHeiti", "Helvetica Neue", "Arial", "DejaVu Sans", "sans-serif"]
            else:
                # Linux or other systems
                font_list = ["WenQuanYi Zen Hei", "DejaVu Sans", "Arial", "sans-serif"]
            
            plt.rcParams["font.family"] = "sans-serif"
            plt.rcParams["font.sans-serif"] = font_list
            
        except Exception as e:
            print(f"Font configuration failed: {e}")
            # If the above configuration fails, fall back to the original settings
            plt.rcParams["font.family"] = "sans-serif"
            plt.rcParams["font.sans-serif"] = [
                "Arial",
                "Helvetica Neue",
                "Helvetica",
                "DejaVu Sans",
                "Bitstream Vera Sans",
                "sans-serif",
            ]

        # --- 1. Data Parsing & Flattening ---
        # The goal here is to traverse the nested structure (Event -> Stage -> Episode)
        # and extract all relevant information into flat lists for easier processing.
        # We also collect all timestamps to decide between Real Time and Logical rendering.

        drawables = []

        # A. Event Info
        evt_title = cascade_data["title"]["value"]
        evt_start = self._parse_time(cascade_data["start_time"])
        evt_end = self._parse_time(cascade_data["end_time"])

        # We need to determine if we are using Real Time or Logical Time
        # Heuristic: If we have valid timestamps, we prefer Real Time.
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
                # Extract participant info to build the legend and style map.
                # structure.py defines participants as a list of dictionaries.
                parts = []
                raw_parts = ep["participants"]
                for p in raw_parts:
                    p_id = p["participant_id"]
                    p_name = p["name"]["value"]
                    # Priority for type: participant_type > role > type
                    # We access fields directly as per user request (no .get() default masking).
                    p_type = p["participant_type"]["value"]

                    if p_id:
                        parts.append({"id": p_id, "name": p_name, "type": p_type})

                # Relations
                # Extract relationships to draw connecting lines between participants.
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

        # Strategy:
        # If timestamps are available (use_real_time), we map them to the X-axis (hours from start).
        # If not, we use a fixed-width logical layout where each stage/episode follows sequentially.

        # Use real time if ANY valid time exists
        use_real_time = len(time_points) > 0

        if use_real_time:
            # Calculate global time bounds
            min_time = min(time_points)
            max_time = max(time_points)
            if min_time == max_time:
                # Handle single-point edge case by adding a default 1-hour span
                max_time = min_time + pd.Timedelta(hours=1)

            # Helper to convert timestamp to X-coordinate (Hours)
            def to_coord(t):
                if t is None:
                    return None
                return (t - min_time).total_seconds() / 3600.0

            x_label = "Time (Hours from Start)"
        else:
            # Logical Layout: Sequential integer coordinates
            def to_coord(t):
                # Unused in logical mode
                return None

            x_label = "Event Progression (Logical Steps)"
            min_time = 0

        # Prepare for Coordinate Calculation
        # We iterate through stages and episodes to assign (x, y, width, height).
        # Layout Rules:
        # - Stages: Placed at Y=0.
        # - Episodes: Placed above stages (Y > 0).
        #   - Staggered vertically (Y level increases) to avoid overlap and show sequence clearly.
        #   - Box width depends on duration (Real Time) or fixed constant (Logical).

        final_items = []

        # Layout Constants
        # Logical width for episodes
        EPISODE_WIDTH = 4
        # Gap between episodes in logical mode
        EPISODE_GAP = 2
        # Gap between stages in logical mode
        STAGE_GAP = 4

        # Tracking cursor for logical layout
        current_x = 0

        # Ticks for X-axis
        x_ticks = []
        x_tick_labels = []

        def add_tick(x, label):
            """Adds an X-axis tick with a formatted label."""
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
            # 1. Determine Stage Start
            stage_start_x = current_x

            # Get raw time values for ticks
            s_start_val = stage.get("start")
            s_end_val = stage.get("end")

            if use_real_time:
                # Try to use real coordinates from stage metadata
                sx = to_coord(s_start_val)
                ex = to_coord(s_end_val)
                if sx is not None:
                    stage_start_x = sx
                if ex is not None:
                    stage_end_x = ex
                else:
                    # Fallback if end is missing: default width if no episodes
                    stage_end_x = stage_start_x + (
                        EPISODE_WIDTH if not stage.get("episodes") else 0
                    )
            else:
                # Logical mode: stage starts at current cursor
                pass

            episodes = stage.get("episodes", [])

            # If no episodes, stage has fixed width (Logical only or fallback)
            if not episodes:
                if not use_real_time:
                    current_x += EPISODE_WIDTH
                    stage_end_x = current_x

                add_tick(stage_start_x, s_start_val)
                add_tick(stage_end_x, s_end_val)
            else:
                # 2. Process Episodes
                # Stagger logic: Episodes are stacked vertically to show sequence.
                # Y = 1 + e_idx * 1.5 (base height + stagger step)

                min_ep_x = None
                max_ep_x = None

                for i, ep in enumerate(episodes):
                    if use_real_time:
                        esx = to_coord(ep.get("start"))
                        eex = to_coord(ep.get("end"))

                        # Fallback for unknown episode times in Real Time mode
                        # If unknown, place relative to stage start or previous episode
                        if esx is None:
                            esx = stage_start_x + (i * 0.5)
                        if eex is None:
                            # Default 1 hour duration
                            eex = esx + 1.0

                        ep_start_x = esx
                        ep_end_x = eex
                        # Ensure min width for visibility
                        width = max(ep_end_x - ep_start_x, 0.1)
                    else:
                        # Logical mode: Fixed width, sequential placement
                        ep_start_x = current_x
                        width = EPISODE_WIDTH
                        ep_end_x = ep_start_x + width

                    # Y Level Calculation (Staggered)
                    ep_y = 1 + i * 1.5

                    ep["x"] = ep_start_x
                    ep["width"] = width
                    ep["y"] = ep_y
                    ep["type"] = "Episode"

                    final_items.append(ep)

                    # Ticks for Episode
                    add_tick(ep_start_x, ep.get("start"))
                    add_tick(ep_end_x, ep.get("end"))

                    max_y = max(max_y, ep_y)

                    # Update bounds for stage containment
                    if min_ep_x is None or ep_start_x < min_ep_x:
                        min_ep_x = ep_start_x
                    if max_ep_x is None or ep_end_x > max_ep_x:
                        max_ep_x = ep_end_x

                    if not use_real_time:
                        current_x += width + EPISODE_GAP

                # 3. Update Stage Width to cover all episodes
                if use_real_time:
                    # Determine stage bounds based on real times or episode bounds
                    real_s_start = to_coord(s_start_val)
                    real_s_end = to_coord(s_end_val)

                    # Prefer real stage times if available, otherwise use episode bounds
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
                    # Logical mode: Stage covers from first Ep start to last Ep end
                    # (current_x includes the last gap, so we subtract it)
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
        # Initialize the figure and axis
        fig, ax = plt.subplots(figsize=(20, 12))

        # Dynamic Font Scaling & Text Wrapping Logic:
        # To ensure text fits inside boxes, we calculate the relationship between
        # data coordinates and physical inches.

        # Total X range visible in data units
        x_min_limit = -2
        x_max_limit = current_x + 2
        total_x_range = x_max_limit - x_min_limit

        # Physical width in inches (approximate, excluding margins)
        plot_width_inches = 18.0

        inches_per_unit = plot_width_inches / max(total_x_range, 1.0)

        # Font metrics (Points -> Inches)
        font_size_points = 12
        font_size_inches = font_size_points / 72.0
        # Average character width ratio (approx 0.6 of height)
        avg_char_width_inches = font_size_inches * 0.6

        # Result: How many characters fit in 1 unit of data width
        chars_per_unit = inches_per_unit / avg_char_width_inches

        # Height Constants
        STAGE_HEIGHT = 0.6
        EPISODE_HEIGHT = 1.0

        for item in final_items:
            # --- Render Stage ---
            if item["type"] == "Stage":
                # Light Blue
                color = "#ADD8E6"
                edgecolor = "black"
                alpha = 0.8
                height = STAGE_HEIGHT
                y_pos = item["y"]

                # Draw Stage Rectangle
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

                # Label Stage Name (Center)
                # Calculate wrap width dynamically based on box physical width
                # Adjust for font size difference (14 vs base 12)
                stage_chars_per_unit = chars_per_unit * (12.0 / 14.0)
                wrap_width = max(5, int(item["width"] * stage_chars_per_unit * 0.9))
                wrapped_title = "\n".join(wrap(item["title"], width=wrap_width))

                ax.text(
                    item["x"] + item["width"] / 2,
                    y_pos + height / 2,
                    wrapped_title,
                    ha="center",
                    va="center",
                    fontsize=14,
                    fontweight="bold",
                    color="black",
                )

                # Label Stage ID (Bottom Center)
                ax.text(
                    item["x"] + item["width"] / 2,
                    y_pos + 0.05,
                    f"Stage: {item.get('id', '')}",
                    ha="center",
                    va="bottom",
                    fontsize=12,
                    fontweight="bold",
                    color="black",
                    alpha=0.9,
                )

                # Visual Guides: Vertical Dashed Lines
                # Connect stage boundaries to the X-axis for time alignment
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

            # --- Render Episode ---
            elif item["type"] == "Episode":
                # Light green
                color = "#e6f5c9"
                edgecolor = "black"
                alpha = 0.9
                height = EPISODE_HEIGHT
                y_pos = item["y"]

                # Draw Episode Rectangle
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
                # Calculate wrap width dynamically based on box physical width
                wrap_width = max(5, int(item["width"] * chars_per_unit * 0.9))

                wrapped_title = "\n".join(wrap(item["title"], width=wrap_width))

                ax.text(
                    item["x"],
                    y_pos + height + 0.1,
                    wrapped_title,
                    ha="left",
                    va="bottom",
                    fontsize=12,
                    fontweight="bold",
                    color="black",
                    rotation=0,
                    wrap=True,
                )

                # Label Episode ID (Inside box, bottom)
                ep_id_str = f"Episode: {item.get('id', '')}"
                ax.text(
                    item["x"] + item["width"] / 2,
                    y_pos + 0.05,
                    ep_id_str,
                    ha="center",
                    va="bottom",
                    fontsize=12,
                    fontweight="bold",
                    color="#333333",
                    zorder=15,
                )

                # Visual Guides: Vertical Dashed Lines
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

                # --- Render Participants (Inside Box) ---
                parts = item.get("participants", [])
                rels = item.get("relations", [])

                if parts:
                    # Strategy:
                    # To organize participants neatly, we group them by 'Type' (e.g., Analyst, Manager).
                    # Each type gets its own horizontal row within the episode box.

                    # 1. Group participants by type
                    type_groups = {}
                    for p in parts:
                        p_type = p.get("type", "Participant")
                        if p_type not in type_groups:
                            type_groups[p_type] = []
                        type_groups[p_type].append(p)

                    # Sort types to ensure consistent ordering (e.g., alphabetical)
                    sorted_types = sorted(type_groups.keys())
                    num_groups = len(sorted_types)

                    # 2. Calculate vertical spacing for rows
                    # We have 'height' available (e.g. 1.0).
                    # Use margins to avoid edge crowding.
                    # 10% top, 10% bottom padding
                    margin_v = 0.2 * height
                    available_h = height - 2 * margin_v

                    if num_groups > 0:
                        row_height = available_h / num_groups
                    else:
                        row_height = available_h

                    p_coords = {}  # Store coordinates for relation lines

                    for g_idx, p_type in enumerate(sorted_types):
                        group_parts = type_groups[p_type]

                        # Calculate Y-coordinate for this row center
                        # Stacking from bottom to top
                        row_cy = (
                            y_pos + margin_v + (g_idx * row_height) + (row_height / 2)
                        )

                        # 3. Distribute participants horizontally in this row
                        # Margin of 10% on each side
                        cx_start = item["x"] + (item["width"] * 0.1)
                        row_width = item["width"] * 0.8

                        if len(group_parts) > 1:
                            cx_step = row_width / (len(group_parts) - 1)
                        else:
                            # Center it if only one
                            cx_step = 0
                            cx_start = item["x"] + (item["width"] / 2)

                        for i, p in enumerate(group_parts):
                            if len(group_parts) > 1:
                                px = cx_start + i * cx_step
                            else:
                                # Centered
                                px = cx_start

                            py = row_cy

                            # Register & Get Style (Color/Marker)
                            p_color, p_marker = self._register_participant(
                                p["id"], p["name"], p.get("type", "Participant")
                            )

                            # Draw Marker
                            ax.scatter(
                                [px],
                                [py],
                                color=p_color,
                                marker=p_marker,
                                # Marker size
                                s=100,
                                # Above box background
                                zorder=10,
                                edgecolor="white",
                            )

                            p_coords[p["id"]] = (px, py)

                    # --- Render Relations ---
                    # Draw lines connecting participants based on extracted relations
                    for rel in rels:
                        src_id = rel["src"]
                        dst_id = rel["dst"]
                        rel_name = rel.get("name", "Relation")

                        if src_id in p_coords and dst_id in p_coords:
                            sx, sy = p_coords[src_id]
                            dx, dy = p_coords[dst_id]

                            # Get style for this relation type
                            r_color, r_style = self._get_relation_style(rel_name)

                            # Draw line
                            ax.plot(
                                [sx, dx],
                                [sy, dy],
                                color=r_color,
                                alpha=0.8,
                                linestyle=r_style,
                                linewidth=1.5,
                                # Below markers
                                zorder=5,
                            )

        # --- 4. Final Formatting ---

        # Set Plot Limits
        ax.set_ylim(-1, max_y + 2)
        ax.set_xlim(-2, current_x + 2)

        # Configure X-axis Ticks
        # We rotate them for better readability of long timestamps
        ax.set_xticks(x_ticks)
        ax.set_xticklabels(x_tick_labels, rotation=45, ha="right", fontsize=10)

        ax.set_yticks([])  # Hide Y axis ticks as they have no semantic meaning here

        # Hide chart spines for a cleaner look
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_visible(False)

        # --- 5. Legend ---
        # Create a custom legend for participants
        handles = []
        labels = []

        # Participant Legend Items
        for p_id, (color, marker) in self.participant_style_map.items():
            info = self.participant_info_map.get(
                p_id, {"name": p_id, "type": "Unknown"}
            )
            # Group by type to avoid duplicate entries in legend if desired?
            # User request: "legent 后面展示的participat 种类 即括号里的应该是 participant_type 字段"
            # Current implementation lists every participant.
            # If we want to group by type, we would need to change logic.
            # For now, stick to per-participant but with type info.
            label_str = f"{info['name']} ({info['type']})"

            # Check if we already have this label (to avoid duplicates if multiple participants share name/type/style?)
            # But unique participants should probably be listed.

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

        # Relation Legend Items
        if self.relation_style_map:
            # Add a separator or just append?
            # Appending with a "heading" might be tricky in a single legend.
            # We can add a proxy artist for a title, or just list them.

            # Optional: Add a spacer/header
            handles.append(Line2D([0], [0], color="none", label=""))
            labels.append("--- Relations ---")

            for rel_name, (r_color, r_style) in self.relation_style_map.items():
                handle = Line2D(
                    [0],
                    [0],
                    color=r_color,
                    linestyle=r_style,
                    linewidth=2,
                    label=rel_name,
                )
                handles.append(handle)
                labels.append(rel_name)

        if handles:
            ax.legend(
                handles,
                labels,
                title="Legend",
                loc="upper left",
                # Place outside plot area
                bbox_to_anchor=(1, 1),
            )

        plt.title(f"Event Cascade: {evt_title}", fontsize=24, fontweight="bold", pad=20)
        plt.tight_layout()

        if output_path:
            # Save as requested format (usually PNG)
            plt.savefig(output_path, dpi=300, bbox_inches="tight")

            # Also save as high-res PDF
            # Replace extension or append .pdf
            base_name = output_path.rsplit(".", 1)[0]
            pdf_path = f"{base_name}.pdf"
            plt.savefig(pdf_path, format="pdf", bbox_inches="tight")

            plt.close()
            return output_path
        else:
            return fig
