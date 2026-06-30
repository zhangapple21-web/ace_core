"""
Assets Module — 基础设施资产管理模块

提供资产发现、验证、索引功能
"""

from .asset_curator import AssetCurator, Asset, ASSET_TYPES, AUTH_TYPES

__all__ = [
    "AssetCurator",
    "Asset",
    "ASSET_TYPES",
    "AUTH_TYPES",
]
