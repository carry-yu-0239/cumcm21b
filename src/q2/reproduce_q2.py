"""复现问题二冻结的温度分层匹配与跨背景效应对比分析。

本脚本只实现《问题2_模型交接单》给定的四层证据链：温度端点比较、
严格匹配块、跨背景同对比族和局部二因素二阶对比。它不拟合统一预测模型，
不做因素重要性排名，也不把 A/B 编号作为物理因素。

运行：
    python src/q2/reproduce_q2.py --strict
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Iterable

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[2]
RAW_PATH = ROOT / "data" / "raw" / "q1_attachment1.xlsx"
PROCESSED_DIR = ROOT / "data" / "processed"
OUTPUT_DIR = ROOT / "outputs" / "q2"
TABLE_DIR = OUTPUT_DIR / "tables"
FIGURE_DIR = OUTPUT_DIR / "figures"
LOG_DIR = OUTPUT_DIR / "logs"
HANDOFF_PATH = ROOT / "docs" / "handoffs" / "q2_model_handoff.docx"

COMBINATIONS = [f"A{i}" for i in range(1, 15)] + [f"B{i}" for i in range(1, 8)]
RESPONSES = {"X_EtOH": "X_EtOH_pct", "S_C4": "S_C4_pct"}
FACTORS = {
    "co_loading_wt_pct": "Co loading (wt%)",
    "total_catalyst_mg": "Total catalyst mass (mg)",
    "ratio_key": "Co/SiO2:HAP mass ratio",
    "ethanol_feed_ml_min": "Ethanol feed (mL/min)",
    "packing_mode": "Packing mode",
}
FACTOR_ORDER = list(FACTORS)
EXPECTED_BLOCKS = {
    "co_loading_wt_pct": ["A4/A1/A2/A6", "A9/A10"],
    "total_catalyst_mg": ["A1/A12", "A3/A8", "B3/B4/B1/B6/B2"],
    "ratio_key": ["A14/A12/A13"],
    "ethanol_feed_ml_min": ["A1/A3", "A2/A5", "A7/A8/A12/A9", "B1/B5", "B2/B7"],
    "packing_mode": ["A12/B1", "A9/B5"],
}
EXPECTED_FAMILIES = {
    "co_loading_wt_pct:1->5",
    "total_catalyst_mg:100->400",
    "ethanol_feed_ml_min:0.9->1.68",
    "ethanol_feed_ml_min:0.3->1.68",
    "ethanol_feed_ml_min:1.68->2.1",
    "packing_mode:I->II",
}
EXPECTED_RECTANGLE_FACTORS = {("total_catalyst_mg", "ethanol_feed_ml_min"), ("ethanol_feed_ml_min", "packing_mode")}


@dataclass(frozen=True)
class MatchBlock:
    factor: str
    identifier: str
    groups: tuple[str, ...]
    levels: tuple[object, ...]
    common_temperatures: tuple[float, ...]
    background: tuple[tuple[str, object], ...]


@dataclass(frozen=True)
class Rectangle:
    factor_1: str
    factor_2: str
    groups: tuple[str, ...]
    level_1: tuple[object, object]
    level_2: tuple[object, object]
    background: tuple[tuple[str, object], ...]
    common_temperatures: tuple[float, ...]


def display_number(value: object) -> str:
    """Stable text keys for factors without float-equality matching."""
    if isinstance(value, (float, np.floating)):
        return f"{float(value):g}"
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    return str(value)


def display_level(factor: str, value: object) -> str:
    if factor == "packing_mode":
        return "I" if int(value) == 0 else "II"
    if factor == "ratio_key":
        return str(value)
    return display_number(value)


def sort_value(factor: str, value: object) -> tuple[float, str]:
    if factor == "ratio_key":
        left, right = str(value).split(":")
        return (float(left) / float(right), str(value))
    return (float(value), str(value))


def group_sort_key(group: str) -> int:
    return COMBINATIONS.index(group)


def factor_label(factor: str) -> str:
    return FACTORS[factor]


def parse_catalyst(group: str, description: str) -> dict[str, object]:
    """Parse a catalyst string while preserving A11 as a non-ratio special case."""
    text = re.sub(r"\s+", " ", description).strip()
    main = re.search(r"(?P<mc>\d+(?:\.\d+)?)mg\s*(?P<co>\d+(?:\.\d+)?)wt%Co/SiO2", text)
    feed = re.search(r"乙醇浓度(?P<q>\d+(?:\.\d+)?)ml/min", text)
    if main is None or feed is None:
        raise ValueError(f"Cannot parse catalyst description for {group}: {description!r}")

    mc = float(main.group("mc"))
    co = float(main.group("co"))
    q = float(feed.group("q"))
    hap = re.search(r"-\s*(?P<mh>\d+(?:\.\d+)?)mg\s*HAP", text)
    quartz = re.search(r"\+\s*(?P<mq>\d+(?:\.\d+)?)mg\s*石英砂", text)
    is_a11 = group == "A11"
    if is_a11:
        if hap is not None or quartz is None:
            raise ValueError("A11 must have quartz sand and no HAP.")
        mh = 0.0
        mq = float(quartz.group("mq"))
        ratio_key: str | None = None
        rho: float | None = None
    else:
        if hap is None or quartz is not None:
            raise ValueError(f"Ordinary HAP combination parsed incorrectly: {group}")
        mh = float(hap.group("mh"))
        mq = 0.0
        gcd = math.gcd(int(round(mc)), int(round(mh)))
        ratio_key = f"{int(round(mc)) // gcd}:{int(round(mh)) // gcd}"
        rho = mc / mh
    return {
        "group": group,
        "catalyst_description": description,
        "co_loading_wt_pct": co,
        "co_sio2_mass_mg": mc,
        "hap_mass_mg": mh,
        "quartz_sand_mass_mg": mq,
        "total_catalyst_mg": mc + mh,
        "ratio_key": ratio_key,
        "rho": rho,
        "ethanol_feed_ml_min": q,
        "packing_mode": 0 if group.startswith("A") else 1,
        "packing_mode_label": "I" if group.startswith("A") else "II",
        "is_a11_special": is_a11,
    }


def load_data(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = pd.read_excel(path, sheet_name=0)
    if raw.shape != (114, 10):
        raise ValueError(f"Unexpected Attachment 1 dimensions: {raw.shape}")
    raw = raw.copy()
    raw.iloc[:, 0] = raw.iloc[:, 0].ffill()
    raw.iloc[:, 1] = raw.iloc[:, 1].ffill()
    raw.columns = [
        "group",
        "catalyst_description",
        "temperature_c",
        "X_EtOH_pct",
        "S_ethylene_pct",
        "S_C4_pct",
        "S_acetaldehyde_pct",
        "S_C4_12_fatty_alcohol_pct",
        "S_methyl_benzaldehyde_alcohol_pct",
        "S_other_pct",
    ]
    raw = raw.dropna(subset=["group", "catalyst_description", "temperature_c", "X_EtOH_pct", "S_C4_pct"])
    raw["group"] = raw["group"].astype(str).str.strip()
    if sorted(raw["group"].unique(), key=group_sort_key) != COMBINATIONS:
        raise ValueError("The 21 expected catalyst labels were not recovered.")
    numeric = [column for column in raw.columns if column not in {"group", "catalyst_description"}]
    raw[numeric] = raw[numeric].apply(pd.to_numeric, errors="raise")
    factor_rows = [parse_catalyst(group, frame["catalyst_description"].iloc[0]) for group, frame in raw.groupby("group", sort=False)]
    factors = pd.DataFrame(factor_rows).sort_values("group", key=lambda s: s.map(group_sort_key)).reset_index(drop=True)
    records = raw.merge(factors, on=["group", "catalyst_description"], validate="many_to_one")
    records["selectivity_total_pct"] = records[[
        "S_ethylene_pct", "S_C4_pct", "S_acetaldehyde_pct", "S_C4_12_fatty_alcohol_pct",
        "S_methyl_benzaldehyde_alcohol_pct", "S_other_pct",
    ]].sum(axis=1)
    records["selectivity_balance_error_pct_point"] = records["selectivity_total_pct"] - 100.0
    records = records.sort_values(["group", "temperature_c"], key=lambda s: s.map(group_sort_key) if s.name == "group" else s).reset_index(drop=True)
    return records, factors


def temperatures_by_group(records: pd.DataFrame) -> dict[str, tuple[float, ...]]:
    return {
        group: tuple(frame["temperature_c"].astype(float).sort_values())
        for group, frame in records.groupby("group", sort=False)
    }


def common_temperatures(groups: Iterable[str], temperature_map: dict[str, tuple[float, ...]]) -> tuple[float, ...]:
    group_list = list(groups)
    return tuple(sorted(set.intersection(*(set(temperature_map[group]) for group in group_list))))


def enumerate_match_blocks(factors: pd.DataFrame, temperature_map: dict[str, tuple[float, ...]]) -> list[MatchBlock]:
    normal = factors.loc[~factors["is_a11_special"]].copy()
    blocks: list[MatchBlock] = []
    for factor in FACTOR_ORDER:
        background_cols = [column for column in FACTOR_ORDER if column != factor]
        grouped = normal.groupby(background_cols, dropna=False, sort=False)
        ordinal = 0
        for key, frame in grouped:
            if frame[factor].nunique(dropna=False) < 2:
                continue
            rows = frame.sort_values(factor, key=lambda s: s.map(lambda v: sort_value(factor, v)))
            groups = tuple(rows["group"])
            levels = tuple(rows[factor])
            ordinal += 1
            background = tuple(zip(background_cols, key if isinstance(key, tuple) else (key,)))
            blocks.append(MatchBlock(
                factor=factor,
                identifier=f"{factor}:{ordinal}",
                groups=groups,
                levels=levels,
                common_temperatures=common_temperatures(groups, temperature_map),
                background=background,
            ))
    return blocks


def record_value(records: pd.DataFrame, group: str, temperature: float, response: str) -> float:
    value = records.loc[(records["group"] == group) & (records["temperature_c"] == temperature), response]
    if len(value) != 1:
        raise ValueError(f"Expected one record for {group}, {temperature}, {response}; got {len(value)}")
    return float(value.iloc[0])


def block_rows(records: pd.DataFrame, block: MatchBlock) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for response_name, response_column in RESPONSES.items():
        matrix = np.array([
            [record_value(records, group, temperature, response_column) for group in block.groups]
            for temperature in block.common_temperatures
        ], dtype=float)
        grand = float(matrix.mean())
        level_means = matrix.mean(axis=0)
        temperature_means = matrix.mean(axis=1)
        crossings = any(np.any(np.diff(matrix[temperature_index]) * np.diff(matrix[temperature_index + 1]) < 0) for temperature_index in range(len(matrix) - 1))
        stable_rank = all(np.array_equal(np.argsort(matrix[0]), np.argsort(matrix[temperature_index])) for temperature_index in range(1, len(matrix)))
        for level_index, (group, level) in enumerate(zip(block.groups, block.levels)):
            rows.append({
                "factor": block.factor,
                "block_id": block.identifier,
                "group": group,
                "level": display_level(block.factor, level),
                "response": response_name,
                "mean_response_pct": level_means[level_index],
                "gamma_pct_point": level_means[level_index] - grand,
                "block_grand_mean_pct": grand,
                "common_temperatures_c": "/".join(display_number(t) for t in block.common_temperatures),
                "curves_cross": crossings,
                "rank_order_stable": stable_rank,
                **{f"response_{display_number(temperature)}c_pct": matrix[temperature_index, level_index] for temperature_index, temperature in enumerate(block.common_temperatures)},
                **{f"temperature_mean_{display_number(temperature)}c_pct": temperature_means[temperature_index] for temperature_index, temperature in enumerate(block.common_temperatures)},
            })
    return rows


def pairwise_contrasts(blocks: list[MatchBlock], records: pd.DataFrame) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for block in blocks:
        for low_index, high_index in combinations(range(len(block.groups)), 2):
            low_group, high_group = block.groups[low_index], block.groups[high_index]
            low_level, high_level = block.levels[low_index], block.levels[high_index]
            factor = block.factor
            key = f"{factor}:{display_level(factor, low_level)}->{display_level(factor, high_level)}"
            for response_name, response_column in RESPONSES.items():
                for temperature in block.common_temperatures:
                    rows.append({
                        "family_key": key,
                        "factor": factor,
                        "low_level": display_level(factor, low_level),
                        "high_level": display_level(factor, high_level),
                        "block_id": block.identifier,
                        "background": "; ".join(f"{factor_label(column)}={display_level(column, value)}" for column, value in block.background),
                        "low_group": low_group,
                        "high_group": high_group,
                        "temperature_c": temperature,
                        "response": response_name,
                        "delta_pct_point": record_value(records, high_group, temperature, response_column) - record_value(records, low_group, temperature, response_column),
                    })
    return rows


def family_outputs(contrast_rows: list[dict[str, object]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    all_rows = pd.DataFrame(contrast_rows)
    counts = all_rows[["family_key", "block_id"]].drop_duplicates().groupby("family_key").size()
    retained = set(counts[counts >= 2].index)
    detail = all_rows.loc[all_rows["family_key"].isin(retained)].copy()
    filtered: list[pd.DataFrame] = []
    for family_key, frame in detail.groupby("family_key", sort=False):
        background_temperatures = frame.groupby("block_id")["temperature_c"].agg(lambda values: set(values))
        shared = sorted(set.intersection(*background_temperatures.tolist()))
        filtered.append(frame.loc[frame["temperature_c"].isin(shared)].copy())
    detail = pd.concat(filtered, ignore_index=True).sort_values(["family_key", "response", "block_id", "temperature_c"])
    summaries: list[dict[str, object]] = []
    for (family_key, response), frame in detail.groupby(["family_key", "response"], sort=False):
        block_means = frame.groupby(["block_id", "background", "low_group", "high_group"], as_index=False)["delta_pct_point"].mean()
        signs = set(np.sign(frame["delta_pct_point"].to_numpy(dtype=float))) - {0.0}
        within_reversal = any((sub["delta_pct_point"] > 0).any() and (sub["delta_pct_point"] < 0).any() for _, sub in frame.groupby("block_id"))
        mean_signs = set(np.sign(block_means["delta_pct_point"].to_numpy(dtype=float))) - {0.0}
        if len(mean_signs) > 1:
            interpretation = "opposite directions across backgrounds"
        elif within_reversal:
            interpretation = "temperature-dependent direction within a background"
        elif len(signs) == 1:
            interpretation = "same direction; magnitude may vary by background"
        else:
            interpretation = "includes zero difference"
        summaries.append({
            "family_key": family_key,
            "response": response,
            "background_count": int(frame["block_id"].nunique()),
            "shared_temperatures_c": "/".join(display_number(v) for v in sorted(frame["temperature_c"].unique())),
            "minimum_delta_pct_point": float(frame["delta_pct_point"].min()),
            "maximum_delta_pct_point": float(frame["delta_pct_point"].max()),
            "background_mean_deltas_pct_point": "; ".join(
                f"{row.low_group}->{row.high_group}: {row.delta_pct_point:.2f}" for row in block_means.itertuples(index=False)
            ),
            "comparison_interpretation": interpretation,
        })
    return detail.reset_index(drop=True), pd.DataFrame(summaries)


def enumerate_rectangles(factors: pd.DataFrame, temperature_map: dict[str, tuple[float, ...]]) -> list[Rectangle]:
    normal = factors.loc[~factors["is_a11_special"]].copy()
    rectangles: list[Rectangle] = []
    for factor_1, factor_2 in combinations(FACTOR_ORDER, 2):
        remaining = [factor for factor in FACTOR_ORDER if factor not in {factor_1, factor_2}]
        for key, frame in normal.groupby(remaining, dropna=False, sort=False):
            for level_1_pair in combinations(sorted(frame[factor_1].unique(), key=lambda value: sort_value(factor_1, value)), 2):
                for level_2_pair in combinations(sorted(frame[factor_2].unique(), key=lambda value: sort_value(factor_2, value)), 2):
                    expected_cells = {(level_1, level_2) for level_1 in level_1_pair for level_2 in level_2_pair}
                    cell_frame = frame.loc[frame.apply(lambda row: (row[factor_1], row[factor_2]) in expected_cells, axis=1)]
                    found_cells = set(zip(cell_frame[factor_1], cell_frame[factor_2]))
                    if len(cell_frame) != 4 or found_cells != expected_cells:
                        continue
                    coordinate_groups: list[str] = []
                    for level_1 in level_1_pair:
                        for level_2 in level_2_pair:
                            coordinate_groups.append(cell_frame.loc[(cell_frame[factor_1] == level_1) & (cell_frame[factor_2] == level_2), "group"].iloc[0])
                    rectangles.append(Rectangle(
                        factor_1=factor_1,
                        factor_2=factor_2,
                        groups=tuple(coordinate_groups),
                        level_1=level_1_pair,
                        level_2=level_2_pair,
                        background=tuple(zip(remaining, key if isinstance(key, tuple) else (key,))),
                        common_temperatures=common_temperatures(coordinate_groups, temperature_map),
                    ))
    return rectangles


def rectangle_outputs(rectangles: list[Rectangle], records: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    interactions: list[dict[str, object]] = []
    sensitivity: list[dict[str, object]] = []
    for rectangle in rectangles:
        label = f"{rectangle.factor_1}__{rectangle.factor_2}"
        # Coordinate order is (low F1, low F2), (low F1, high F2), (high F1, low F2), (high F1, high F2).
        low_low, low_high, high_low, high_high = rectangle.groups
        for response_name, response_column in RESPONSES.items():
            values: list[tuple[float, float]] = []
            for temperature in rectangle.common_temperatures:
                interaction = (
                    record_value(records, high_high, temperature, response_column)
                    - record_value(records, high_low, temperature, response_column)
                    - record_value(records, low_high, temperature, response_column)
                    + record_value(records, low_low, temperature, response_column)
                )
                values.append((temperature, interaction))
                interactions.append({
                    "rectangle": label,
                    "factor_1": rectangle.factor_1,
                    "factor_2": rectangle.factor_2,
                    "factor_1_levels": f"{display_level(rectangle.factor_1, rectangle.level_1[0])}->{display_level(rectangle.factor_1, rectangle.level_1[1])}",
                    "factor_2_levels": f"{display_level(rectangle.factor_2, rectangle.level_2[0])}->{display_level(rectangle.factor_2, rectangle.level_2[1])}",
                    "groups_coordinate_order": "/".join(rectangle.groups),
                    "temperature_c": temperature,
                    "response": response_name,
                    "interaction_I_pct_point": interaction,
                })
            for omitted_temperature, _ in values:
                kept = [interaction for temperature, interaction in values if temperature != omitted_temperature]
                sensitivity.append({
                    "rectangle": label,
                    "response": response_name,
                    "omitted_temperature_c": omitted_temperature,
                    "mean_I_without_temperature_pct_point": float(np.mean(kept)),
                    "sign_preserved_vs_full_mean": bool(np.sign(np.mean(kept)) == np.sign(np.mean([item[1] for item in values]))),
                })
    return pd.DataFrame(interactions), pd.DataFrame(sensitivity)


def temperature_overall(records: pd.DataFrame) -> pd.DataFrame:
    pivot = records.loc[records["temperature_c"].isin([250, 275, 300, 350])].pivot(index="group", columns="temperature_c", values=["X_EtOH_pct", "S_C4_pct"])
    rows: list[dict[str, object]] = []
    for group in COMBINATIONS:
        row = {"group": group}
        for response in ["X_EtOH_pct", "S_C4_pct"]:
            row[f"{response}_250c"] = float(pivot.loc[group, (response, 250)])
            row[f"{response}_275c"] = float(pivot.loc[group, (response, 275)])
            row[f"{response}_300c"] = float(pivot.loc[group, (response, 300)])
            row[f"{response}_350c"] = float(pivot.loc[group, (response, 350)])
            row[f"{response}_delta_250_to_350_pct_point"] = row[f"{response}_350c"] - row[f"{response}_250c"]
        rows.append(row)
    detail = pd.DataFrame(rows)
    summary_rows = []
    for response in ["X_EtOH_pct", "S_C4_pct"]:
        delta = detail[f"{response}_delta_250_to_350_pct_point"]
        summary_rows.append({
            "group": "ALL_21_SUMMARY",
            "response": response,
            "positive_delta_count": int((delta > 0).sum()),
            "mean_delta_250_to_350_pct_point": float(delta.mean()),
            "median_delta_250_to_350_pct_point": float(delta.median()),
        })
    return detail, pd.DataFrame(summary_rows)


def latex_escape(value: object) -> str:
    text = str(value)
    for source, replacement in [("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"), ("_", r"\_"), ("#", r"\#")]:
        text = text.replace(source, replacement)
    return text


TEX_COLUMNS = {
    "q2_factor_parsing": ["group", "co_loading_wt_pct", "co_sio2_mass_mg", "hap_mass_mg", "quartz_sand_mass_mg", "total_catalyst_mg", "ratio_key", "ethanol_feed_ml_min", "packing_mode_label", "is_a11_special"],
    "q2_temperature_trajectories": ["group", "X_EtOH_pct_delta_250_to_350_pct_point", "S_C4_pct_delta_250_to_350_pct_point"],
    "q2_multilevel_matching_responses": ["factor", "block_id", "group", "level", "response", "mean_response_pct", "gamma_pct_point", "common_temperatures_c", "curves_cross", "rank_order_stable"],
    "q2_contrast_family_differences": ["family_key", "low_group", "high_group", "temperature_c", "response", "delta_pct_point"],
    "q2_local_rectangle_interactions": ["rectangle", "groups_coordinate_order", "temperature_c", "response", "interaction_I_pct_point"],
    "q2_specific_contrast_evidence": ["comparison", "response", "background_count", "shared_temperatures_c", "minimum_effect_pct_point", "maximum_effect_pct_point", "comparison_interpretation"],
    "q2_factor_conclusions": ["factor", "response", "scope_qualified_conclusion", "evidence"],
}


def write_table(frame: pd.DataFrame, stem: str, caption: str, label: str, decimals: int = 2) -> None:
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    frame.to_csv(TABLE_DIR / f"{stem}.csv", index=False, encoding="utf-8-sig", float_format=f"%.{decimals}f")
    printable = frame.loc[:, TEX_COLUMNS.get(stem, list(frame.columns))].copy()
    columns = list(printable.columns)
    header = " & ".join(latex_escape(column) for column in columns) + r" \\"
    header += "\n" + r"\midrule" + "\n" + r"\endhead"
    body_rows = []
    for row in printable.itertuples(index=False, name=None):
        values = []
        for value in row:
            if pd.isna(value):
                values.append("--")
            elif isinstance(value, (float, np.floating)):
                values.append(f"{float(value):.{decimals}f}")
            elif isinstance(value, (bool, np.bool_)):
                values.append("Yes" if value else "No")
            else:
                values.append(latex_escape(value))
        body_rows.append(" & ".join(values) + r" \\")
    tex = "\n".join([
        r"\begingroup\scriptsize",
        r"\begin{longtable}{" + "l" * len(columns) + "}",
        rf"\caption{{{caption}}}\label{{{label}}}\\",
        r"\toprule",
        header,
        *body_rows,
        r"\bottomrule",
        r"\end{longtable}",
        r"\endgroup",
        "",
    ])
    (TABLE_DIR / f"{stem}.tex").write_text(tex, encoding="utf-8")


def plot_temperature_trajectories(records: pd.DataFrame) -> None:
    temperatures = [250, 275, 300, 350]
    for response_name, response_column in RESPONSES.items():
        figure, axis = plt.subplots(figsize=(8.6, 5.2))
        matrix = []
        for group in COMBINATIONS:
            values = [record_value(records, group, temperature, response_column) for temperature in temperatures]
            matrix.append(values)
            axis.plot(temperatures, values, color="#8DA0A6", linewidth=0.8, alpha=0.75)
        axis.plot(temperatures, np.mean(matrix, axis=0), color="#1F5E4B", linewidth=2.7, marker="o", label="Equal-weight mean")
        axis.set(xlabel="Temperature (°C)", ylabel=f"{response_name} (%)", title=f"21 catalyst trajectories: {response_name}")
        axis.grid(alpha=0.22)
        axis.legend(frameon=False)
        figure.tight_layout()
        figure.savefig(FIGURE_DIR / f"q2_temperature_trajectories_{response_name}.png", dpi=220)
        plt.close(figure)


def plot_multilevel_blocks(blocks: list[MatchBlock], records: pd.DataFrame) -> None:
    multi = [block for block in blocks if len(block.groups) >= 3]
    for response_name, response_column in RESPONSES.items():
        figure, axes = plt.subplots(2, 2, figsize=(10.6, 7.4), sharex=False)
        for axis, block in zip(axes.flat, multi):
            for group, level in zip(block.groups, block.levels):
                values = [record_value(records, group, temperature, response_column) for temperature in block.common_temperatures]
                axis.plot(block.common_temperatures, values, marker="o", linewidth=1.5, label=f"{display_level(block.factor, level)} ({group})")
            axis.set_title(f"{factor_label(block.factor)}: {'/'.join(block.groups)}", fontsize=9)
            axis.set_xlabel("Temperature (°C)")
            axis.set_ylabel(f"{response_name} (%)")
            axis.grid(alpha=0.22)
            axis.legend(fontsize=7, frameon=False, ncol=2)
        figure.tight_layout()
        figure.savefig(FIGURE_DIR / f"q2_multilevel_blocks_{response_name}.png", dpi=220)
        plt.close(figure)


def plot_contrast_families(detail: pd.DataFrame) -> None:
    for response_name in RESPONSES:
        figure, axes = plt.subplots(3, 2, figsize=(10.6, 9.4), sharex=False)
        for axis, (family_key, frame) in zip(axes.flat, detail.loc[detail["response"] == response_name].groupby("family_key", sort=False)):
            for _, background in frame.groupby("block_id", sort=False):
                description = f"{background['low_group'].iloc[0]}→{background['high_group'].iloc[0]}"
                axis.plot(background["temperature_c"], background["delta_pct_point"], marker="o", linewidth=1.5, label=description)
            axis.axhline(0, color="black", linewidth=0.85)
            axis.set_title(family_key.replace("_", " "), fontsize=9)
            axis.set_xlabel("Temperature (°C)")
            axis.set_ylabel("Δ (percentage points)")
            axis.grid(alpha=0.22)
            axis.legend(fontsize=7, frameon=False, loc="best")
        figure.tight_layout()
        figure.savefig(FIGURE_DIR / f"q2_contrast_families_{response_name}.png", dpi=220)
        plt.close(figure)


def plot_rectangles(interactions: pd.DataFrame, sensitivity: pd.DataFrame) -> None:
    rectangles = list(interactions["rectangle"].drop_duplicates())
    for response_name in RESPONSES:
        figure, axes = plt.subplots(1, 2, figsize=(10.4, 4.2), sharey=False)
        for axis, rectangle in zip(axes, rectangles):
            frame = interactions.loc[(interactions["response"] == response_name) & (interactions["rectangle"] == rectangle)]
            axis.plot(frame["temperature_c"], frame["interaction_I_pct_point"], marker="o", color="#A13E2B", linewidth=1.8)
            axis.axhline(0, color="black", linewidth=0.85)
            axis.set(title=rectangle.replace("_", " "), xlabel="Temperature (°C)", ylabel="I (percentage points)")
            axis.grid(alpha=0.22)
        figure.tight_layout()
        figure.savefig(FIGURE_DIR / f"q2_local_rectangles_{response_name}.png", dpi=220)
        plt.close(figure)

    figure, axes = plt.subplots(2, 2, figsize=(10.4, 7.2), sharex=False)
    for axis, ((rectangle, response), frame) in zip(axes.flat, sensitivity.groupby(["rectangle", "response"], sort=False)):
        axis.bar(frame["omitted_temperature_c"].astype(str), frame["mean_I_without_temperature_pct_point"], color="#587B9B")
        axis.axhline(0, color="black", linewidth=0.85)
        axis.set(title=f"{rectangle.replace('_', ' ')} / {response}", xlabel="Omitted temperature (°C)", ylabel="Mean I after omission")
        axis.grid(axis="y", alpha=0.22)
    figure.tight_layout()
    figure.savefig(FIGURE_DIR / "q2_leave_one_temperature_sensitivity.png", dpi=220)
    plt.close(figure)


def factor_conclusions(multilevel: pd.DataFrame, families: pd.DataFrame, interactions: pd.DataFrame) -> pd.DataFrame:
    # These statements are the handoff's frozen, scope-qualified conclusions; their evidence files are generated above.
    return pd.DataFrame([
        {"factor": "Temperature", "response": "X_EtOH and S_C4", "scope_qualified_conclusion": "Across all 21 observed combinations, the 250→350°C endpoint change is positive; local intervals may still be non-monotone.", "evidence": "q2_temperature_overall"},
        {"factor": "Co loading", "response": "X_EtOH", "scope_qualified_conclusion": "The 1→5 wt% contrast reverses direction across the two matched backgrounds.", "evidence": "q2_contrast_family_summary"},
        {"factor": "Co loading", "response": "S_C4", "scope_qualified_conclusion": "The 1→5 wt% contrast is negative in both reproducible backgrounds.", "evidence": "q2_contrast_family_summary"},
        {"factor": "Ethanol feed", "response": "X_EtOH and S_C4", "scope_qualified_conclusion": "No uniform main effect is asserted outside the matched temperature and background conditions.", "evidence": "q2_contrast_family_summary"},
        {"factor": "Co/SiO2:HAP ratio", "response": "X_EtOH and S_C4", "scope_qualified_conclusion": "At fixed 100 mg total catalyst in the three-level block, higher HAP share aligns with higher conversion; selectivity is non-monotone.", "evidence": "q2_multilevel_matching_responses"},
        {"factor": "Total catalyst mass", "response": "X_EtOH and S_C4", "scope_qualified_conclusion": "The five-level packing-II block is non-monotone; its best equal-weight levels differ by response.", "evidence": "q2_multilevel_matching_responses"},
        {"factor": "Packing mode", "response": "X_EtOH and S_C4", "scope_qualified_conclusion": "The I/II contrast depends on ethanol-feed background; neither mode is globally superior.", "evidence": "q2_contrast_family_summary"},
        {"factor": "Local non-additivity", "response": "X_EtOH and S_C4", "scope_qualified_conclusion": "Only total catalyst mass–ethanol feed and ethanol feed–packing mode form complete local 2×2 structures under the five-factor matching rule.", "evidence": "q2_local_rectangle_interactions; q2_leave_one_temperature_sensitivity"},
    ])


def contrast_evidence(family_summary: pd.DataFrame, interactions: pd.DataFrame, sensitivity: pd.DataFrame) -> pd.DataFrame:
    rows = family_summary[["family_key", "response", "background_count", "shared_temperatures_c", "minimum_delta_pct_point", "maximum_delta_pct_point", "comparison_interpretation"]].copy()
    rows = rows.rename(columns={"family_key": "comparison", "minimum_delta_pct_point": "minimum_effect_pct_point", "maximum_delta_pct_point": "maximum_effect_pct_point"})
    local_rows = []
    for (rectangle, response), frame in interactions.groupby(["rectangle", "response"], sort=False):
        sens = sensitivity.loc[(sensitivity["rectangle"] == rectangle) & (sensitivity["response"] == response), "mean_I_without_temperature_pct_point"]
        local_rows.append({
            "comparison": f"local rectangle: {rectangle}",
            "response": response,
            "background_count": 1,
            "shared_temperatures_c": "/".join(display_number(v) for v in frame["temperature_c"]),
            "minimum_effect_pct_point": float(frame["interaction_I_pct_point"].min()),
            "maximum_effect_pct_point": float(frame["interaction_I_pct_point"].max()),
            "comparison_interpretation": f"local second-order contrast; omission means span {sens.min():.2f} to {sens.max():.2f}",
        })
    return pd.concat([rows, pd.DataFrame(local_rows)], ignore_index=True)


def validation(records: pd.DataFrame, factors: pd.DataFrame, blocks: list[MatchBlock], family_summary: pd.DataFrame, rectangles: list[Rectangle], temperature_summary: pd.DataFrame, interactions: pd.DataFrame, sensitivity: pd.DataFrame) -> dict[str, object]:
    block_actual = defaultdict(list)
    for block in blocks:
        block_actual[block.factor].append("/".join(block.groups))
    actual_sets = {factor: sorted(values) for factor, values in block_actual.items()}
    expected_sets = {factor: sorted(values) for factor, values in EXPECTED_BLOCKS.items()}
    normalized_actual_sets = {factor: sorted("/".join(sorted(item.split("/"), key=group_sort_key)) for item in values) for factor, values in actual_sets.items()}
    normalized_expected_sets = {factor: sorted("/".join(sorted(item.split("/"), key=group_sort_key)) for item in values) for factor, values in expected_sets.items()}
    family_keys = set(family_summary["family_key"].unique())
    rectangle_factors = {(rectangle.factor_1, rectangle.factor_2) for rectangle in rectangles}
    overall = {row.response: row for row in temperature_summary.itertuples(index=False)}
    checks = {
        "raw_record_count_is_114": len(records) == 114,
        "combination_count_is_21": records["group"].nunique() == 21,
        "responses_within_0_100": bool(((records[["X_EtOH_pct", "S_C4_pct"]] >= 0) & (records[["X_EtOH_pct", "S_C4_pct"]] <= 100)).all().all()),
        "selectivity_balance_max_abs_error_le_0_1": float(records["selectivity_balance_error_pct_point"].abs().max()) <= 0.1,
        "a11_ratio_is_undefined": pd.isna(factors.loc[factors["group"] == "A11", "ratio_key"].iloc[0]),
        "a11_excluded_from_matching_pool": all("A11" not in block.groups for block in blocks),
        "common_temperature_set_is_250_275_300_350": set.intersection(*(set(frame["temperature_c"]) for _, frame in records.groupby("group"))) == {250, 275, 300, 350},
        "temperature_X_21_of_21_positive": overall["X_EtOH_pct"].positive_delta_count == 21,
        "temperature_S_21_of_21_positive": overall["S_C4_pct"].positive_delta_count == 21,
        "temperature_X_mean_near_handoff": abs(overall["X_EtOH_pct"].mean_delta_250_to_350_pct_point - 24.46) < 0.06,
        "temperature_S_mean_near_handoff": abs(overall["S_C4_pct"].mean_delta_250_to_350_pct_point - 15.30) < 0.06,
        "strict_block_structure_matches_handoff": normalized_actual_sets == normalized_expected_sets,
        "six_reproducible_contrast_families": family_keys == EXPECTED_FAMILIES,
        "two_complete_rectangles": rectangle_factors == EXPECTED_RECTANGLE_FACTORS,
        "qz_350_x_near_3_07": abs(float(interactions.loc[(interactions["rectangle"] == "ethanol_feed_ml_min__packing_mode") & (interactions["response"] == "X_EtOH") & (interactions["temperature_c"] == 350), "interaction_I_pct_point"].iloc[0]) - 3.07) < 0.06,
        "qz_350_s_near_minus_19_41": abs(float(interactions.loc[(interactions["rectangle"] == "ethanol_feed_ml_min__packing_mode") & (interactions["response"] == "S_C4") & (interactions["temperature_c"] == 350), "interaction_I_pct_point"].iloc[0]) + 19.41) < 0.06,
        "all_omission_signs_preserved": bool(sensitivity["sign_preserved_vs_full_mean"].all()),
    }
    return {
        "model": "基于温度分层匹配与跨背景效应对比的催化因素影响分析",
        "checks": checks,
        "passed": all(checks.values()),
        "strict_blocks": actual_sets,
        "reproducible_families": sorted(family_keys),
        "rectangles": sorted(" × ".join(pair) for pair in rectangle_factors),
        "temperature_summary": [row._asdict() for row in temperature_summary.itertuples(index=False)],
        "source_hashes": {str(RAW_PATH.relative_to(ROOT)): sha256(RAW_PATH), str(HANDOFF_PATH.relative_to(ROOT)): sha256(HANDOFF_PATH) if HANDOFF_PATH.exists() else "not_present"},
    }


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_logs(report: dict[str, object], rectangles: list[Rectangle]) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    (LOG_DIR / "q2_validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    status_lines = ["# 问题二复现与结构校验", "", f"- 总体状态：{'通过' if report['passed'] else '失败'}", ""]
    status_lines.extend(f"- {'通过' if passed else '失败'}：`{name}`" for name, passed in report["checks"].items())
    status_lines.extend(["", "## 口径说明", "", "- 原始 0 保留为实验结果；未实测温度未补值或插值。", "- A11 仅参与温度总体分析，未作为普通 Co/SiO2:HAP 配比点。", "- 局部二阶对比是百分点加法尺度的非加性，不报告显著性检验或因果结论。"])
    (LOG_DIR / "q2_validation.md").write_text("\n".join(status_lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="Fail with non-zero status when frozen structural checks fail.")
    args = parser.parse_args()
    for directory in [PROCESSED_DIR, TABLE_DIR, FIGURE_DIR, LOG_DIR]:
        directory.mkdir(parents=True, exist_ok=True)

    records, factors = load_data(RAW_PATH)
    records.to_csv(PROCESSED_DIR / "q2_attachment1_parsed_records.csv", index=False, encoding="utf-8-sig", float_format="%.8f")
    temperature_map = temperatures_by_group(records)
    blocks = enumerate_match_blocks(factors, temperature_map)
    temperature_detail, temperature_summary = temperature_overall(records)
    multilevel = pd.DataFrame([row for block in blocks if len(block.groups) >= 3 for row in block_rows(records, block)])
    contrasts = pairwise_contrasts(blocks, records)
    family_detail, family_summary = family_outputs(contrasts)
    rectangles = enumerate_rectangles(factors, temperature_map)
    interactions, sensitivity = rectangle_outputs(rectangles, records)

    factor_table = factors[["group", "catalyst_description", "co_loading_wt_pct", "co_sio2_mass_mg", "hap_mass_mg", "quartz_sand_mass_mg", "total_catalyst_mg", "ratio_key", "ethanol_feed_ml_min", "packing_mode_label", "is_a11_special"]].copy()
    block_table = pd.DataFrame([{
        "factor": factor_label(block.factor),
        "block_id": block.identifier,
        "groups": "/".join(block.groups),
        "factor_levels": "/".join(display_level(block.factor, level) for level in block.levels),
        "common_temperatures_c": "/".join(display_number(value) for value in block.common_temperatures),
        "fixed_background": "; ".join(f"{factor_label(key)}={display_level(key, value)}" for key, value in block.background),
    } for block in blocks])
    conclusions = factor_conclusions(multilevel, family_summary, interactions)
    evidence = contrast_evidence(family_summary, interactions, sensitivity)

    write_table(factor_table, "q2_factor_parsing", "Experiment-factor parsing for the 21 catalyst combinations", "tab:q2-factor-parsing")
    write_table(temperature_detail, "q2_temperature_trajectories", "Common-temperature trajectories by catalyst combination", "tab:q2-temperature-trajectories")
    write_table(temperature_summary, "q2_temperature_overall", "250 to 350 degree C endpoint changes across all 21 combinations", "tab:q2-temperature-overall")
    write_table(block_table, "q2_strict_match_blocks", "Automatically enumerated strict matching blocks", "tab:q2-strict-blocks")
    write_table(multilevel, "q2_multilevel_matching_responses", "Multi-level matching-block temperature responses and equal-weight summaries", "tab:q2-multilevel")
    write_table(family_detail, "q2_contrast_family_differences", "Temperature-stratified differences in six reproducible contrast families", "tab:q2-contrast-detail")
    write_table(family_summary, "q2_contrast_family_summary", "Six cross-background contrast-family summaries", "tab:q2-contrast-summary")
    write_table(interactions, "q2_local_rectangle_interactions", "Local 2 by 2 second-order contrasts", "tab:q2-local-interactions")
    write_table(sensitivity, "q2_leave_one_temperature_sensitivity", "Leave-one-temperature sensitivity for local second-order contrasts", "tab:q2-sensitivity")
    write_table(evidence, "q2_specific_contrast_evidence", "Specific matched-comparison evidence", "tab:q2-evidence")
    write_table(conclusions, "q2_factor_conclusions", "Scope-qualified factor conclusions", "tab:q2-conclusions")

    plot_temperature_trajectories(records)
    plot_multilevel_blocks(blocks, records)
    plot_contrast_families(family_detail)
    plot_rectangles(interactions, sensitivity)
    report = validation(records, factors, blocks, family_summary, rectangles, temperature_summary, interactions, sensitivity)
    write_logs(report, rectangles)
    print(json.dumps({"passed": report["passed"], "checks": report["checks"]}, ensure_ascii=False, indent=2))
    return 0 if report["passed"] or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
