# 【导读】infrastructure/llm.py ｜ 基础设施层：把各家大模型统一为 BaseChatModel 客户端
# 【导读】被谁调用：Engine 引擎做推理时复用本模块的全局单例 llm
# 【导读】要点：换厂商只改 settings 配置，业务与推理代码一行都不用动

# itwwy/infrastructure/llm.py

# 教:init_chat_model 是 LangChain 提供的"一行初始化任意厂商模型"入口
from langchain.chat_models import init_chat_model
# 教:BaseChatModel 是所有聊天模型共有的抽象基类，即统一的"鸭子类型"
from langchain_core.language_models import BaseChatModel

# 教:模型名、密钥、网关等配置统一从 conf.settings 读取
from conf.config import settings

"""
如果没有 BaseChatModel，你可能需要：
为每个 AI 厂商写不同的代码（OpenAI 一套、百度一套、阿里一套...）
处理各种复杂的 API 调用细节
有了它之后：
统一标准：不管换哪个 AI 模型，代码写法都一样
简化操作：只需要关心"问什么"，不用关心"怎么问"
"""
# 教:模块级单例：文件被 import 即创建好 llm，全项目共享同一客户端
llm: BaseChatModel = init_chat_model(
    model=settings.llm_model,
    model_provider="openai",
    api_key=settings.llm_api_key,
    base_url=settings.llm_base_url,
    temperature=0
)

# 教:直接运行本文件即自测连通性；被 import 时这段不执行
if __name__ == '__main__':
    # 教:invoke 是同步调用；.content 取出模型回复的文本
    print(llm.invoke("你好").content)
