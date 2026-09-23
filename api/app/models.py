"""请求模型：2..40 个唯一 ASCII 采样点、一个注入根、至多 160 条有向通道。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class ChannelIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    from_: str = Field(alias="from")
    to: str
    cost: StrictInt = Field(ge=0, description="非负整数代价")


class SolveRequest(BaseModel):
    points: list[str] = Field(min_length=2, max_length=40)
    root: str
    channels: list[ChannelIn] = Field(max_length=160)
