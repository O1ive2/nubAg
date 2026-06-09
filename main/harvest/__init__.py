"""
Harvest 模块 - 信息采集层
====================================
负责为 Agent 收集外部信息：用户输入解析、网页抓取、文件读取、API 调用等。
是 Agent 感知世界的"眼睛和耳朵"。
"""

from .collector import Harvester, HarvestResult

__all__ = ["Harvester", "HarvestResult"]