# ═══════════════════════════════════════════════════════════════════════════
# 文件职责：文字转语音（TTS）合成器，把机器人回复文本合成为 mp3 字节流
# 所在层：digital_human 能力层（基础设施），被 api 路由调用
# 被谁调用：api/routers/digital_human_router.py 的 POST /api/chat/tts
# 实现选型：edge-tts（微软 Edge 在线语音，免申请、免密钥、中文音色自然）
# ═══════════════════════════════════════════════════════════════════════════

# logging：合成失败只记警告并降级，不让整个请求 500
import logging
# hashlib：给"音色+文本"算缓存键，同一句话不重复合成
import hashlib
# asyncio：重试之间做短暂退避
import asyncio

# edge_tts：异步 TTS 客户端，Communicate.stream() 逐块吐音频
import edge_tts

logger = logging.getLogger(__name__)

# 单次合成文本长度上限：客服话术都很短，超长多为异常/滥用，直接截断保护
MAX_TEXT_LENGTH = 1000

# 合成重试次数：edge-tts 依赖微软在线服务，实测存在"首次连接偶发失败、
# 紧接着重试即成功"的情况，不重试会让用户第一次点喇叭听不到声音
MAX_ATTEMPTS = 3

# 重试间隔（秒）：给网络抖动一点恢复时间，又不至于让用户明显等待
RETRY_DELAY_SECONDS = 0.4

# 进程内缓存上限（条）：客服话术重复率高，命中缓存能省掉整次网络合成
CACHE_MAX_ENTRIES = 128

# 模块级缓存：{缓存键: mp3 字节}；dict 保持插入顺序，便于按 FIFO 淘汰
_audio_cache: dict[str, bytes] = {}


def _cache_key(text: str, voice: str) -> str:
    """缓存键 = 音色 + 文本的 sha256；用 \x00 分隔避免拼接歧义。"""
    return hashlib.sha256(f"{voice}\x00{text}".encode("utf-8")).hexdigest()


async def _synthesize_once(text: str, voice: str) -> bytes | None:
    """跑一次完整的 edge-tts 合成；失败返回 None（不抛异常，交给上层决定是否重试）。"""
    try:
        communicate = edge_tts.Communicate(text, voice)
        # bytearray 累积：音频是分块推送的，逐块 extend 比反复拼 bytes 高效
        audio = bytearray()
        async for chunk in communicate.stream():
            # stream 里除了音频块还有元数据块（如 WordBoundary），只收 audio
            if chunk["type"] == "audio":
                audio.extend(chunk["data"])
    except Exception as exc:  # noqa: BLE001
        logger.warning("TTS 单次合成失败 voice=%s: %s", voice, exc)
        return None

    # 一块音频都没拿到 = 这次没合成出来
    return bytes(audio) if audio else None


async def synthesize(text: str, voice: str) -> bytes | None:
    """
    把文本合成为 mp3 字节流。

    与项目里其他外部调用保持一致：失败一律静默降级返回 None，
    由调用方决定怎么提示用户，绝不让网络异常直接把请求打成 500。
    内部带重试，抵御 edge-tts 在线服务的偶发抖动。

    :param text: 要朗读的文本（已由调用方去掉首尾空白）
    :param voice: edge-tts 音色名，如 zh-CN-XiaoxiaoNeural
    :return: mp3 字节；文本为空或多次重试仍失败时返回 None
    """
    # 空文本没有合成意义，直接返回 None
    if not text:
        return None

    # 超长文本截断，防止异常调用把一次请求拖成几十秒
    if len(text) > MAX_TEXT_LENGTH:
        text = text[:MAX_TEXT_LENGTH]

    # 先查缓存：命中就直接返回，不再走网络
    key = _cache_key(text, voice)
    cached = _audio_cache.get(key)
    if cached is not None:
        return cached

    # 带重试的合成：任一次拿到音频即成功
    data: bytes | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        data = await _synthesize_once(text, voice)
        if data is not None:
            if attempt > 1:
                logger.info("TTS 第 %d 次尝试成功 voice=%s", attempt, voice)
            break
        # 最后一次失败就不用再等了
        if attempt < MAX_ATTEMPTS:
            await asyncio.sleep(RETRY_DELAY_SECONDS)

    # 全部尝试都失败，降级返回 None
    if data is None:
        logger.warning("TTS 连续 %d 次合成失败 voice=%s", MAX_ATTEMPTS, voice)
        return None

    # 写缓存前先做容量控制：满了就淘汰最早的一半，避免内存无界增长
    if len(_audio_cache) >= CACHE_MAX_ENTRIES:
        for old_key in list(_audio_cache)[: CACHE_MAX_ENTRIES // 2]:
            _audio_cache.pop(old_key, None)
    _audio_cache[key] = data

    return data
