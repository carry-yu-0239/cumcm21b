# CUMCM 数学建模项目脚手架（高保真版）

该脚手架按 `carry-yu-0239/cumcm16A` 的实际工程方式抽取：保留工程协作规则、模型追溯链、数据/代码/输出分层，以及完整 LaTeX 论文编译框架；仅移除原 2016 A 题的具体题意、公式、参数和结论。

## 目录约定

- `problem/original_problem/`：新题原始题目、附件、题图，不修改原件。
- `problem/problem_notes/`：读题记录、口径、团队批注和待澄清事项。
- `data/raw/`：只读原始数据。
- `data/processed/`：由代码生成的清洗/转换数据。
- `model_cards/`：各小问经团队确认后的模型交接单。
- `src/q1/`、`src/q2/`、`src/q3/`：各小问代码；`src/common/`：共享函数。
- `outputs/q*/figures/`：程序生成图片。
- `outputs/q*/tables/`：程序生成表格与数值结果。
- `outputs/q*/logs/`：运行日志、参数记录、验证记录。
- `docs/`：结果总账、待确认事项、模型说明和决策记录。
- `paper/`：论文 LaTeX 主文件、全局设置、章节、图片和表格。

## 推荐工作顺序

1. 把题面及附件放进 `problem/original_problem/` 和 `data/raw/`。
2. 先读题，形成 `problem/problem_notes/`，不要急着写论文。
3. 将已确认的输入、输出、假设、变量、公式、参数、约束、验证方式写进 `model_cards/q*.md`。
4. 在 `src/q*/` 实现最小可复现代码，输出统一写入 `outputs/q*/`。
5. 将核验过的关键数值登记到 `docs/result_registry.md`。
6. 只有已经确认且可追溯的模型与结果才能写入 `paper/sections/`。
7. 从 `paper/` 目录运行 `latexmk -xelatex main.tex` 编译论文。

## Codex 初始化建议

Codex 第一次进入仓库时，应优先阅读：

1. `AGENTS.md`
2. `README.md`
3. `problem/original_problem/`
4. `problem/problem_notes/`
5. `model_cards/`
6. 与当前任务直接相关的 `src/`、`outputs/`、`paper/sections/`

不要把“能运行”当成“模型正确”，也不要把未确认的推演直接写成论文事实。
