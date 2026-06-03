"""离线 LLM Provider —— 规则化模板实现,无需密钥/算力。

用于 demo 与测试:对 Agent 用到的几类"表达"任务给出确定性模板输出。
生产环境替换为真实国产大模型时,只需实现同样的 complete() 接口。
"""

from __future__ import annotations


class OfflineProvider:
    """离线规则化 Provider。

    complete() 按提示词中的任务标记返回模板文本。这样 Agent 的"表达"环节
    在无网络/无密钥时也能产出可读结果,演示闭环完整。
    """

    name = "offline-stub"

    def complete(self, prompt: str, *, system: str = "", max_tokens: int = 1024) -> str:
        p = prompt.lower()
        if "技术方案" in prompt or "section:tech-proposal" in p:
            return (
                "本公司针对本项目所需阀门,依据 GB/T、API 等标准组织设计、制造与检验。"
                "产品选用与工况相匹配的阀体与密封材质,经水压强度、密封及(必要时)高温试验合格后出厂,"
                "并提供完整质量证明文件与质保服务。"
            )
        if "话术" in prompt or "suggestion" in p:
            return "就该偏离项,我方可提供替代型号或就工况与招标方进一步澄清,确保实质性响应。"
        return "(离线模式)已生成模板化文本,接入大模型后此处为模型润色内容。"
