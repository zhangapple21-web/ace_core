# ACE 外部目标注入最小协议（v1）

## 目的

当前 ACE 的任务全部来自自身的 `Observer / TaskCreator / file_scanner`，形成
`观察 → 怀疑 → 立项 → 验证失败 → 归档` 的自我循环。本协议提供一个**外部目标通道**：
由人类/上游系统给出明确目标，强制生成一个必须交出**物理文件**的任务。

## 协议版本

`ace.target.inject.v1`

## 输入 JSON（放入 `ops/inject_target.py` 的 `--json` 参数或 stdin）

```json
{
  "protocol": "ace.target.inject.v1",
  "title": "把 task_pool 实际状态画成时序图",
  "hypothesis": "用一份 Markdown 文档描述 task 从 pending 到 archived 的关键流转",
  "expected_output": "docs/TASK_LIFECYCLE.md",
  "success_metric": "file_exists_nonempty",
  "priority": "high",
  "domain": "document",
  "tags": ["external_target", "delivery:physical"],
  "why_now": "人工验收需要一份可审阅的生命周期说明"
}
```

### 字段约束

| 字段 | 必填 | 约束 |
|------|------|------|
| `protocol` | 是 | 必须等于 `ace.target.inject.v1` |
| `title` | 是 | 1–200 字符 |
| `hypothesis` | 否 | 默认空 |
| `expected_output` | 是 | 相对路径，必须以 `.md/.json/.py/.txt/.csv/.yaml/.yml` 结尾 |
| `success_metric` | 是 | `file_exists_nonempty` / `user_accepted` / `schema_valid_json` / `tests_pass` |
| `priority` | 否 | `low/medium/high/critical`，默认 `medium` |
| `domain` | 否 | `document/code/analysis/other`，默认 `other` |
| `tags` | 否 | 字符串数组；自动追加 `external_target` 与 `delivery:physical` |
| `why_now` | 否 | 默认 `external_target_injected` |

## 任务映射

注入脚本会把上述 JSON 转成：

```python
TaskPool.create_task(
    title=..., hypothesis=..., priority=..., tags=...,
    admission={
        "source_type": "external_target",
        "source_ref": expected_output,
        "why_now": why_now,
        "expected_result": expected_output,
        "verification_method": success_metric,
        "evidence": [],
    },
    outputs={
        "delivery": {
            "required_path": expected_output,
            "success_metric": success_metric,
            "domain": domain,
        }
    },
)
```

## 为什么任务必须交出物理文件

- `outputs.delivery.required_path` 记录了交付路径；
- `admission.verification_method` 里的 `file_exists_nonempty` / `schema_valid_json` / `tests_pass` 给 Validator 一个可执行的验收标准；
- `execution_discipline` 会在 `build_execution_discipline` 时把该 `admission` 写进 clarification，后续 verify 时必须用它做证据。

## 最小可用性

本协议刻意不新增运行时、不改 `ace_host_adapter` 的只读语义、不改 daemon 主循环。
它只补一个受限的入口脚本：`ops/inject_target.py`。

## 示例命令

```bash
python ops/inject_target.py --json '{"protocol":"ace.target.inject.v1",...}'
```
