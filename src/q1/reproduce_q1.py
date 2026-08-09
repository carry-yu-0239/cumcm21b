"""复现并核验问题一冻结交接成果。

此脚本仅实现《问题1_模型交接单》已经冻结的低阶经验模型：
每个催化剂组合内的线性/二次温度回归、固定中心化的 LOOCV，及附件2的
时间序列派生量。它不做跨组合排名、因素归因或工艺优化，也不重新绘制交接
单内已验收的图形。

运行：
    python src/q1/reproduce_q1.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
TABLE_DIR = ROOT / "outputs" / "q1" / "tables"
LOG_DIR = ROOT / "outputs" / "q1" / "logs"
HANDOFF_PATH = ROOT / "docs" / "handoffs" / "q1_frozen_handoff.docx"
FROZEN_FIGURES = {
    "attachment1_conversion_fits": ROOT / "paper" / "figures" / "q1_handoff" / "appendix_c_conversion_fits.png",
    "attachment1_selectivity_fits": ROOT / "paper" / "figures" / "q1_handoff" / "appendix_c_selectivity_fits.png",
    "attachment2_time_stability": ROOT / "paper" / "figures" / "q1_handoff" / "appendix_c_time_stability.png",
}

COMBINATIONS = [f"A{i}" for i in range(1, 15)] + [f"B{i}" for i in range(1, 8)]

# 以下字典是交接单附录 A、B 的冻结值，供复现结果核验；不是代码重新选模。
FROZEN_LOO = {
    "X_EtOH": {
        "A1": (6.535, 5.292, "二次", "总体上升且增幅扩大；二次LOOCV较低"),
        "A2": (3.970, 9.006, "线性", "持续上升，线性LOOCV明显更低"),
        "A3": (8.693, 15.546, "线性（总体）", "总体上升；400--450°C增幅明显缩小，二次LOOCV不稳定，高温趋缓单独描述"),
        "A4": (3.263, 7.027, "线性", "持续上升，线性LOOCV更低且拟合已较好"),
        "A5": (15.654, 4.332, "二次", "275°C短暂下降后明显加速上升；二次LOOCV显著改善"),
        "A6": (9.080, 14.628, "线性（总体）", "275°C轻微下降后快速上升；二次LOOCV更差，局部非线性不作强识别"),
        "A7": (1.401, 0.855, "线性", "持续近似均匀上升；两模型均好，优先线性"),
        "A8": (8.300, 2.625, "二次", "持续上升且高温段增幅扩大；二次LOOCV显著改善"),
        "A9": (12.540, 6.908, "二次", "持续上升并在高温段明显加速；二次LOOCV改善"),
        "A10": (9.041, 3.894, "二次", "低温响应接近0，高温快速上升；二次LOOCV明显改善且区间预测非负"),
        "A11": (11.712, 6.722, "低阶模型均仅粗略", "总体加速上升；二次LOOCV较好但区间内出现轻微负预测，线性低温端亦越界"),
        "A12": (9.410, 2.321, "二次", "持续加速上升；二次LOOCV显著改善"),
        "A13": (11.234, 4.105, "二次", "持续加速上升；二次LOOCV显著改善"),
        "A14": (11.035, 4.755, "二次", "持续加速上升；二次LOOCV明显改善"),
        "B1": (9.337, 2.513, "二次", "持续加速上升；二次LOOCV显著改善"),
        "B2": (12.876, 7.069, "二次", "持续上升且高温段加速；二次LOOCV改善"),
        "B3": (6.744, 3.054, "二次（谨慎）", "持续加速上升；二次LOOCV改善，但低温段拟合接近0边界"),
        "B4": (10.181, 5.871, "二次", "持续加速上升；二次LOOCV改善"),
        "B5": (12.207, 6.211, "二次", "持续加速上升；二次LOOCV改善"),
        "B6": (13.773, 7.948, "二次", "持续上升，高温段增幅扩大；二次LOOCV改善"),
        "B7": (15.620, 5.171, "二次", "持续加速上升；二次LOOCV显著改善"),
    },
    "S_C4": {
        "A1": (5.215, 6.930, "线性（总体）", "总体上升，但325°C实测最高后回落；二次LOOCV变差，局部回落直接报告"),
        "A2": (6.697, 3.918, "二次", "低温小幅回落后加速上升，二次LOOCV明显改善"),
        "A3": (9.439, 11.727, "线性（总体）", "总体上升至400°C后450°C回落；二次LOOCV变差，端部回落直接报告"),
        "A4": (5.932, 7.852, "线性（总体）", "低温略降后总体上升；二次LOOCV变差"),
        "A5": (5.754, 5.143, "线性", "持续上升；二次LOOCV仅小幅改善，优先简洁模型"),
        "A6": (12.499, 13.752, "低阶模型均仅粗略", "总体上升且400°C跃升明显；二次虽提高训练拟合但LOOCV更差"),
        "A7": (5.524, 0.906, "二次", "随温度升高增幅扩大；二次LOOCV显著改善"),
        "A8": (3.640, 0.932, "二次", "持续上升且呈明显加速；二次LOOCV显著改善"),
        "A9": (1.601, 4.689, "线性", "持续上升且近似线性；线性LOOCV显著更低"),
        "A10": (3.643, 2.152, "二次", "275°C小幅回落后加速上升；二次LOOCV改善"),
        "A11": (0.902, 0.256, "二次", "持续上升且曲率明显；二次LOOCV显著改善"),
        "A12": (4.278, 1.425, "二次", "持续加速上升；二次LOOCV显著改善"),
        "A13": (2.602, 5.691, "线性", "总体持续上升；线性LOOCV明显更低"),
        "A14": (4.647, 0.422, "二次", "持续加速上升；二次LOOCV显著改善"),
        "B1": (4.399, 3.341, "二次", "持续上升并有一定加速；二次LOOCV较低"),
        "B2": (4.726, 3.035, "二次", "持续上升且有曲率；二次LOOCV改善"),
        "B3": (2.398, 1.633, "二次", "总体上升；二次LOOCV改善"),
        "B4": (4.583, 3.061, "二次", "300°C局部下降后上升；二次LOOCV改善"),
        "B5": (3.108, 0.860, "二次", "持续上升且二次LOOCV显著改善"),
        "B6": (2.778, 7.145, "线性", "总体持续上升；二次LOOCV明显变差"),
        "B7": (2.309, 2.262, "线性", "持续上升且近似线性；两者LOOCV几乎相同，优先线性"),
    },
}

FROZEN_RECOMMENDED = {
    "X_EtOH": {
        "A1": (300, "二次", 12.6932, 16.6595, 6.3616, 0.9797, 5.292),
        "A2": (300, "线性", 36.9965, 33.1479, None, 0.9900, 3.970),
        "A3": (350, "线性（总体）", 50.9646, 20.9782, None, 0.9643, 8.693),
        "A4": (325, "线性", 44.4855, 29.0856, None, 0.9950, 3.263),
        "A5": (325, "二次", 26.9427, 20.3931, 7.9895, 0.9940, 4.332),
        "A6": (325, "线性（总体）", 43.1658, 25.0767, None, 0.9674, 9.080),
        "A7": (325, "线性", 48.4390, 18.8768, None, 0.9988, 1.401),
        "A8": (325, "二次", 21.3221, 16.8308, 4.3773, 0.9990, 2.625),
        "A9": (325, "二次", 7.9172, 12.2447, 6.1056, 0.9903, 6.908),
        "A10": (325, "二次", 4.5415, 9.0158, 4.4902, 0.9940, 3.894),
        "A11": (325, "低阶模型均仅粗略", None, None, None, None, None),
        "A12": (325, "二次", 12.3726, 14.1326, 4.7578, 0.9991, 2.321),
        "A13": (325, "二次", 8.2405, 12.4809, 5.6139, 0.9965, 4.105),
        "A14": (325, "二次", 15.9136, 16.6078, 5.4445, 0.9972, 4.755),
        "B1": (325, "二次", 12.0008, 13.8111, 4.7103, 0.9989, 2.513),
        "B2": (325, "二次", 10.0884, 13.4178, 6.2812, 0.9913, 7.069),
        "B3": (325, "二次（谨慎）", 3.0507, 6.5656, 3.4693, 0.9915, 3.054),
        "B4": (325, "二次", 5.5665, 10.3879, 5.1415, 0.9870, 5.871),
        "B5": (325, "二次", 9.7412, 13.5798, 6.2549, 0.9914, 6.211),
        "B6": (325, "二次", 17.6707, 19.1857, 7.0324, 0.9902, 7.948),
        "B7": (325, "二次", 18.8690, 20.9857, 8.1952, 0.9966, 5.171),
    },
    "S_C4": {
        "A1": (300, "线性（总体）", 43.0660, 7.7180, None, 0.7869, 5.215),
        "A2": (300, "二次", 21.0426, 11.0800, 7.7829, 0.9803, 3.918),
        "A3": (350, "线性（总体）", 32.2243, 13.0599, None, 0.9128, 9.439),
        "A4": (325, "线性（总体）", 21.2419, 11.3311, None, 0.9173, 5.932),
        "A5": (325, "线性", 16.8426, 11.4854, None, 0.9401, 5.754),
        "A6": (325, "低阶模型均仅粗略", None, None, None, None, None),
        "A7": (325, "二次", 12.9954, 9.2450, 2.8847, 0.9997, 0.906),
        "A8": (325, "二次", 19.2245, 12.0487, 1.8677, 0.9995, 0.932),
        "A9": (325, "线性", 23.3900, 12.6900, None, 0.9948, 1.601),
        "A10": (325, "二次", 2.3290, 2.5234, 1.7464, 0.9785, 2.152),
        "A11": (325, "二次", 3.0064, 2.5790, 0.4578, 0.9994, 0.256),
        "A12": (325, "二次", 16.1395, 10.1666, 2.2549, 0.9993, 1.425),
        "A13": (325, "线性", 17.0117, 8.1386, None, 0.9768, 2.602),
        "A14": (325, "二次", 6.6883, 6.7977, 2.4227, 0.9995, 0.422),
        "B1": (325, "二次", 18.3754, 11.9053, 2.3213, 0.9972, 3.341),
        "B2": (325, "二次", 15.2724, 12.1206, 2.4814, 0.9977, 3.035),
        "B3": (325, "二次", 9.5689, 6.0089, 1.1943, 0.9763, 1.633),
        "B4": (325, "二次", 8.5439, 5.1163, 2.5038, 0.9737, 3.061),
        "B5": (325, "二次", 11.2839, 7.3089, 1.6243, 0.9982, 0.860),
        "B6": (325, "线性", 16.0874, 9.5146, None, 0.9646, 2.778),
        "B7": (325, "线性", 19.4854, 11.6826, None, 0.9888, 2.309),
    },
}

FROZEN_TIME_TREND = {"intercept": 42.6709, "slope": -0.05276, "r2": 0.9329, "loo_rmse": 2.025}


@dataclass(frozen=True)
class Fit:
    group: str
    response: str
    degree: int
    tc_c: float
    beta0: float
    beta1: float
    beta2: float | None
    r2: float
    rmse_loo: float
    range_min: float
    range_max: float


def load_attachment1(path: Path) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name=0)
    selected = raw.iloc[:, [0, 2, 3, 5]].copy()
    selected.columns = ["group", "temperature_c", "X_EtOH", "S_C4"]
    selected["group"] = selected["group"].ffill()
    selected = selected.dropna(subset=["group", "temperature_c", "X_EtOH", "S_C4"])
    selected["group"] = selected["group"].astype(str).str.strip()
    for column in ["temperature_c", "X_EtOH", "S_C4"]:
        selected[column] = pd.to_numeric(selected[column], errors="raise")
    return selected.sort_values(["group", "temperature_c"], key=lambda s: s.map({v: i for i, v in enumerate(COMBINATIONS)}) if s.name == "group" else s).reset_index(drop=True)


def load_attachment2(path: Path) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name=0, header=None)
    selected = raw.iloc[3:, [0, 1, 3, 5, 4, 6]].copy()
    selected.columns = ["time_min", "X_EtOH", "S_C4", "S_C4_12_alcohol", "S_acetaldehyde", "S_methyl_benzaldehyde_alcohol"]
    selected = selected.dropna(subset=["time_min", "X_EtOH", "S_C4"])
    for column in selected.columns:
        selected[column] = pd.to_numeric(selected[column], errors="raise")
    selected = selected.sort_values("time_min").reset_index(drop=True)
    selected["Y_C4"] = selected["X_EtOH"] * selected["S_C4"] / 100.0
    selected["delta_X_per_min_next"] = selected["X_EtOH"].diff().shift(-1) / selected["time_min"].diff().shift(-1)
    selected["interval_end_min"] = selected["time_min"].shift(-1)
    return selected


def fit_polynomial(group: str, response: str, frame: pd.DataFrame, degree: int) -> Fit:
    x = frame["temperature_c"].to_numpy(dtype=float)
    y = frame[response].to_numpy(dtype=float)
    tc = (x.min() + x.max()) / 2.0
    u = (x - tc) / 50.0
    design = np.column_stack([u**power for power in range(degree + 1)])
    beta = np.linalg.lstsq(design, y, rcond=None)[0]
    predicted = design @ beta
    sse = float(np.sum((y - predicted) ** 2))
    sst = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - sse / sst
    loo_errors = []
    for held_out in range(len(y)):
        mask = np.arange(len(y)) != held_out
        beta_fold = np.linalg.lstsq(design[mask], y[mask], rcond=None)[0]
        loo_errors.append(y[held_out] - float(design[held_out] @ beta_fold))
    grid = np.linspace(x.min(), x.max(), 501)
    grid_u = (grid - tc) / 50.0
    grid_design = np.column_stack([grid_u**power for power in range(degree + 1)])
    grid_prediction = grid_design @ beta
    return Fit(
        group=group,
        response=response,
        degree=degree,
        tc_c=tc,
        beta0=float(beta[0]),
        beta1=float(beta[1]),
        beta2=None if degree == 1 else float(beta[2]),
        r2=r2,
        rmse_loo=float(math.sqrt(np.mean(np.square(loo_errors)))),
        range_min=float(grid_prediction.min()),
        range_max=float(grid_prediction.max()),
    )


def latex_escape(value: object) -> str:
    text = str(value)
    return text.replace("%", r"\%").replace("_", r"\_").replace("&", r"\&")


def render_latex_table(headers: list[str], rows: Iterable[Iterable[object]], label: str, caption: str, widths: str) -> str:
    rendered = [r"\begin{longtable}{" + widths + "}", rf"\caption{{{caption}}}\label{{{label}}}\\", r"\toprule"]
    rendered.append(" & ".join(headers) + r" \\")
    rendered += [r"\midrule", r"\endfirsthead", r"\toprule"]
    rendered.append(" & ".join(headers) + r" \\")
    rendered += [r"\midrule", r"\endhead"]
    for row in rows:
        rendered.append(" & ".join(latex_escape(value) for value in row) + r" \\")
    rendered += [r"\bottomrule", r"\end{longtable}", ""]
    return "\n".join(rendered)


def frozen_recommendation(response: str, group: str) -> str:
    return FROZEN_LOO[response][group][2]


def make_outputs(attachment1: pd.DataFrame, attachment2: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, list[Fit]]:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    attachment1.to_csv(PROCESSED_DIR / "q1_attachment1_temperature_records.csv", index=False, encoding="utf-8-sig")
    attachment2.to_csv(PROCESSED_DIR / "q1_attachment2_time_records.csv", index=False, encoding="utf-8-sig")

    fits: list[Fit] = []
    for group in COMBINATIONS:
        subgroup = attachment1.loc[attachment1["group"] == group]
        for response in ("X_EtOH", "S_C4"):
            for degree in (1, 2):
                fits.append(fit_polynomial(group, response, subgroup, degree))
    all_fits = pd.DataFrame(asdict(fit) for fit in fits)
    all_fits.to_csv(TABLE_DIR / "q1_all_candidate_fits.csv", index=False, encoding="utf-8-sig", float_format="%.10f")

    comparison_rows = []
    recommended_rows = []
    for response in ("X_EtOH", "S_C4"):
        display_name = "乙醇转化率 $X_{\\mathrm{EtOH}}$" if response == "X_EtOH" else "$\\mathrm{C}_4$烯烃选择性 $S_{\\mathrm{C4}}$"
        for group in COMBINATIONS:
            linear = next(fit for fit in fits if fit.group == group and fit.response == response and fit.degree == 1)
            quadratic = next(fit for fit in fits if fit.group == group and fit.response == response and fit.degree == 2)
            loo1, loo2, recommendation, basis = FROZEN_LOO[response][group]
            comparison_rows.append({
                "response": response, "group": group, "linear_loo": linear.rmse_loo, "quadratic_loo": quadratic.rmse_loo,
                "frozen_linear_loo": loo1, "frozen_quadratic_loo": loo2, "recommendation": recommendation, "basis": basis,
            })
            tc, rec, *frozen_values = FROZEN_RECOMMENDED[response][group]
            selected_fit = linear if rec.startswith("线性") else quadratic
            if rec == "低阶模型均仅粗略":
                recommended_rows.append({"response": response, "group": group, "tc_c": tc, "recommendation": rec, "beta0": None, "beta1": None, "beta2": None, "r2": None, "rmse_loo": None})
            else:
                recommended_rows.append({"response": response, "group": group, "tc_c": tc, "recommendation": rec, "beta0": selected_fit.beta0, "beta1": selected_fit.beta1, "beta2": selected_fit.beta2, "r2": selected_fit.r2, "rmse_loo": selected_fit.rmse_loo})
        subset = [row for row in comparison_rows if row["response"] == response]
        name = "conversion" if response == "X_EtOH" else "selectivity"
        latex_rows = [[row["group"], f"{row['linear_loo']:.3f}", f"{row['quadratic_loo']:.3f}", row["recommendation"], row["basis"]] for row in subset]
        (TABLE_DIR / f"q1_model_comparison_{name}.tex").write_text(
            render_latex_table(["组合", "一次LOOCV", "二次LOOCV", "推荐描述", "主要依据"], latex_rows, f"tab:q1-{name}-comparison", f"附件1{display_name}的冻结模型比较结果（RMSE单位：百分点）", "C{0.07\\textwidth}C{0.11\\textwidth}C{0.11\\textwidth}L{0.16\\textwidth}L{0.42\\textwidth}"), encoding="utf-8"
        )
        subset_recommended = [row for row in recommended_rows if row["response"] == response]
        latex_rows = [[row["group"], f"{row['tc_c']:.0f}", row["recommendation"], "--" if row["beta0"] is None else f"{row['beta0']:.4f}", "--" if row["beta1"] is None else f"{row['beta1']:.4f}", "--" if row["beta2"] is None else f"{row['beta2']:.4f}", "--" if row["r2"] is None else f"{row['r2']:.4f}", "--" if row["rmse_loo"] is None else f"{row['rmse_loo']:.3f}"] for row in subset_recommended]
        (TABLE_DIR / f"q1_recommended_{name}.tex").write_text(
            render_latex_table(["组合", "$T_c/\\si{\\degreeCelsius}$", "推荐", "$\\beta_0$", "$\\beta_1$", "$\\beta_2$", "$R^2$", "LOO RMSE"], latex_rows, f"tab:q1-{name}-recommended", f"附件1{display_name}的冻结推荐经验模型系数", "C{0.06\\textwidth}C{0.10\\textwidth}L{0.15\\textwidth}C{0.10\\textwidth}C{0.10\\textwidth}C{0.10\\textwidth}C{0.08\\textwidth}C{0.11\\textwidth}"), encoding="utf-8"
        )

    comparison = pd.DataFrame(comparison_rows)
    recommended = pd.DataFrame(recommended_rows)
    comparison.to_csv(TABLE_DIR / "q1_model_comparison.csv", index=False, encoding="utf-8-sig", float_format="%.10f")
    recommended.to_csv(TABLE_DIR / "q1_recommended_models.csv", index=False, encoding="utf-8-sig", float_format="%.10f")

    attachment2_latex = []
    for _, row in attachment2.iterrows():
        rate = "--" if pd.isna(row["delta_X_per_min_next"]) else f"{row['delta_X_per_min_next']:.5f}"
        interval = "末次观测" if pd.isna(row["interval_end_min"]) else f"{int(row['time_min'])}--{int(row['interval_end_min'])} min"
        attachment2_latex.append([f"{row['time_min']:.0f}", f"{row['X_EtOH']:.4f}", f"{row['S_C4']:.2f}", f"{row['Y_C4']:.4f}", rate, interval])
    (TABLE_DIR / "q1_time_stability.tex").write_text(
        render_latex_table(["$t$/min", "$X_{\\mathrm{EtOH}}$/\\%", "$S_{\\mathrm{C4}}$/\\%", "$Y_{\\mathrm{C4}}$/\\%", "下一时段$\\Delta X/\\Delta t$", "说明"], attachment2_latex, "tab:q1-time-stability", "附件2的冻结时间序列派生结果", "C{0.10\\textwidth}C{0.13\\textwidth}C{0.13\\textwidth}C{0.13\\textwidth}C{0.22\\textwidth}C{0.19\\textwidth}"), encoding="utf-8"
    )
    attachment2.to_csv(TABLE_DIR / "q1_time_stability.csv", index=False, encoding="utf-8-sig", float_format="%.10f")
    return comparison, recommended, fits


def close(actual: float, expected: float, tolerance: float) -> bool:
    return abs(actual - expected) <= tolerance


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def validate(comparison: pd.DataFrame, recommended: pd.DataFrame, attachment2: pd.DataFrame) -> dict:
    discrepancies: list[dict[str, object]] = []
    for response in ("X_EtOH", "S_C4"):
        for group in COMBINATIONS:
            row = comparison.query("response == @response and group == @group").iloc[0]
            expected_linear, expected_quadratic, _, _ = FROZEN_LOO[response][group]
            for field, actual, expected in (("linear_loo", row.linear_loo, expected_linear), ("quadratic_loo", row.quadratic_loo, expected_quadratic)):
                if not close(float(actual), expected, 0.00051):
                    discrepancies.append({"scope": f"{response}/{group}", "field": field, "frozen": expected, "reproduced": float(actual), "tolerance": 0.00051})
            frozen = FROZEN_RECOMMENDED[response][group]
            actual = recommended.query("response == @response and group == @group").iloc[0]
            for field, expected, tolerance in zip(("tc_c", "beta0", "beta1", "beta2", "r2", "rmse_loo"), (frozen[0], frozen[2], frozen[3], frozen[4], frozen[5], frozen[6]), (0.0, 0.000051, 0.000051, 0.000051, 0.000051, 0.00051)):
                value = actual[field]
                if expected is None:
                    if not pd.isna(value):
                        discrepancies.append({"scope": f"{response}/{group}", "field": field, "frozen": None, "reproduced": float(value), "tolerance": tolerance})
                elif not close(float(value), float(expected), tolerance):
                    discrepancies.append({"scope": f"{response}/{group}", "field": field, "frozen": expected, "reproduced": float(value), "tolerance": tolerance})
    time_fit = np.linalg.lstsq(np.column_stack([np.ones(len(attachment2)), attachment2["time_min"].to_numpy()]), attachment2["X_EtOH"].to_numpy(), rcond=None)[0]
    predicted = time_fit[0] + time_fit[1] * attachment2["time_min"].to_numpy()
    r2 = 1 - np.sum((attachment2["X_EtOH"] - predicted) ** 2) / np.sum((attachment2["X_EtOH"] - attachment2["X_EtOH"].mean()) ** 2)
    errors = []
    for index in range(len(attachment2)):
        mask = np.arange(len(attachment2)) != index
        x = attachment2.loc[mask, "time_min"].to_numpy()
        y = attachment2.loc[mask, "X_EtOH"].to_numpy()
        beta = np.linalg.lstsq(np.column_stack([np.ones(len(x)), x]), y, rcond=None)[0]
        errors.append(float(attachment2.loc[index, "X_EtOH"] - (beta[0] + beta[1] * attachment2.loc[index, "time_min"])))
    time_actual = {"intercept": float(time_fit[0]), "slope": float(time_fit[1]), "r2": float(r2), "loo_rmse": float(math.sqrt(np.mean(np.square(errors))))}
    for field, expected in FROZEN_TIME_TREND.items():
        tolerance = 0.000051 if field != "loo_rmse" else 0.00051
        if not close(time_actual[field], expected, tolerance):
            discrepancies.append({"scope": "attachment2/X_EtOH_time_trend", "field": field, "frozen": expected, "reproduced": time_actual[field], "tolerance": tolerance})
    return {"status": "PASS" if not discrepancies else "DISCREPANCY", "discrepancies": discrepancies, "attachment2_linear_trend": time_actual}


def write_validation_report(validation: dict) -> None:
    payload = json.dumps(validation, ensure_ascii=False, indent=2)
    (LOG_DIR / "q1_validation.json").write_text(payload + "\n", encoding="utf-8")
    lines = ["# 问题一冻结结果复现核验", "", f"状态：**{validation['status']}**", "", "核验对象：交接单附录A、附录B和附件2线性趋势。所有LOOCV均使用每组完整温度范围固定的中心化温度。", ""]
    trend = validation["attachment2_linear_trend"]
    lines.append("附件2复现线性趋势：$X_{\\mathrm{EtOH}}(t)=" + f"{trend['intercept']:.4f}{trend['slope']:+.5f}t$，$R^2={trend['r2']:.4f}$，LOOCV RMSE$={trend['loo_rmse']:.3f}$ 百分点。")
    if validation["discrepancies"]:
        lines += ["", "## Discrepancy", "", "| 范围 | 字段 | 冻结值 | 复现值 | 容差 |", "|---|---|---:|---:|---:|"]
        for item in validation["discrepancies"]:
            lines.append(f"| {item['scope']} | {item['field']} | {item['frozen']} | {item['reproduced']} | {item['tolerance']} |")
        lines += ["", "按项目约定：以上差异仅记录，不会自动替换冻结模型、参数、图片或论文结论。"]
    else:
        lines += ["", "未发现超过交接单显示精度的数值差异。"]
    (LOG_DIR / "q1_validation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    asset_manifest = {
        "purpose": "冻结交接单、原始输入和原样复用图形的完整性记录；图形不由复现脚本重绘。",
        "handoff_docx": {"path": HANDOFF_PATH.relative_to(ROOT).as_posix(), "sha256": sha256(HANDOFF_PATH)},
        "raw_inputs": {path.relative_to(ROOT).as_posix(): sha256(path) for path in (RAW_DIR / "q1_attachment1.xlsx", RAW_DIR / "q1_attachment2.xlsx")},
        "frozen_figures": {name: {"path": path.relative_to(ROOT).as_posix(), "sha256": sha256(path)} for name, path in FROZEN_FIGURES.items()},
    }
    (LOG_DIR / "q1_asset_manifest.json").write_text(json.dumps(asset_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="复现并核验问题一冻结成果")
    parser.add_argument("--strict", action="store_true", help="发现冻结结果差异时以非零状态退出")
    args = parser.parse_args()
    attachment1 = load_attachment1(RAW_DIR / "q1_attachment1.xlsx")
    attachment2 = load_attachment2(RAW_DIR / "q1_attachment2.xlsx")
    if attachment1["group"].nunique() != 21 or len(attachment1) != 114:
        raise ValueError(f"附件1数据结构不符合冻结口径：G={attachment1['group'].nunique()}，N1={len(attachment1)}")
    if len(attachment2) != 7:
        raise ValueError(f"附件2数据结构不符合冻结口径：N2={len(attachment2)}")
    comparison, recommended, _ = make_outputs(attachment1, attachment2)
    validation = validate(comparison, recommended, attachment2)
    write_validation_report(validation)
    print(f"Q1 reproduction {validation['status']}; validation: {LOG_DIR / 'q1_validation.md'}")
    return 1 if args.strict and validation["status"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
