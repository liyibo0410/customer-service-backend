# ══════════════════════════════════════════════════════════════════════════
# 文件职责：用 pydantic-settings 从 .env 读取并校验全局配置
# 所在层：配置层（conf 包，属基础设施范畴）
# 被谁调用：main.py、api 层等 from conf.config import settings 使用
# ══════════════════════════════════════════════════════════════════════════
# itwwy/conf/config.py

# Path：跨平台路径处理，用来定位项目根目录下的 .env 文件
from pathlib import Path

# BaseSettings 让字段自动读环境变量；SettingsConfigDict 配置读取方式
from pydantic_settings import BaseSettings, SettingsConfigDict

# ENV_FILE：.env 的绝对路径（当前文件上一级目录即项目根目录）
ENV_FILE = Path(__file__).resolve().parents[1] / ".env"

# 配置文件的 模型类  有校验功能
# Settings 继承 BaseSettings：每个带注解的类属性即一项配置，自动校验
class Settings(BaseSettings):

    # LLM
    # 大模型 API 密钥，对应 .env 中的 LLM_API_KEY
    llm_api_key: str
    # 大模型名称，请求时决定调用哪个模型
    llm_model: str
    # 大模型服务地址（兼容 OpenAI 协议的 base_url）
    llm_base_url: str

    # LLM 调用治理：超时 / 重试 / 重试间隔（统一在 infrastructure/llm.py 的包装函数里生效）
    # 单次 LLM 调用超时秒数：超时即判定本次失败，交由调用方走降级
    llm_timeout_seconds: float = 30.0
    # 单次 LLM 调用的最大尝试次数（含首次）
    llm_max_attempts: int = 3
    # 两次尝试之间的等待秒数，给网络抖动一点恢复时间
    llm_retry_delay_seconds: float = 0.5

    # 数据库
    # 数据库连接串：驱动+账号+地址+库名，用于创建异步连接池
    database_url: str

    # 是否打印 SQL：仅本地调试时置 true；生产保持 false，否则每次查询都会刷大量 SQL 日志
    database_echo: bool = False

    # 商城 API
    # 商城系统接口根地址：查订单/商品等数据时调用
    commerce_api_base_url: str

    # 服务器
    # 服务监听地址，如 0.0.0.0 表示对外网开放
    app_host: str
    # 服务监听端口，声明 int 会自动做类型转换与校验
    app_port: int

    # 数字人（魔珐星云）
    # AppSecret 等同应用密码，只允许存在后端 .env，绝不能下发到前端源码里
    # 给空串默认值：未申请魔珐账号时服务仍可正常启动，只是数字人接口返回"未配置"
    digital_human_app_id: str = ""
    digital_human_app_secret: str = ""
    # 魔珐星云网关地址，文档指定值，无特殊需求不要改
    digital_human_gateway_server: str = "https://nebula-agent.xingyun3d.com/user/v1/ttsa/session"

    # 语音播报（TTS）
    # 音色：听澜是女性客服形象，默认用晓晓；可选 zh-CN-XiaoyiNeural / zh-CN-YunxiNeural 等
    tts_voice: str = "zh-CN-XiaoxiaoNeural"

    # 从.env文件中读取配置信息
    # 如果读取真实环境变量，则不写这句话
    # extra="ignore" 表示忽略.env中有，这里没有的配置项，不会报错
    # env_file_encoding：如果遇到乱码问题则添加这个属性解决
    # 注意这里对象名必须叫model_config ，而且必须定义，否则配置会被回收
    # 继承 BaseSettings 里面也提供一系列 默认 的属性
    # 配置元数据：指定 .env 路径、忽略多余键、utf-8 解码
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore", env_file_encoding="utf-8")

# 实例化全局唯一配置对象：import 即解析 .env，全项目共享
settings = Settings()


if __name__ == '__main__':
    # 直接运行本文件时做自测：验证配置能否正常读取

    from conf.config import settings

    # 打印一项配置，肉眼确认 .env 解析结果
    print(settings.llm_base_url)