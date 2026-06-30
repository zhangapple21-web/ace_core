"""
UnidbgPool — Unidbg 实例复用池

设计原则：
  - 复用已加载的 .so 库实例，避免重复加载开销
  - 池大小可配置，默认 3
  - 超时控制和异常恢复
  - 骨架实现：目前是模拟层，真实 Unidbg 接入后替换内部实现

（这是结构资产，不是模型资产。
 真实的 Unidbg 执行引擎只是可替换节点。）
"""

import time
import logging
import threading
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class UnidbgInstance:
    """Unidbg 实例封装"""
    instance_id: str
    so_path: str
    loaded: bool = False
    last_used: float = 0.0
    use_count: int = 0
    error_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def is_healthy(self, max_errors: int = 5) -> bool:
        return self.loaded and self.error_count < max_errors


class UnidbgPool:
    """
    Unidbg 实例池

    功能：
      - 按 so_path 分组管理实例
      - 池大小限制，LRU 淘汰
      - 超时自动回收
      - 异常实例自动重建
    """

    def __init__(
        self,
        pool_size: int = 3,
        idle_timeout: int = 300,
        max_errors_per_instance: int = 5,
    ):
        self.pool_size = pool_size
        self.idle_timeout = idle_timeout
        self.max_errors_per_instance = max_errors_per_instance

        self._pools: Dict[str, List[UnidbgInstance]] = {}
        self._lock = threading.Lock()
        self._total_created = 0
        self._total_destroyed = 0
        self._hits = 0
        self._misses = 0

    def acquire(self, so_path: str, timeout: float = 5.0) -> Optional[UnidbgInstance]:
        """
        获取一个可用的 Unidbg 实例

        Args:
            so_path: .so 库路径
            timeout: 超时时间（秒）

        Returns:
            UnidbgInstance 或 None
        """
        with self._lock:
            self._cleanup_idle()

            pool = self._pools.setdefault(so_path, [])

            # 找一个健康的实例
            for inst in pool:
                if inst.is_healthy(self.max_errors_per_instance):
                    inst.last_used = time.time()
                    inst.use_count += 1
                    self._hits += 1
                    logger.debug(f"[UnidbgPool] 复用实例 {inst.instance_id} for {so_path}")
                    return inst

            # 没有可用实例，创建新的
            if len(pool) < self.pool_size:
                inst = self._create_instance(so_path)
                pool.append(inst)
                self._misses += 1
                logger.debug(f"[UnidbgPool] 创建新实例 {inst.instance_id} for {so_path}")
                return inst

            # 池满了，淘汰最久未使用的
            if pool:
                pool.sort(key=lambda x: x.last_used)
                oldest = pool.pop(0)
                self._destroy_instance(oldest)
                inst = self._create_instance(so_path)
                pool.append(inst)
                self._misses += 1
                logger.debug(f"[UnidbgPool] 淘汰 {oldest.instance_id}，创建 {inst.instance_id}")
                return inst

            return None

    def release(self, instance: UnidbgInstance, success: bool = True) -> None:
        """
        释放实例回池

        Args:
            instance: Unidbg 实例
            success: 本次调用是否成功（失败则累加 error_count）
        """
        with self._lock:
            if not success:
                instance.error_count += 1
                logger.warning(
                    f"[UnidbgPool] 实例 {instance.instance_id} 错误次数: "
                    f"{instance.error_count}/{self.max_errors_per_instance}"
                )

            # 如果错误太多，销毁
            if instance.error_count >= self.max_errors_per_instance:
                self._destroy_instance_from_pool(instance)
                logger.warning(f"[UnidbgPool] 实例 {instance.instance_id} 错误过多，已销毁")

    def call_function(
        self,
        so_path: str,
        function_name: str,
        args: Optional[List] = None,
        timeout: float = 5.0,
    ) -> Dict[str, Any]:
        """
        调用 so 中的函数（骨架实现）

        Args:
            so_path: .so 库路径
            function_name: 函数名
            args: 参数列表
            timeout: 超时时间

        Returns:
            {success, result, error, instance_id}
        """
        inst = self.acquire(so_path, timeout)
        if not inst:
            return {
                "success": False,
                "result": None,
                "error": "no available instance",
                "instance_id": "",
            }

        success = False
        try:
            # TODO: 真实 Unidbg 接入后替换这里
            # 目前是骨架，返回模拟结果
            result = self._simulate_call(inst, function_name, args)
            success = True
            return {
                "success": True,
                "result": result,
                "error": None,
                "instance_id": inst.instance_id,
            }
        except Exception as e:
            logger.error(f"[UnidbgPool] 调用失败: {e}")
            return {
                "success": False,
                "result": None,
                "error": str(e),
                "instance_id": inst.instance_id,
            }
        finally:
            self.release(inst, success)

    def _create_instance(self, so_path: str) -> UnidbgInstance:
        """创建新的 Unidbg 实例（骨架）"""
        self._total_created += 1
        inst = UnidbgInstance(
            instance_id=f"unidbg-{self._total_created:04d}",
            so_path=so_path,
            loaded=True,  # 骨架：假装加载成功
            last_used=time.time(),
        )
        logger.info(f"[UnidbgPool] 创建实例: {inst.instance_id} ({so_path})")
        return inst

    def _destroy_instance(self, inst: UnidbgInstance) -> None:
        """销毁实例"""
        self._total_destroyed += 1
        inst.loaded = False
        logger.info(f"[UnidbgPool] 销毁实例: {inst.instance_id}")

    def _destroy_instance_from_pool(self, target: UnidbgInstance) -> None:
        """从池中移除并销毁实例"""
        for so_path, pool in self._pools.items():
            for i, inst in enumerate(pool):
                if inst.instance_id == target.instance_id:
                    pool.pop(i)
                    self._destroy_instance(inst)
                    return

    def _cleanup_idle(self) -> None:
        """清理超时未使用的实例"""
        now = time.time()
        for so_path, pool in self._pools.items():
            to_remove = []
            for inst in pool:
                if now - inst.last_used > self.idle_timeout:
                    to_remove.append(inst)
            for inst in to_remove:
                pool.remove(inst)
                self._destroy_instance(inst)

    def _simulate_call(
        self, inst: UnidbgInstance, function_name: str, args: Optional[List]
    ) -> Any:
        """模拟函数调用（骨架用）"""
        return {
            "simulated": True,
            "function": function_name,
            "args": args or [],
            "instance": inst.instance_id,
            "timestamp": datetime.now().isoformat(),
        }

    def get_stats(self) -> Dict[str, Any]:
        """获取池统计信息"""
        with self._lock:
            total_instances = sum(len(pool) for pool in self._pools.values())
            total_requests = self._hits + self._misses
            hit_rate = self._hits / total_requests if total_requests > 0 else 0.0

            pool_details = {}
            for so_path, pool in self._pools.items():
                pool_details[so_path] = {
                    "size": len(pool),
                    "instances": [
                        {
                            "id": inst.instance_id,
                            "loaded": inst.loaded,
                            "use_count": inst.use_count,
                            "error_count": inst.error_count,
                            "idle_seconds": int(time.time() - inst.last_used),
                        }
                        for inst in pool
                    ],
                }

            return {
                "pool_size_limit": self.pool_size,
                "total_instances": total_instances,
                "total_created": self._total_created,
                "total_destroyed": self._total_destroyed,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": hit_rate,
                "idle_timeout": self.idle_timeout,
                "pools": pool_details,
            }

    def shutdown(self) -> None:
        """关闭池，销毁所有实例"""
        with self._lock:
            for so_path, pool in self._pools.items():
                for inst in pool:
                    self._destroy_instance(inst)
            self._pools.clear()
            logger.info("[UnidbgPool] 池已关闭")
