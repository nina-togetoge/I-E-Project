"""
AI 助手路由：对接火山引擎 Ark (豆包) 大模型
"""
# ====================================================================
# AI 助手路由
# ----------------------------------------------------------------------------
# 对外接口分组（前缀 /api/ai）：
#   POST /chat   多轮对话，由后端代理调用火山引擎 Ark 的 chat/completions 接口
# 前端对应：页面右下角「智能助手小创」悬浮对话窗。
# 依赖：settings 中的 ARK_BASE_URL / ARK_MODEL_ID / ARK_API_KEY；
#       本模块不落库，也不依赖任何业务 Service。
# 权限约束：仅登录用户可调用（require_login），避免未认证请求消耗大模型额度。
# 特殊规则：
#   - API Key 只在服务端使用，绝不下发给前端；
#   - 未配置 Key 时返回业务错误 500，上游调用失败返回 502，HTTP 状态仍为 200，
#     由前端按响应体 code 判断；
#   - 对话历史由前端随请求上传，后端每次拼入固定系统提示词，不保存会话。
# ====================================================================
import json
import urllib.request
import urllib.error
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.security import require_login
from app.core.response import ResponseModel, success
from app.models import SysUser

router_ai = APIRouter(prefix="/ai", tags=["AI助手"])


# 单条对话消息：只接受 user/assistant 两种角色，system 提示词由服务端统一注入，
# 防止调用方伪造 system 指令改变助手行为；content 限长 4000 字，避免超长请求拖垮上游。
class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$", description="角色: user / assistant")
    content: str = Field(..., min_length=1, max_length=4000, description="消息内容")


# 对话请求体：messages 最多 50 条（约 25 轮），限制上下文长度与 token 成本；
# temperature 取值 0~2，数值越高回答越发散，默认 0.7 兼顾稳定与自然。
class ChatRequest(BaseModel):
    messages: List[ChatMessage] = Field(..., min_length=1, max_length=50, description="对话历史")
    temperature: Optional[float] = Field(default=0.7, ge=0, le=2)


# 固定系统提示词：限定助手身份为平台客服「小创」，引导其回答申报/审核/经费/成果/比赛问题，
# 并要求不确定时坦诚告知，减少模型编造平台功能。
SYSTEM_PROMPT = (
    "你是「校园创新创业项目管理平台」的智能助手小创。"
    "你可以帮助用户解答创新创业项目申报、审核、经费、成果、比赛等相关问题，"
    "也可以提供一般的知识问答。回答要简洁、友好、实用。"
    "如果用户询问平台功能，引导其使用对应菜单；如果无法回答，坦诚告知。"
)


def _call_ark(messages: List[dict], temperature: float = 0.7) -> str:
    """调用火山引擎 Ark 接口

    入参 messages 为 OpenAI 兼容格式（含 system/user/assistant 角色），
    返回模型生成的第一条回复文本；不处理流式输出。
    异常：HTTP 错误与网络连接失败统一转为 RuntimeError，由路由层转换为业务错误码 502。
    """
    # 1. 拼接兼容 OpenAI 协议的 chat/completions 地址，携带模型 ID 与温度参数
    url = f"{settings.ARK_BASE_URL}/chat/completions"
    payload = {
        "model": settings.ARK_MODEL_ID,
        "messages": messages,
        "temperature": temperature,
    }
    # 2. 标准库 urllib 发起 POST：API Key 只放在服务端请求头，前端不可见
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.ARK_API_KEY}",
        },
        method="POST",
    )
    try:
        # 3. 读取 JSON 响应并取第一条候选回复；超时 60 秒，避免请求长期挂起
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return body["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        # 4. 上游返回 4xx/5xx（Key 失效、限流、参数错误等）时保留状态码与响应体，便于排查
        err_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"AI 接口错误 [{e.code}]: {err_body}")
    except urllib.error.URLError as e:
        # 5. 网络不可达 / DNS 失败 / 超时，转换为统一 RuntimeError
        raise RuntimeError(f"AI 接口连接失败: {e.reason}")


# --- 接口说明 ---
# POST /api/ai/chat：AI 智能助手对话。
# 谁可以调用：任意已登录用户。
# 入参：messages = 前端维护的对话历史（最多 50 条，每条 1~4000 字）；temperature 可选。
# 返回：data.reply = 模型回复文本。
# 错误码：500 表示服务端未配置 ARK_API_KEY；502 表示上游大模型调用失败；
#         均为业务响应体 code，HTTP 状态保持 200，避免前端全局拦截器误跳转登录页。
# 副作用：不写库、不发通知；仅产生一次外部大模型调用。
@router_ai.post("/chat", response_model=ResponseModel, summary="AI 对话")
def api_ai_chat(
    req: ChatRequest,
    current_user: SysUser = require_login,
):
    # 1. 未配置密钥时快速失败，提示联系管理员，避免请求打到上游再报鉴权错误
    if not settings.ARK_API_KEY:
        return ResponseModel(code=500, message="AI 服务未配置 API Key，请联系管理员")

    # 2. 服务端固定注入 system 提示词，再顺序追加前端上传的历史消息
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in req.messages:
        messages.append({"role": m.role, "content": m.content})

    try:
        # 3. 调用 Ark 接口；temperature 缺省时回退 0.7（Pydantic 默认值已保证非空）
        reply = _call_ark(messages, req.temperature or 0.7)
    except RuntimeError as e:
        # 4. 上游异常统一转为 502 业务错误，前端展示友好提示而不暴露堆栈
        return ResponseModel(code=502, message=str(e))

    return success(data={"reply": reply})
