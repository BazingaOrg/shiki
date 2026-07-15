# README 架构图实施计划

日期：2026-07-15

## 目标

为 README 增加一张可长期维护的架构图，以单一阅读路径说明 Shiki 的委派闭环，并保持 Claude Code 与 Codex 的角色、模型和配置载体映射准确。

## 执行计划

- [x] 核对 README、Claude Code 与 Codex 的编排规则和 agent 定义，确定术语、节点、关系与模型映射。
- [x] 基于 kami architecture 模板创建自包含的 `docs/assets/architecture/index.html`，主路径为“用户目标 → 主模型 → deep-reasoner → fast-worker → qa-runner → 已验证结果”，并补充 QA 失败回流。
- [x] 创建 `docs/assets/architecture/prompt.md`，按 Must preserve、Suggested additions、Visual direction、Sister boundaries 四块记录重绘约束。
- [x] 从 HTML 以 2800–3200 px 宽重新导出 `docs/assets/architecture/architecture.png`，不手工编辑或裁剪 PNG。
- [x] 在 README 的工作流程附近嵌入 PNG，避免重复已有流程说明。
- [x] 执行机械扫描与视觉检查，确认三件套一致、PNG 新于 HTML、README 路径有效。

## 结构与关键决策

- 使用左到右的任务流，节点总数限制为 6 个。
- 主模型是唯一墨蓝焦点；其余角色使用暖灰中性色。
- QA 失败回流是辅助路径，不与主路径争夺视觉层级。
- Claude Code 与 Codex 的模型及配置载体放入底部双 band，不新增流程节点。
- HTML 采用 inline CSS + SVG，不引用外部脚本、图片、字体或网络资源。

## 影响文件

- `README.md`
- `docs/assets/architecture/index.html`
- `docs/assets/architecture/architecture.png`
- `docs/assets/architecture/prompt.md`
- `docs/plans/2026-07-15-add-architecture-diagram.md`

## 风险

- 中文标签在无指定字体环境下可能发生回退，需要在 PNG 中检查字形与断行。
- QA 回流线可能与节点或正文相交，需要在 SVG 中保留足够下方净空。
- 高分辨率截图可能包含页面空白或裁切，需要固定视口并核对 PNG 实际尺寸。
- README 托管端的内容宽度不固定，图中文字必须在缩放后仍保持清晰。

## 验收命令

```bash
test -f docs/assets/architecture/index.html \
  && test -f docs/assets/architecture/architecture.png \
  && test -f docs/assets/architecture/prompt.md

rg -n '#fff|gradient|shadow|<script|<img|—' docs/assets/architecture/index.html
rg -n 'role="img"|<title>|<desc>' docs/assets/architecture/index.html
rg -n 'docs/assets/architecture/architecture.png' README.md
sips -g pixelWidth -g pixelHeight docs/assets/architecture/architecture.png
test docs/assets/architecture/architecture.png -nt docs/assets/architecture/index.html
```

## Implementation Notes

- 依据仓库中的 `CLAUDE.md`、`codex/AGENTS.md` 及两套 agent 定义完成事实核对；图外保留安装、版本、价格、并发、Git、高风险决策和简单任务例外。
- 架构源文件采用 1200 × 760 的固定画布、6 节点横向主路径和底部双 platform band；主模型为唯一墨蓝焦点，QA FAIL 以暖灰虚线回到 `fast-worker`。
- PNG 由 Google Chrome headless 直接从 HTML 导出，命令使用 `--window-size=1200,760` 与 `--force-device-scale-factor=2.5`，实际尺寸为 3000 × 1900。
- 首次同步配置路径后的默认 Chrome 会话出现一次黑块渲染异常；改用隔离的 `--user-data-dir=/tmp/shiki-kami-chrome-profile` 重新执行同一 HTML 导出链后恢复正常，未编辑或裁切 PNG。
- 已在图片查看器中按原始尺寸检查：标题、6 个节点、主路径、回流线、双 platform band 和底部说明均无裁切、遮挡或断行。
- README 以架构图替换原有纯文本流程块，保留一行图意说明，避免同一委派流程重复表达。
- 机械扫描通过：HTML 不含 `#fff`、渐变、阴影、脚本、图片引用或 em dash；SVG 具备 `role="img"`、`title` 和 `desc`；prompt 四块齐全；README 相对路径存在；PNG 时间新于 HTML。
- 与原计划无功能性偏差。独立 QA 复查结论将在后续 Review Notes 中追加。

## Review Notes

- 独立 QA 结论：PASS，无 findings。
- 检查覆盖：HTML 的自包含结构、SVG 可访问性与禁止模式；PNG 尺寸、清晰度、裁切和源文件新鲜度；README 的嵌入位置、相对路径与重复内容；`prompt.md` 四块契约及其与当前图的术语一致性；仓库内相关链接有效性。
- 未发现需要回流 `fast-worker` 的问题，因此没有追加修复或偏离原方案。
