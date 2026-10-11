# ══════════════════════════════════════════════════════════════════════════
# 文件职责：数字人相关 HTTP 接口——凭证下发 + 语音播报（TTS）
# 所在层：API 层路由（FastAPI 的 APIRouter）
# 被谁调用：api/app.py 通过 app.include_router(router) 挂载
# 说明：本文件是"数字人功能"在后端唯一的落点，业务后端（对话/流程）一行未改
# ══════════════════════════════════════════════════════════════════════════

# APIRouter 组织路由；HTTPException 抛标准错误响应
from fastapi import APIRouter, HTTPException
# Response：TTS 要返回的是二进制音频流，不是 JSON，必须用原生响应
from fastapi.responses import Response
# BaseModel：声明 TTS 请求体结构，FastAPI 自动校验
from pydantic import BaseModel

# settings：数字人凭证与 TTS 音色都从后端 .env 读取
from conf.config import settings
# tts 模块：真正做语音合成的执行者（edge-tts 封装）
from digital_human import tts

# 创建路由对象
router = APIRouter()


# TTS 请求体：前端只传要朗读的文本，音色一般走服务端默认
class TTSRequest(BaseModel):
    # 要合成的文本（前端传的是机器人回复正文）
    text: str
    # 可选音色覆盖：不传就用 .env 里的 TTS_VOICE
    voice: str | None = None


@router.get("/api/digital-human/credentials")
async def get_digital_human_credentials() -> dict:
    """
    下发数字人（魔珐星云）SDK 初始化凭证。

    安全要点：AppSecret 等同应用密码，只存在于后端 .env；
    前端每次初始化数字人时动态获取，源码里不出现任何明文密钥。
    """
    # 未配置凭证时明确告知，而不是把空串发给前端让 SDK 报 10003 这种难懂的错
    if not settings.digital_human_app_id or not settings.digital_human_app_secret:
        raise HTTPException(
            status_code=503,
            detail="数字人凭证未配置，请在后端 .env 中设置 DIGITAL_HUMAN_APP_ID / DIGITAL_HUMAN_APP_SECRET",
        )

    # 字段名与前端 SDK 初始化参数一一对应，前端拿到即可直接 new XmovAvatar
    return {
        "app_id": settings.digital_human_app_id,
        "app_secret": settings.digital_human_app_secret,
        "gateway_server": settings.digital_human_gateway_server,
    }


# 路径沿用前端既有约定（App.vue 的「语音播报」按钮已经在调 /api/chat/tts）
@router.post("/api/chat/tts")
async def text_to_speech(payload: TTSRequest) -> Response:
    """
    把文本合成为 mp3 返回给前端播放。

    前端期望拿到音频二进制（response.blob() → Audio），所以这里返回 Response
    而不是 JSON；失败时用 503 明确表达"语音服务暂时不可用"。
    """
    # 文本去空白：全空白直接拒绝，省掉一次无意义的合成
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text 不能为空")

    # 音色优先取请求指定，其次回落到 .env 默认值
    voice = payload.voice or settings.tts_voice

    # 合成（内部已做失败降级：拿不到音频返回 None，不抛异常）
    audio = await tts.synthesize(text, voice)
    if audio is None:
        raise HTTPException(status_code=503, detail="语音合成失败，请稍后重试")

    # media_type 必须是 audio/mpeg，浏览器才会把它当音频交给 <audio>/Audio 播放
    return Response(content=audio, media_type="audio/mpeg")
