# Runtime Fitness Suite — 完整报告

**生成时间**: 2026-07-01T20:47:13.138602

## 一、Runtime Fitness Score

> ⚠️  **Runtime Capability Regression** — 分数下降 7.8%

| 指标 | 值 |
|------|-----|
| **Fitness Score** | **70.0%** |
| 上次分数 | 77.8% |
| 变化 | -7.8% |
| Provider 通过 | 7/10 |

## 二、Provider 详细结果

| Provider | 状态 | 延迟 | Failure Code |
|----------|------|------|--------------|
| glm | ✅ PASS | 1787ms | PASS |
| openrouter | ✅ PASS | 13584ms | PASS |
| nim | ✅ PASS | 30348ms | PASS |
| apiyi | ✅ PASS | 1820ms | PASS |
| sambanova | ✅ PASS | 1019ms | PASS |
| oneapi | ✅ PASS | 18366ms | PASS |
| github_models | ✅ PASS | 2502ms | PASS |
| modelscope | ❌ FAIL | 1167ms | AUTH_INVALID |
| huggingface | ❌ FAIL | 85ms | NETWORK_DNS |
| gemini | ❌ FAIL | 554ms | RATE_LIMITED |

## 三、模型验证

总模型: 9 | 通过: 3 | 失败: 6

### ⚠️  404 模型

- ❌ `openrouter:anthropic/claude-3.5-sonnet`

## 四、Failure Memory

| 指标 | 值 |
|------|-----|
| 故障种类 | 13 |
| 总发生次数 | 83 |
| 关键故障 | 8 |
| 未修复 | 13 |

### 按分类

- **认证**: 5 种
- **解析**: 2 种
- **模型**: 3 种
- **网络**: 3 种

## 五、Key Health

| 指标 | 值 |
|------|-----|
| Key 总数 | 11 |
| 平均健康度 | 35.8% |
| 总成功率 | 45.0% |
| healthy | 1 |
| degraded | 1 |
| unhealthy | 5 |
| suspended | 4 |

## 六、Provider Registry

- Provider 数: 9
- 模型总数: 9
- 已验证模型: 4

---

## 宪法原则

> **Runtime Capability Non-Regression**
>
> 任何 Runtime 在进入下一阶段演化之前，
> 必须保持不少于上一版本的 Provider 可用能力。
> 若 Runtime Fitness 下降，
> 优先恢复执行能力，
> 禁止继续新增功能。

> 文明可以每天成长，但 Runtime 不允许每天退化。