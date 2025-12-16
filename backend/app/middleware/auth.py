# backend/app/middleware/auth.py

import os
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
import httpx
from dotenv import load_dotenv

# 确保可从 .env 读取到 JWT_SECRET
load_dotenv()

security = HTTPBearer(auto_error=True)


def _get_jwt_secret() -> str:
    # 兼容多种环境变量命名，优先 JWT_SECRET
    secret = os.environ.get("JWT_SECRET") or os.environ.get("SUPABASE_JWT_SECRET")
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="服务器未配置 JWT_SECRET（或 SUPABASE_JWT_SECRET）",
        )
    return secret


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """
    校验传入的 Bearer Token 并返回用户标识（user_id）。

    - 使用 HS256 算法
    - Secret 从环境变量 JWT_SECRET / SUPABASE_JWT_SECRET 读取
    - 放宽校验以兼容 Supabase：不校验 aud，允许 60s 时钟偏移
    - 失败抛出 401
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少认证信息",
        )

    token = credentials.credentials
    secret = _get_jwt_secret()

    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            options={"verify_aud": False},
            leeway=60,  # 允许 60 秒时钟偏移
        )  # type: ignore
        # 常见字段名为 "sub" 作为用户唯一标识
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的令牌：缺少 sub",
            )
        return str(user_id)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌已过期",
        )
    except jwt.InvalidSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌签名无效，请确认后端 JWT_SECRET 与 Supabase Settings→API→JWT Secret 一致",
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"无效的令牌: {str(e)}",
        )

