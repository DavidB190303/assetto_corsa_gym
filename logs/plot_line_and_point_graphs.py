"""
plot_training_log.py

Simple plotting helper for Assetto Corsa Gym training logs.

Usage:
    1. Put this file next to your log.log, or set LOG_FILE below.
    2. Set X_AXIS and Y_AXIS to the metric you want to plot.
    3. Run:
        python plot_training_log.py

Example:
    X_AXIS = "episode"
    Y_AXIS = "ep_reward"

The script parses episode-level values from the log and creates a plot.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import pandas as pd
import matplotlib.pyplot as plt


# =============================================================================
# USER SETTINGS
# =============================================================================

LOG_FILE = Path("log.log")

# Choose what to plot here.
# Good x-axis choices:
#   "episode", "total_steps", "timestamp"
#
# Good y-axis choices:
#   "ep_reward", "ep_steps", "speed_mean", "speed_max", "max_abs_gap",
#   "packages_lost", "fps", "ballast", "road_temp", "track_grip",
#   "ep_bestLapTime", "best_lap_reported"
X_AXIS = "track_grip"
Y_AXIS = "ep_reward"

# Optional: smooth the y-axis with a rolling mean.
# Set to 1 to disable smoothing.
ROLLING_WINDOW = 1

# Choose how the data should be drawn:
#   "line"   -> connect points with a line, as before
#   "points" -> show only the individual points
PLOT_STYLE = "points"

# Save image file as well as showing it.
SAVE_PLOT = False
OUTPUT_FILE = "training_plot.png"


# =============================================================================
# PARSER
# =============================================================================

RE_RESET = re.compile(r"Reset AC\. Episode\s+(?P<episode>\d+)\s+total_steps:\s+(?P<total_steps>\d+)")
RE_RANDOMIZATION = re.compile(
    r"Updated race\.ini with ballast=(?P<ballast>[-+]?\d*\.?\d+)kg,\s*"
    r"road_temp=(?P<road_temp>[-+]?\d*\.?\d+)C,\s*"
    r"random_track_grip=(?P<track_grip>[-+]?\d*\.?\d+)"
)
RE_TERMINATION_OFFTRACK = re.compile(
    r"out_of_track\. N wheels out:\s*(?P<wheels_out>\d+)\.\s*"
    r"LapDist:\s*(?P<offtrack_lapdist>[-+]?\d*\.?\d+)\s*"
    r"x:\s*(?P<offtrack_x>[-+]?\d*\.?\d+)\s*"
    r"y:\s*(?P<offtrack_y>[-+]?\d*\.?\d+)"
)
RE_STATS = re.compile(
    r"total_steps:\s*(?P<stats_total_steps>\d+)\s+"
    r"ep_steps:\s*(?P<ep_steps>\d+)\s+"
    r"ep_reward:\s*(?P<ep_reward>[-+]?\d*\.?\d+)\s+"
    r"LapDist:\s*(?P<lapdist>[-+]?\d*\.?\d+)\s+"
    r"packages lost\s*(?P<packages_lost>\d+)\s+"
    r"BestLap:\s*(?P<best_lap_reported>[-+]?\d*\.?\d+)"
)
RE_EP_BEST_LAP = re.compile(r"ep_bestLapTime:\s*(?P<ep_bestLapTime>[-+]?\d*\.?\d+)")
RE_SPEED = re.compile(
    r"speed_mean:\s*(?P<speed_mean>[-+]?\d*\.?\d+)\s+"
    r"speed_max:\s*(?P<speed_max>[-+]?\d*\.?\d+)\s+"
    r"max_abs_gap:\s*(?P<max_abs_gap>[-+]?\d*\.?\d+)\s+"
    r"ep_laps:\s*(?P<ep_laps>\d+)"
)
RE_AGENT_DONE = re.compile(
    r"Episode done\. Took\s*(?P<episode_wall_time>[-+]?\d*\.?\d+)s\.\s+"
    r"Steps per episode:\s*(?P<steps_per_episode>\d+)\.\s+"
    r"Buffer size:\s*(?P<buffer_size>\d+)\s+"
    r"fps:\s*(?P<fps>[-+]?\d*\.?\d+)"
)
RE_DT = re.compile(
    r"dt avr:\s*(?P<dt_avg>[-+]?\d*\.?\d+)\s+"
    r"std:\s*(?P<dt_std>[-+]?\d*\.?\d+)\s+"
    r"min:\s*(?P<dt_min>[-+]?\d*\.?\d+)\s+"
    r"max:\s*(?P<dt_max>[-+]?\d*\.?\d+)"
)


def _to_number(value: str):
    """Convert a regex string to int or float."""
    if value is None:
        return None
    if re.fullmatch(r"[-+]?\d+", value):
        return int(value)
    return float(value)


def _timestamp_from_line(line: str) -> Optional[str]:
    """Extract timestamp at the start of a log line."""
    match = re.match(r"(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})", line)
    return match.group("timestamp") if match else None


def parse_training_log(log_file: Path) -> pd.DataFrame:
    """
    Parse episode-level information from an Assetto Corsa Gym training log.

    Returns:
        DataFrame where each row is one episode.
    """
    episodes = []
    current = {}

    def update_from_match(pattern, line):
        match = pattern.search(line)
        if not match:
            return False
        for key, value in match.groupdict().items():
            current[key] = _to_number(value)
        return True

    with log_file.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            timestamp = _timestamp_from_line(line)

            reset_match = RE_RESET.search(line)
            if reset_match:
                # Start a new episode record.
                current = {
                    "timestamp": timestamp,
                    "episode": int(reset_match.group("episode")),
                    "total_steps": int(reset_match.group("total_steps")),
                    "termination_reason": None,
                }
                continue

            if not current:
                continue

            update_from_match(RE_RANDOMIZATION, line)
            update_from_match(RE_TERMINATION_OFFTRACK, line)
            update_from_match(RE_STATS, line)
            update_from_match(RE_EP_BEST_LAP, line)
            update_from_match(RE_SPEED, line)
            update_from_match(RE_DT, line)

            if "Terminate episode. is_out_of_track" in line:
                current["termination_reason"] = "out_of_track"
            elif "Race stopped. Speed too low" in line:
                current["termination_reason"] = "low_speed"
            elif "Terminate episode. Max steps" in line:
                current["termination_reason"] = "max_steps"
            elif "Terminate. Lap ended by Assetto Corsa" in line:
                current["termination_reason"] = "lap_ended_by_ac"

            done_match = RE_AGENT_DONE.search(line)
            if done_match:
                for key, value in done_match.groupdict().items():
                    current[key] = _to_number(value)

                # Episode is complete when the agent logs "Episode done".
                episodes.append(current.copy())
                current = {}

    df = pd.DataFrame(episodes)

    if not df.empty and "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], format="%Y-%m-%d %H:%M:%S,%f", errors="coerce")

    return df


# =============================================================================
# PLOTTING
# =============================================================================

def plot_line(df: pd.DataFrame, x_axis: str, y_axis: str, rolling_window: int = 1) -> None:
    """Create a simple plot from selected DataFrame columns."""
    if df.empty:
        raise ValueError("No complete episodes found in the log.")

    if x_axis not in df.columns:
        raise ValueError(
            f"Unknown x-axis '{x_axis}'. Available columns:\n{sorted(df.columns.tolist())}"
        )

    if y_axis not in df.columns:
        raise ValueError(
            f"Unknown y-axis '{y_axis}'. Available columns:\n{sorted(df.columns.tolist())}"
        )

    plot_df = df[[x_axis, y_axis]].dropna().copy()

    if plot_df.empty:
        raise ValueError(f"No valid data found for x='{x_axis}' and y='{y_axis}'.")

    y_values = plot_df[y_axis]
    label = y_axis

    if rolling_window and rolling_window > 1:
        y_values = y_values.rolling(rolling_window, min_periods=1).mean()
        label = f"{y_axis} ({rolling_window}-episode rolling mean)"

    plt.figure(figsize=(11, 6))

    if PLOT_STYLE == "line":
        plt.plot(plot_df[x_axis], y_values, marker="o", linewidth=1.5)
    elif PLOT_STYLE == "points":
        plt.scatter(plot_df[x_axis], y_values)
    else:
        raise ValueError("PLOT_STYLE must be either 'line' or 'points'.")

    plt.xlabel(x_axis)
    plt.ylabel(label)
    plt.title(f"{label} over {x_axis}")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()

    if SAVE_PLOT:
        plt.savefig(OUTPUT_FILE, dpi=200)
        print(f"Saved plot to: {OUTPUT_FILE}")

    plt.show()


def main() -> None:
    df = parse_training_log(LOG_FILE)

    print(f"Parsed {len(df)} complete episodes.")
    print("\nAvailable columns:")
    for col in df.columns:
        print(f"  - {col}")

    # Save parsed episode table for further analysis.
    csv_file = "parsed_training_log.csv"
    df.to_csv(csv_file, index=False)
    print(f"\nSaved parsed episode table to: {csv_file}")

    plot_line(df, X_AXIS, Y_AXIS, ROLLING_WINDOW)


if __name__ == "__main__":
    main()
