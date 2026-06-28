#!/usr/bin/env python3
"""批量疏通 review 队列 — 清理 Runtime 瓶颈"""
import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.task import TaskPool

pool = TaskPool('task_pool')

review_tasks = pool.list_tasks(status='review', limit=20)
print(f'待处理: {len(review_tasks)} 个')
print()

results = {'approved': 0, 'rejected': 0, 'kept': 0}
for task in review_tasks:
    ev_count = len(task.evidence)
    rv_count = task.review_count
    title = task.title[:55]

    # === 重复任务直接拒绝 ===
    if task.task_id == 'RQ-20260628-002':
        pool.move_task(task.task_id, 'rejected', actor='batch_processor',
                      reason='与RQ-20260628-001重复，文件相同')
        results['rejected'] += 1
        print(f'[REJECT] {task.task_id} (重复考古报告)')
        continue

    # === 证据充分（>=5条）→ 批准 ===
    if ev_count >= 5:
        task.guardian_decision = 'experience'
        task.add_validation_note('[批量终审] 证据充分(ev=' + str(ev_count) + ')，批量批准', validator='batch_processor')
        pool.update_task(task)
        pool.move_task(task.task_id, 'approved', actor='batch_processor', task=task)
        results['approved'] += 1
        print('[APPROVE] ' + task.task_id + ' ev=' + str(ev_count) + ' rv=' + str(rv_count) + ': ' + title)
        continue

    # === 用户输入任务且无证据 → 保留active ===
    if task.creator == 'user_input' and ev_count == 0:
        task.add_validation_note('[批量处理] 无证据，暂存待后续研究', validator='batch_processor')
        pool.update_task(task)
        pool.move_task(task.task_id, 'active', actor='batch_processor', task=task)
        results['kept'] += 1
        print('[ACTIVE ] ' + task.task_id + ' (无证据，用户输入): ' + title)
        continue

    # === 其余保留review ===
    results['kept'] += 1
    print('[KEEP  ] ' + task.task_id + ' ev=' + str(ev_count) + ' rv=' + str(rv_count) + ': ' + title)

print()
print('结果: 批准=' + str(results['approved']) + ' | 拒绝=' + str(results['rejected']) + ' | 保留=' + str(results['kept']))

# 验证结果
remaining = pool.list_tasks(status='review', limit=20)
print('剩余review任务: ' + str(len(remaining)))
