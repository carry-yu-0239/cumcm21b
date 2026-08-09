# 问题一代码

`reproduce_q1.py` 是冻结交接成果的等价复现与核验脚本。它读取 `data/raw/q1_attachment1.xlsx`、`data/raw/q1_attachment2.xlsx`，输出处理数据、候选低阶拟合、冻结推荐表、附件2派生表及核验日志。

```powershell
python src/q1/reproduce_q1.py --strict
```

脚本不会重绘 `paper/figures/q1_handoff/` 的三张冻结图片，也不执行跨组合排名、因素归因或优化。
