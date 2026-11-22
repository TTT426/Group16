"""/connect/discord: save the bot token, choose the server, import.

Same rules as the other connect routes: localhost only, no cross-site requests, the token is never sent back.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import discord_account as discord
from ..config import get_settings
from ..connectors.base import ConnectorError
from ..connectors.factory import build_connector
from ..db.models import Document
from ..db.session import get_session
from ..embeddings.base import Embedder
from ..envfile import update_env
from ..ingest.pipeline import ingest_documents
from .deps import embedder_dep
from .hub import local_only, page

router = APIRouter(dependencies=[Depends(local_only)], tags=["connect"])
SessionDep = Annotated[Session, Depends(get_session)]


def _status(session: Session, check: dict | None = None) -> dict:
    """What the connect pages show: the bot, the chosen server, and how much was imported from it."""
    settings = get_settings()
    token, guild_id = settings.discord_bot_token, settings.discord_guild_id
    result: dict = {"connected": bool(token), "guild_id": guild_id, "check": None, "error": None, "documents": 0}
    if token:
        try:
            result["check"] = check or discord.check(token)
        except discord.DiscordError as exc:
            result["error"] = str(exc)
    if guild_id:  # documents link to their server, so this never counts the practice scenario
        result["documents"] = session.scalar(select(func.count()).select_from(Document).where(
            Document.source == "discord", Document.url.contains(f"/channels/{guild_id}/"))) or 0
    return result


@router.get("/connect/discord", include_in_schema=False)
def discord_page() -> FileResponse:
    return page("connect-discord.html")


@router.get("/api/discord/status")
def status(session: SessionDep) -> dict:
    return _status(session)


class TokenIn(BaseModel):
    token: str


@router.post("/api/discord/token")
def save_token(body: TokenIn, session: SessionDep) -> dict:
    token = body.token.strip()
    try:
        check = discord.check(token)  # valid token: save it even before the bot joins a server
    except discord.DiscordError as exc:
        raise HTTPException(400, str(exc)) from exc
    guilds = [g["id"] for g in check["guilds"]]
    current = get_settings().discord_guild_id
    guild_id = current if current in guilds else guilds[0] if len(guilds) == 1 else ""  # only one server: pick it
    update_env({"DISCORD_BOT_TOKEN": token, "DISCORD_GUILD_ID": guild_id})
    return _status(session, check)


class GuildIn(BaseModel):
    guild_id: str


@router.post("/api/discord/guild")
def choose_guild(body: GuildIn, session: SessionDep) -> dict:
    try:
        check = discord.check(get_settings().discord_bot_token)
    except discord.DiscordError as exc:
        raise HTTPException(400, str(exc)) from exc
    if body.guild_id not in {g["id"] for g in check["guilds"]}:
        raise HTTPException(400, discord.MSG_NOT_IN_SERVER)
    update_env({"DISCORD_GUILD_ID": body.guild_id})
    return _status(session, check)


@router.post("/api/discord/disconnect")
def disconnect() -> dict:
    update_env({"DISCORD_BOT_TOKEN": "", "DISCORD_GUILD_ID": ""})
    return {"ok": True}


@router.post("/api/discord/import")
def import_discord(session: SessionDep, embedder: Annotated[Embedder, Depends(embedder_dep)]) -> dict:
    try:
        stats = ingest_documents(session, build_connector("discord", get_settings()).fetch(), embedder)
    except ConnectorError as exc:
        session.rollback()
        raise HTTPException(502, str(exc)) from exc
    return {"imported": stats.as_dict()}
