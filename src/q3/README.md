# 问题三代码

`reproduce_q3.py` 复现附件1上的收率排序、共同温度横截面、候选因素级代理的按组合留出检验、A3 高温三点二次压力测试，以及 A2 在严格 $T<350$ ℃条件下的局部线性上确界。

运行：

```powershell
python src/q3/reproduce_q3.py --strict
```

输入为 `data/raw/q1_attachment1.xlsx`；交接材料副本为 `docs/handoffs/q3_model_handoff.docx`。表格、图形和核验日志分别写入 `outputs/q3/tables/`、`outputs/q3/figures/` 和 `outputs/q3/logs/`。
