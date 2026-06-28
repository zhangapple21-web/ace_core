#!/usr/bin/env python3
"""
为已有碎片索引补充主题标签

扫描所有已有条目，自动提取主题标签并保存。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.fragment_index import FragmentIndex


def main():
    fi = FragmentIndex('02_FRAGMENT_INDEX')
    
    updated = 0
    for path_str, rec in list(fi.index.items()):
        path = Path(path_str)
        if not path.exists():
            continue
        
        topics = fi._extract_topics(path)
        if topics:
            existing = set(rec.get("topics", []))
            if not existing.issuperset(topics):
                rec["topics"] = list(existing.union(topics))
                updated += 1
    
    if updated > 0:
        fi._save()
        print(f"已为 {updated} 个条目补充主题标签")
    else:
        print("所有条目已有完整主题标签")
    
    # 显示主题统计
    print()
    print("【主题统计】")
    topics = fi.get_all_topics()
    for t, c in sorted(topics.items(), key=lambda x: -x[1]):
        print(f"  {t}: {c} 个文件")


if __name__ == "__main__":
    main()
