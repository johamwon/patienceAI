"""Research Radar API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..models.schemas import ChannelSetRequest, SubscribeRequest
from ..services.radar.radar_service import is_demo_mode, radar_service

router = APIRouter()


class DemoTriggerRequest(BaseModel):
    subscription_id: str
    evidences: list[dict] | None = None


@router.post("/radar/subscribe")
async def subscribe(req: SubscribeRequest):
    return radar_service.subscribe(req.anon_user_id, req.disease_keyword, req.entities_json)


@router.get("/radar/subscriptions")
async def subscriptions(anon_user_id: str = Query(..., min_length=1)):
    return radar_service.list_subscriptions(anon_user_id)


@router.post("/radar/subscriptions/{subscription_id}/revoke")
async def revoke_subscription(subscription_id: str):
    radar_service.revoke(subscription_id)
    return {"ok": True}


@router.delete("/radar/subscriptions/{subscription_id}")
async def delete_subscription(subscription_id: str):
    radar_service.delete(subscription_id)
    return {"ok": True}


@router.get("/radar/channels")
async def channels(anon_user_id: str = Query(..., min_length=1)):
    return radar_service.list_channels(anon_user_id)


@router.post("/radar/channels")
async def set_channel(req: ChannelSetRequest):
    try:
        radar_service.set_channel(req.anon_user_id, req.channel, req.contact)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


@router.delete("/radar/channels/{channel}")
async def unset_channel(channel: str, anon_user_id: str = Query(..., min_length=1)):
    try:
        radar_service.unset_channel(anon_user_id, channel)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


@router.delete("/radar/user/{anon_user_id}")
async def delete_user(anon_user_id: str):
    radar_service.delete_all(anon_user_id)
    return {"ok": True}


@router.get("/radar/messages")
async def messages(anon_user_id: str = Query(..., min_length=1)):
    return radar_service.subscriptions.list_inapp_messages(anon_user_id)


@router.post("/radar/messages/{message_id}/read")
async def mark_message_read(message_id: str):
    radar_service.subscriptions.mark_read(message_id)
    return {"ok": True}


@router.post("/radar/demo/trigger")
async def demo_trigger(req: DemoTriggerRequest):
    if not is_demo_mode():
        raise HTTPException(status_code=404, detail="Radar demo mode disabled")
    try:
        result = await radar_service.inject_demo_progress(req.subscription_id, req.evidences)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "ok": True,
        "delivered": result.delivered,
        "new_count": result.new_count,
        "delivery_results": [item.__dict__ for item in result.delivery_results],
        "digest": result.digest,
    }
