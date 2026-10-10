"""
AI 助手路由：对接火山引擎 Ark (豆包) 大模型
"""
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


class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$", description="角色: user / assistant")
    content: str = Field(..., min_length=1, max_length=4000, description="消息内容")


class ChatRequest(BaseModel):
    messages: List[ChatMessage] = Field(..., min_length=1, max_length=50, description="对话历史")
    temperature: Optional[float] = Field(default=0.7, ge=0, le=2)


SYSTEM_PROMPT = (
    "你是「校园创新创业项目管理平台」的智能助手小创。"
    "你可以帮助用户解答创新创业项目申报、审核、经费、成果、比赛等相关问题，"
    "也可以提供一般的知识问答。回答要简洁、友好、实用。"
    "如果用户询问平台功能，引导其使用对应菜单；如果无法回答，坦诚告知。"
)


def _call_ark(messages: List[dict], temperature: float = 0.7) -> str:
    """调用火山引擎 Ark 接口"""
    url = f"{settings.ARK_BASE_URL}/chat/completions"
    payload = {
        "model": settings.ARK_MODEL_ID,
        "messages": messages,
        "temperature": temperature,
    }
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
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return body["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"AI 接口错误 [{e.code}]: {err_body}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"AI 接口连接失败: {e.reason}")


@router_ai.post("/chat", response_model=ResponseModel, summary="AI 对话")
def api_ai_chat(
    req: ChatRequest,
    current_user: SysUser = require_login,
):
    if not settings.ARK_API_KEY:
        return ResponseModel(code=500, message="AI 服务未配置 API Key，请联系管理员")

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in req.messages:
        messages.append({"role": m.role, "content": m.content})

    try:
        reply = _call_ark(messages, req.temperature or 0.7)
    except RuntimeError as e:
        return ResponseModel(code=502, message=str(e))

    return success(data={"reply": reply})
