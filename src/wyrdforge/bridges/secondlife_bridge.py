"""SlWyrdBridge — the Second Life Bifrost bridge for WYRD.

This bridge is the perception/memory seam designed in
``heimdall-research/04-wyrd-integration-design.md`` §B.  It consumes
Heimdall-format events (the C# core's §7.3 vocabulary and the Python API's
JSON event forms), translates them into:

1. ECS mutations in a ``second-life`` World,
2. attributed Hugin observations through :class:`WritebackEngine`, and
3. ``sl.*`` publications on WYRD's EventBus.

Truth ownership is the central invariant: simulator state is mirrored in
ECS components, while chat is stored only as an attributed utterance.  A
sentence spoken in chat never becomes a Mimir canonical fact merely
because it was said.  Inbound text is checked with the prompt-injection
guard before it is written as an observation; the observation title is
bridge-generated, so untrusted message text is never used as a title.
"""
from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import Field

import wyrdforge.ecs.components.character  # noqa: F401  (registers persona_ref)
import wyrdforge.ecs.components.identity  # noqa: F401  (registers name/status)
import wyrdforge.ecs.components.sl_avatar_profile  # noqa: F401
import wyrdforge.ecs.components.sl_object  # noqa: F401
import wyrdforge.ecs.components.sl_place  # noqa: F401
import wyrdforge.ecs.components.sl_position  # noqa: F401
import wyrdforge.ecs.components.sl_presence  # noqa: F401
from wyrdforge.bridges.base import BifrostBridge
from wyrdforge.ecs.components.character import PersonaRefComponent
from wyrdforge.ecs.components.identity import (
    DescriptionComponent,
    NameComponent,
    StatusComponent,
)
from wyrdforge.ecs.components.sl_avatar_profile import SLAvatarProfileComponent
from wyrdforge.ecs.components.sl_object import SLObjectComponent
from wyrdforge.ecs.components.sl_place import SLParcelComponent, SLRegionComponent
from wyrdforge.ecs.components.sl_position import SLPositionComponent
from wyrdforge.ecs.components.sl_presence import SLPresenceComponent
from wyrdforge.ecs.components.spatial import ContainerComponent, SpatialComponent
from wyrdforge.ecs.world import World
from wyrdforge.ecs.yggdrasil import YggdrasilTree
from wyrdforge.models.common import StrictModel
from wyrdforge.oracle.models import ObservationSummary, WorldContextPacket
from wyrdforge.oracle.passive_oracle import PassiveOracle
from wyrdforge.persistence.memory_store import PersistentMemoryStore
from wyrdforge.persistence.world_store import WorldStore
from wyrdforge.runtime.events import EventBus
from wyrdforge.security.prompt_injection_guard import detect_prompt_injection
from wyrdforge.services.writeback_engine import WritebackEngine

GRID_ZONE_ID = "sl:grid:agni"
WORLD_ID = "second-life"


# ---------------------------------------------------------------------------
# Configuration and translation results
# ---------------------------------------------------------------------------


@dataclass
class SecondLifeBridgeConfig:
    """Identity and ingestion settings for the inhabitant of the bridge."""

    self_avatar_uuid: str = ""
    self_name: str = "Yrsa Freydisdottir"
    self_persona_id: str = "yrsa_freydisdottir"
    grid_id: str = GRID_ZONE_ID
    grid_name: str = "Agni"
    position_throttle_seconds: float = 1.0


@dataclass
class TranslatedEvent:
    """A compact receipt for one translated Heimdall event."""

    event_type: str
    bus_topic: str | None = None
    entity_ids: list[str] = field(default_factory=list)
    observation_id: str | None = None
    injection_patterns: list[str] = field(default_factory=list)
    ignored_reason: str | None = None


# ---------------------------------------------------------------------------
# Bus payload schemas
# ---------------------------------------------------------------------------


class SLChatReceivedPayload(StrictModel):
    speaker_id: str
    speaker_name: str
    message: str
    channel: int = 0
    place_id: str | None = None
    group_id: str | None = None
    injection_patterns: list[str] = Field(default_factory=list)


class SLIMReceivedPayload(StrictModel):
    sender_id: str
    sender_name: str
    message: str
    conversation_id: str
    injection_patterns: list[str] = Field(default_factory=list)


class SLRegionChangedPayload(StrictModel):
    region_id: str
    region_name: str
    previous_region_id: str | None = None


class SLParcelChangedPayload(StrictModel):
    parcel_id: str
    parcel_name: str
    region_id: str


class SLAvatarAppearedPayload(StrictModel):
    avatar_id: str
    avatar_name: str
    place_id: str | None = None


class SLAvatarLeftPayload(StrictModel):
    avatar_id: str
    place_id: str | None = None


class SLSelfMovedPayload(StrictModel):
    avatar_id: str
    region_id: str | None = None
    parcel_id: str | None = None
    position: tuple[float, float, float]


class SLObjectSeenPayload(StrictModel):
    object_id: str
    object_name: str
    place_id: str | None = None


class SLTeleportCompletedPayload(StrictModel):
    avatar_id: str
    region_id: str
    region_name: str
    parcel_id: str | None = None


class SLFriendPresencePayload(StrictModel):
    avatar_id: str
    avatar_name: str
    online: bool


class SLSelfAppearancePayload(StrictModel):
    avatar_id: str
    items_worn: list[str] = Field(default_factory=list)
    items_removed: list[str] = Field(default_factory=list)


class SLSessionChangedPayload(StrictModel):
    avatar_id: str | None = None
    state: str
    region_id: str | None = None


SL_TOPIC_SCHEMAS: dict[str, type[StrictModel]] = {
    "sl.chat.received": SLChatReceivedPayload,
    "sl.im.received": SLIMReceivedPayload,
    "sl.region.changed": SLRegionChangedPayload,
    "sl.parcel.changed": SLParcelChangedPayload,
    "sl.avatar.appeared": SLAvatarAppearedPayload,
    "sl.avatar.left": SLAvatarLeftPayload,
    "sl.self.moved": SLSelfMovedPayload,
    "sl.object.seen": SLObjectSeenPayload,
    "sl.teleport.completed": SLTeleportCompletedPayload,
    "sl.friend.presence": SLFriendPresencePayload,
    "sl.self.appearance": SLSelfAppearancePayload,
    "sl.session.changed": SLSessionChangedPayload,
}


def register_sl_topics(bus: EventBus) -> None:
    """Register every ``sl.*`` topic and payload schema on *bus*."""
    for topic, schema in SL_TOPIC_SCHEMAS.items():
        # Movement is high-frequency and explicitly not replayed (§B.2.1).
        replay = 0 if topic == "sl.self.moved" else 100
        try:
            bus.register_topic(topic, payload_schema=schema, replay_buffer=replay)
        except ValueError:
            pass  # already registered — first registration wins


# ---------------------------------------------------------------------------
# Small parsing helpers
# ---------------------------------------------------------------------------

_EVENT_ALIASES = {
    "loginsuccess": "LoginSuccess",
    "login": "LoginSuccess",
    "disconnected": "Disconnected",
    "logout": "Disconnected",
    "regionchanged": "RegionChanged",
    "parcelchanged": "ParcelChanged",
    "parcelentered": "ParcelChanged",
    "avatarappeared": "AvatarAppeared",
    "avatarupdated": "AvatarAppeared",
    "avatarleft": "AvatarLeft",
    "chat": "ChatReceived",
    "chatreceived": "ChatReceived",
    "groupchat": "GroupChatReceived",
    "groupchatreceived": "GroupChatReceived",
    "im": "IMReceived",
    "imreceived": "IMReceived",
    "selfpositionupdated": "SelfPositionUpdated",
    "positionupdate": "SelfPositionUpdated",
    "positionupdated": "SelfPositionUpdated",
    "objectinfo": "ObjectInfo",
    "objectappeared": "ObjectInfo",
    "teleportcompleted": "TeleportCompleted",
    "teleportprogress": "TeleportProgress",
    "friendonline": "FriendOnline",
    "friendoffline": "FriendOffline",
    "appearancechanged": "AppearanceChanged",
}


def _canonical_event_name(raw: str) -> str:
    key = re.sub(r"[^a-z0-9]", "", raw.lower())
    try:
        return _EVENT_ALIASES[key]
    except KeyError:
        raise ValueError(f"Unsupported Second Life event type: {raw!r}") from None


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "unnamed"


def _value(payload: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in payload and payload[key] not in (None, ""):
            return payload[key]
    return default


def _text(payload: dict[str, Any], *keys: str, default: str = "") -> str:
    value = _value(payload, *keys, default=default)
    return "" if value is None else str(value).strip()


def _int(payload: dict[str, Any], *keys: str, default: int | None = None) -> int | None:
    value = _value(payload, *keys, default=None)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float(payload: dict[str, Any], *keys: str, default: float | None = None) -> float | None:
    value = _value(payload, *keys, default=None)
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bool(payload: dict[str, Any], *keys: str, default: bool | None = None) -> bool | None:
    value = _value(payload, *keys, default=None)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    lowered = str(value).strip().lower()
    if lowered in {"true", "yes", "1", "on"}:
        return True
    if lowered in {"false", "no", "0", "off"}:
        return False
    return default


def _position(payload: dict[str, Any]) -> tuple[float, float, float] | None:
    raw = _value(payload, "position", "pos", "source_pos", "source_position")
    if isinstance(raw, dict):
        try:
            return (float(raw["x"]), float(raw["y"]), float(raw["z"]))
        except (KeyError, TypeError, ValueError):
            return None
    if isinstance(raw, (list, tuple)) and len(raw) == 3:
        try:
            return (float(raw[0]), float(raw[1]), float(raw[2]))
        except (TypeError, ValueError):
            return None
    if all(key in payload for key in ("x", "y", "z")):
        try:
            return (float(payload["x"]), float(payload["y"]), float(payload["z"]))
        except (TypeError, ValueError):
            return None
    return None


def _rotation(payload: dict[str, Any]) -> tuple[float, float, float, float] | None:
    raw = _value(payload, "rotation", "rot")
    if isinstance(raw, dict):
        try:
            return (
                float(raw.get("x", 0.0)),
                float(raw.get("y", 0.0)),
                float(raw.get("z", 0.0)),
                float(raw.get("w", 1.0)),
            )
        except (TypeError, ValueError):
            return None
    if isinstance(raw, (list, tuple)) and len(raw) == 4:
        try:
            return (float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3]))
        except (TypeError, ValueError):
            return None
    return None


def _timestamp(payload: dict[str, Any]) -> datetime | None:
    raw = _value(payload, "timestamp", "observed_at", "time")
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=UTC)
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(float(raw), tz=UTC)
    text = str(raw).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _string_list(payload: dict[str, Any], *keys: str) -> list[str]:
    raw = _value(payload, *keys, default=[])
    if raw is None:
        return []
    if isinstance(raw, (list, tuple, set)):
        return [str(item) for item in raw]
    return [str(raw)]


# ---------------------------------------------------------------------------
# Event translator
# ---------------------------------------------------------------------------


class EventTranslator:
    """Translate Heimdall events into ECS mutations and Hugin observations."""

    def __init__(
        self,
        world: World,
        yggdrasil: YggdrasilTree,
        writeback: WritebackEngine,
        *,
        bus: EventBus | None = None,
        config: SecondLifeBridgeConfig | None = None,
    ) -> None:
        self._world = world
        self._tree = yggdrasil
        self._writeback = writeback
        self._bus = bus
        self._config = config or SecondLifeBridgeConfig()
        if self._bus is not None:
            register_sl_topics(self._bus)

        self._current_region_id: str | None = None
        self._current_parcel_id: str | None = None
        self._region_ref_by_id: dict[str, str] = {}
        self._seen_avatar_ids: set[str] = {
            entity.entity_id for entity in world.query_by_tag("avatar")
        }
        self._last_position_at: dict[str, datetime] = {}

        if self._config.self_avatar_uuid:
            self._self_entity_id: str | None = (
                f"sl:avatar:{self._config.self_avatar_uuid.lower()}"
            )
        elif self._config.self_name:
            self._self_entity_id = f"sl:avatar:name:{_slug(self._config.self_name)}"
        else:
            self._self_entity_id = None

        self._ensure_grid_zone()

    # -- public state ----------------------------------------------------

    @property
    def self_entity_id(self) -> str | None:
        return self._self_entity_id

    @property
    def current_region_id(self) -> str | None:
        return self._current_region_id

    @property
    def current_parcel_id(self) -> str | None:
        return self._current_parcel_id

    # -- entry points ------------------------------------------------------

    def translate(
        self,
        event_or_type: dict[str, Any] | str,
        payload: dict[str, Any] | None = None,
    ) -> TranslatedEvent:
        """Translate one event dict or an ``(event_type, payload)`` pair."""
        if isinstance(event_or_type, dict):
            event = dict(event_or_type)
            if payload:
                event.update(payload)
            raw_type = _text(event, "event", "event_type", "heimdall_event")
        else:
            event = dict(payload or {})
            raw_type = event_or_type
        if not raw_type:
            raise ValueError("Second Life event is missing its event type")

        canonical = _canonical_event_name(raw_type)
        # The API form uses {"event": "chat", "type": "group"} for group chat.
        if canonical == "ChatReceived" and (
            _text(event, "type").lower() == "group" or _text(event, "group", "group_id")
        ):
            canonical = "GroupChatReceived"

        handler = getattr(self, f"_handle_{_slug(canonical).replace('-', '_')}", None)
        if handler is None:
            return TranslatedEvent(
                event_type=canonical,
                ignored_reason=f"No Phase I0 translator for {canonical}",
            )
        result: TranslatedEvent = handler(canonical, event)
        return result

    def replay(self, events: Iterable[dict[str, Any]]) -> list[TranslatedEvent]:
        """Replay an iterable of Heimdall event dicts in order."""
        return [self.translate(event) for event in events]

    def replay_file(self, path: str | Path) -> list[TranslatedEvent]:
        """Replay a ``.jsonl`` fixture or a JSON list/object fixture."""
        source = Path(path)
        text = source.read_text(encoding="utf-8")
        if source.suffix.lower() == ".jsonl":
            events = [json.loads(line) for line in text.splitlines() if line.strip()]
        else:
            parsed = json.loads(text)
            events = parsed["events"] if isinstance(parsed, dict) else parsed
        return self.replay(events)

    # -- hierarchy and identity helpers ------------------------------------

    def _ensure_grid_zone(self) -> None:
        if self._world.get_entity(self._config.grid_id) is None:
            self._tree.create_zone(
                zone_id=self._config.grid_id,
                name=self._config.grid_name,
                description="Second Life main grid",
            )

    def _region_ref(self, region_id: str | None) -> str:
        if region_id is None:
            return ""
        if region_id in self._region_ref_by_id:
            return self._region_ref_by_id[region_id]
        return region_id.removeprefix("sl:region:")

    def _ensure_region(
        self,
        payload: dict[str, Any],
        *,
        name: str = "",
        uuid: str = "",
    ) -> str | None:
        region_name = name or _text(
            payload,
            "region_name",
            "region",
            "destination_region_name",
            "destination_region",
            "sim_name",
            "sim",
        )
        region_uuid = uuid or _text(
            payload,
            "region_uuid",
            "destination_region_uuid",
            "sim_uuid",
        )
        if not region_name and not region_uuid:
            return self._current_region_id

        ref = region_uuid.lower() if region_uuid else _slug(region_name)
        region_id = f"sl:region:{ref}"
        self._region_ref_by_id[region_id] = ref

        if self._world.get_entity(region_id) is None:
            self._tree.create_region(
                region_id=region_id,
                name=region_name or ref,
                parent_zone_id=self._config.grid_id,
            )
        elif region_name:
            name_comp = self._world.get_component(region_id, "name")
            if isinstance(name_comp, NameComponent) and name_comp.name != region_name:
                name_comp.name = region_name
                name_comp.touch()

        comp = self._world.get_component(region_id, "sl_region")
        if not isinstance(comp, SLRegionComponent):
            comp = SLRegionComponent(entity_id=region_id, region_uuid=region_uuid or ref)
            self._world.add_component(region_id, comp)
        if region_uuid:
            comp.region_uuid = region_uuid
        estate_id = _int(payload, "estate_id")
        if estate_id is not None:
            comp.estate_id = estate_id
        estate_name = _text(payload, "estate_name")
        if estate_name:
            comp.estate_name = estate_name
        maturity = _text(payload, "maturity_rating", "maturity")
        if maturity:
            comp.maturity_rating = maturity
        handle = _int(payload, "region_handle")
        if handle is not None:
            comp.region_handle = handle
        grid_x = _int(payload, "grid_x")
        if grid_x is not None:
            comp.grid_x = grid_x
        grid_y = _int(payload, "grid_y")
        if grid_y is not None:
            comp.grid_y = grid_y
        dilation = _float(payload, "time_dilation")
        if dilation is not None:
            comp.time_dilation = dilation
        fps = _float(payload, "simulator_fps", "fps")
        if fps is not None:
            comp.simulator_fps = fps
        agents = _int(payload, "agent_count")
        if agents is not None:
            comp.agent_count = agents
        damage = _bool(payload, "damage_allowed", "allow_damage")
        if damage is not None:
            comp.damage_allowed = damage
        comp.touch()
        return region_id

    def _ensure_parcel(
        self,
        payload: dict[str, Any],
        *,
        region_id: str | None = None,
    ) -> str | None:
        region_id = region_id or self._ensure_region(payload) or self._current_region_id
        if region_id is None:
            return None
        region_ref = self._region_ref(region_id)

        explicit_id = _text(payload, "parcel_entity_id")
        local_id = _int(payload, "parcel_local_id", "parcel_local", "local_id")
        parcel_uuid = _text(payload, "parcel_uuid")
        parcel_name = _text(payload, "parcel_name", "parcel", "location_name")
        raw_parcel_id = _value(payload, "parcel_id")
        if explicit_id:
            parcel_id = explicit_id
        elif isinstance(raw_parcel_id, str) and raw_parcel_id.startswith("sl:parcel:"):
            parcel_id = raw_parcel_id
        elif local_id is not None:
            parcel_id = f"sl:parcel:{region_ref}:{local_id}"
        elif parcel_uuid:
            parcel_id = f"sl:parcel:{parcel_uuid.lower()}"
        elif isinstance(raw_parcel_id, int):
            local_id = int(raw_parcel_id)
            parcel_id = f"sl:parcel:{region_ref}:{local_id}"
        elif parcel_name:
            parcel_id = f"sl:parcel:{region_ref}:{_slug(parcel_name)}"
        else:
            return self._current_parcel_id if region_id == self._current_region_id else None

        if self._world.get_entity(parcel_id) is None:
            self._tree.create_location(
                location_id=parcel_id,
                name=parcel_name or parcel_id,
                parent_region_id=region_id,
            )
        elif parcel_name:
            name_comp = self._world.get_component(parcel_id, "name")
            if isinstance(name_comp, NameComponent) and name_comp.name != parcel_name:
                name_comp.name = parcel_name
                name_comp.touch()

        comp = self._world.get_component(parcel_id, "sl_parcel")
        if not isinstance(comp, SLParcelComponent):
            comp = SLParcelComponent(
                entity_id=parcel_id,
                region_id=region_id,
                parcel_local_id=local_id or 0,
            )
            self._world.add_component(parcel_id, comp)
        comp.region_id = region_id
        if local_id is not None:
            comp.parcel_local_id = local_id
        owner_uuid = _text(payload, "parcel_owner_uuid", "owner_uuid")
        owner_id = _text(payload, "parcel_owner_id", "owner_id")
        if owner_uuid:
            comp.owner_id = f"sl:avatar:{owner_uuid.lower()}"
        elif owner_id:
            comp.owner_id = owner_id
        group_id = _text(payload, "parcel_group_id", "group_id")
        if group_id:
            comp.group_id = group_id
        area = _int(payload, "area_sqm", "parcel_area", "area")
        if area is not None:
            comp.area_sqm = area
        category = _text(payload, "parcel_category", "category")
        if category:
            comp.category = category
        voice = _bool(payload, "voice_enabled")
        if voice is not None:
            comp.voice_enabled = voice
        public = _bool(payload, "public_access")
        if public is not None:
            comp.public_access = public
        damage = _bool(payload, "parcel_damage_allowed", "damage_allowed")
        if damage is not None:
            comp.damage_allowed = damage
        comp.touch()
        return parcel_id

    def _ensure_place(
        self,
        payload: dict[str, Any],
        *,
        parcel_id: str,
        region_id: str,
    ) -> str | None:
        explicit = _text(payload, "place_entity_id", "sublocation_entity_id")
        slug = _text(payload, "place_slug", "sublocation_slug", "anchor_slug")
        name = _text(payload, "place_name", "sublocation_name", "anchor_name")
        if explicit:
            place_id = explicit
        elif slug:
            place_id = f"sl:place:{self._region_ref(region_id)}:{_slug(slug)}"
        elif name:
            place_id = f"sl:place:{self._region_ref(region_id)}:{_slug(name)}"
        else:
            return None
        if self._world.get_entity(place_id) is None:
            self._tree.create_sublocation(
                sublocation_id=place_id,
                name=name or slug or place_id,
                parent_location_id=parcel_id,
            )
        return place_id

    def _avatar_entity_id(self, uuid: str, name: str) -> str:
        if uuid:
            return f"sl:avatar:{uuid.lower()}"
        if name:
            return f"sl:avatar:name:{_slug(name)}"
        raise ValueError("Second Life avatar event has neither a UUID nor a name")

    def _ensure_avatar(
        self,
        payload: dict[str, Any],
        *,
        self_avatar: bool = False,
        name_keys: tuple[str, ...] = (
            "avatar_name",
            "avatar",
            "from_name",
            "from",
            "sender_name",
            "sender",
            "name",
        ),
        uuid_keys: tuple[str, ...] = (
            "avatar_uuid",
            "from_uuid",
            "sender_uuid",
            "uuid",
        ),
        online: bool | None = None,
        in_region: bool | None = None,
    ) -> str:
        uuid = _text(payload, *uuid_keys)
        name = _text(payload, *name_keys)
        if self_avatar:
            uuid = uuid or self._config.self_avatar_uuid
            name = name or self._config.self_name
        entity_id = self._avatar_entity_id(uuid, name)
        if self_avatar:
            self._self_entity_id = entity_id

        entity = self._world.get_entity(entity_id)
        if entity is None:
            tags = {"avatar", "person"}
            if self_avatar:
                tags.add("self")
            self._world.create_entity(entity_id=entity_id, tags=tags)
        elif self_avatar:
            self._world.tag_entity(entity_id, "self")

        display_name = _text(payload, "display_name")
        legacy_name = _text(payload, "legacy_name") or name
        primary_name = display_name or name or uuid
        name_comp = self._world.get_component(entity_id, "name")
        aliases = sorted(
            {
                alias
                for alias in (name, legacy_name, display_name)
                if alias and alias != primary_name
            }
        )
        if not isinstance(name_comp, NameComponent):
            self._world.add_component(
                entity_id,
                NameComponent(entity_id=entity_id, name=primary_name, aliases=aliases),
            )
        else:
            name_comp.name = primary_name
            name_comp.aliases = sorted(set(name_comp.aliases) | set(aliases))
            name_comp.touch()

        profile_text = _text(payload, "profile_text", "profile")
        if profile_text:
            desc = self._world.get_component(entity_id, "description")
            if not isinstance(desc, DescriptionComponent):
                self._world.add_component(
                    entity_id,
                    DescriptionComponent(entity_id=entity_id, short_desc=profile_text),
                )
            else:
                desc.short_desc = profile_text
                desc.touch()

        profile = self._world.get_component(entity_id, "sl_avatar_profile")
        if not isinstance(profile, SLAvatarProfileComponent):
            profile = SLAvatarProfileComponent(
                entity_id=entity_id,
                avatar_uuid=uuid,
                legacy_name=legacy_name,
                display_name=display_name,
            )
            self._world.add_component(entity_id, profile)
        if uuid:
            profile.avatar_uuid = uuid
        if legacy_name:
            profile.legacy_name = legacy_name
        if display_name:
            profile.display_name = display_name
        created = _text(payload, "account_created_on", "account_created", "born_on")
        if created:
            profile.account_created_on = created
        payment = _bool(payload, "payment_info_on_file")
        if payment is not None:
            profile.payment_info_on_file = payment
        group_ids = _string_list(payload, "group_ids", "groups")
        if group_ids:
            profile.group_ids = group_ids
        scripted = _bool(payload, "scripted_agent", "is_scripted_agent")
        if scripted is not None:
            profile.scripted_agent = scripted
        profile.touch()

        self._update_presence(
            entity_id,
            online=online,
            in_region=in_region,
            last_seen=_timestamp(payload),
        )

        if self_avatar:
            persona = self._world.get_component(entity_id, "persona_ref")
            if not isinstance(persona, PersonaRefComponent):
                self._world.add_component(
                    entity_id,
                    PersonaRefComponent(
                        entity_id=entity_id,
                        persona_id=self._config.self_persona_id,
                        is_ai_controlled=True,
                    ),
                )
            else:
                persona.persona_id = self._config.self_persona_id
                persona.is_ai_controlled = True
                persona.touch()
            status = self._world.get_component(entity_id, "status")
            if not isinstance(status, StatusComponent):
                self._world.add_component(
                    entity_id,
                    StatusComponent(entity_id=entity_id, state="online"),
                )
        return entity_id

    def _ensure_self(self, payload: dict[str, Any] | None = None) -> str:
        payload = payload or {}
        return self._ensure_avatar(
            payload,
            self_avatar=True,
            name_keys=("avatar_name", "avatar", "self_name", "name"),
            uuid_keys=("avatar_uuid", "self_uuid", "uuid"),
            online=True,
            in_region=True,
        )

    def _entity_name(self, entity_id: str) -> str:
        comp = self._world.get_component(entity_id, "name")
        return comp.name if isinstance(comp, NameComponent) else entity_id

    def _update_presence(
        self,
        entity_id: str,
        *,
        online: bool | None = None,
        in_region: bool | None = None,
        typing: bool | None = None,
        idle: bool | None = None,
        afk: bool | None = None,
        last_seen: datetime | None = None,
    ) -> SLPresenceComponent:
        comp = self._world.get_component(entity_id, "sl_presence")
        if not isinstance(comp, SLPresenceComponent):
            comp = SLPresenceComponent(entity_id=entity_id)
            self._world.add_component(entity_id, comp)
        if online is not None:
            comp.online = online
        if in_region is not None:
            comp.in_region = in_region
        if typing is not None:
            comp.typing = typing
        if idle is not None:
            comp.idle = idle
        if afk is not None:
            comp.afk = afk
        if last_seen is not None:
            comp.last_seen_at = last_seen
        comp.touch()
        return comp

    def _update_position(
        self,
        entity_id: str,
        payload: dict[str, Any],
        *,
        region_id: str | None = None,
        parcel_id: str | None = None,
    ) -> SLPositionComponent:
        comp = self._world.get_component(entity_id, "sl_position")
        if not isinstance(comp, SLPositionComponent):
            comp = SLPositionComponent(entity_id=entity_id)
            self._world.add_component(entity_id, comp)
        if region_id is not None:
            comp.region_id = region_id
        elif self._current_region_id is not None:
            comp.region_id = self._current_region_id
        if parcel_id is not None:
            comp.parcel_id = parcel_id
        elif self._current_parcel_id is not None:
            comp.parcel_id = self._current_parcel_id
        position = _position(payload)
        if position is not None:
            comp.position = position
        global_pos = _value(payload, "global_position", "global_pos")
        if isinstance(global_pos, (list, tuple)) and len(global_pos) == 3:
            try:
                comp.global_position = (
                    float(global_pos[0]),
                    float(global_pos[1]),
                    float(global_pos[2]),
                )
            except (TypeError, ValueError):
                pass
        rotation = _rotation(payload)
        if rotation is not None:
            comp.rotation = rotation
        sitting = _text(payload, "sitting_on_object_id", "sitting_on")
        if sitting:
            comp.sitting_on_object_id = sitting
        comp.touch()
        return comp

    def _place(
        self,
        entity_id: str,
        parcel_id: str,
        *,
        sublocation_id: str | None = None,
    ) -> None:
        spatial = self._world.get_component(entity_id, "spatial")
        if isinstance(spatial, SpatialComponent):
            self._tree.move_entity(
                entity_id,
                location_id=parcel_id,
                sublocation_id=sublocation_id,
            )
        else:
            self._tree.place_entity(
                entity_id,
                location_id=parcel_id,
                sublocation_id=sublocation_id,
            )

    def _clear_placement(self, entity_id: str) -> None:
        spatial = self._world.get_component(entity_id, "spatial")
        if not isinstance(spatial, SpatialComponent):
            return
        target_id = spatial.most_specific_id()
        if target_id:
            container = self._world.get_component(target_id, "container")
            if isinstance(container, ContainerComponent):
                container.remove_child(entity_id)
                container.touch()
        self._world.remove_component(entity_id, "spatial")

    def _observe(
        self,
        *,
        kind: str,
        title: str,
        summary: str,
        participants: list[str],
        place_id: str | None,
        salience: float = 0.5,
    ) -> str:
        record = self._writeback.write_observation(
            title=title,
            summary=summary,
            observation_kind=kind,
            participants=participants,
            place_id=place_id,
            salience=salience,
        )
        return record.record_id

    def _publish(self, topic: str, payload: dict[str, Any]) -> None:
        if self._bus is not None:
            self._bus.publish(topic, payload, source="heimdall.secondlife")

    # -- session / region / parcel handlers ---------------------------------

    def _handle_loginsuccess(
        self, canonical: str, payload: dict[str, Any]
    ) -> TranslatedEvent:
        self_id = self._ensure_self(payload)
        region_id = self._ensure_region(payload)
        parcel_id = None
        if region_id is not None:
            self._current_region_id = region_id
            parcel_id = self._ensure_parcel(payload, region_id=region_id)
        if parcel_id is not None:
            self._current_parcel_id = parcel_id
            place_id = self._ensure_place(
                payload, parcel_id=parcel_id, region_id=region_id or ""
            )
            self._place(self_id, parcel_id, sublocation_id=place_id)
        self._update_position(
            self_id, payload, region_id=region_id, parcel_id=parcel_id
        )
        status = self._world.get_component(self_id, "status")
        if isinstance(status, StatusComponent):
            status.state = "online"
            status.touch()
        region_name = self._entity_name(region_id) if region_id else "Second Life"
        observation_id = self._observe(
            kind="world_event",
            title="Second Life session started",
            summary=f"{self._entity_name(self_id)} logged in to {region_name}.",
            participants=[self_id],
            place_id=parcel_id,
        )
        self._publish(
            "sl.session.changed",
            {"avatar_id": self_id, "state": "online", "region_id": region_id},
        )
        return TranslatedEvent(
            event_type=canonical,
            bus_topic="sl.session.changed",
            entity_ids=[self_id],
            observation_id=observation_id,
        )

    def _handle_disconnected(
        self, canonical: str, payload: dict[str, Any]
    ) -> TranslatedEvent:
        self_id = self._self_entity_id
        entity_ids: list[str] = []
        if self_id is not None and self._world.get_entity(self_id) is not None:
            entity_ids.append(self_id)
            self._update_presence(self_id, online=False, in_region=False)
            status = self._world.get_component(self_id, "status")
            if isinstance(status, StatusComponent):
                status.state = "offline"
                status.touch()
        reason = _text(payload, "reason")
        summary = "The Second Life session disconnected."
        if reason:
            summary = f"The Second Life session disconnected: {reason}"
        observation_id = self._observe(
            kind="world_event",
            title="Second Life session ended",
            summary=summary,
            participants=entity_ids,
            place_id=self._current_parcel_id,
        )
        self._publish(
            "sl.session.changed",
            {
                "avatar_id": self_id,
                "state": "offline",
                "region_id": self._current_region_id,
            },
        )
        return TranslatedEvent(
            event_type=canonical,
            bus_topic="sl.session.changed",
            entity_ids=entity_ids,
            observation_id=observation_id,
        )

    def _handle_regionchanged(
        self, canonical: str, payload: dict[str, Any]
    ) -> TranslatedEvent:
        previous_region_id = self._current_region_id
        region_id = self._ensure_region(payload)
        if region_id is None:
            return TranslatedEvent(
                event_type=canonical,
                ignored_reason="RegionChanged event named no region",
            )
        self._current_region_id = region_id
        self_id = self._ensure_self(payload)

        parcel_id = self._ensure_parcel(payload, region_id=region_id)
        if parcel_id is not None:
            self._current_parcel_id = parcel_id
            place_id = self._ensure_place(
                payload, parcel_id=parcel_id, region_id=region_id
            )
            self._place(self_id, parcel_id, sublocation_id=place_id)
        elif region_id != previous_region_id:
            self._current_parcel_id = None
            self._clear_placement(self_id)
        self._update_position(
            self_id, payload, region_id=region_id, parcel_id=parcel_id
        )

        observation_id = None
        if region_id != previous_region_id:
            region_name = self._entity_name(region_id)
            observation_id = self._observe(
                kind="world_event",
                title=f"Arrived in region {region_name}",
                summary=f"{self._entity_name(self_id)} arrived in {region_name}.",
                participants=[self_id],
                place_id=parcel_id,
            )
        self._publish(
            "sl.region.changed",
            {
                "region_id": region_id,
                "region_name": self._entity_name(region_id),
                "previous_region_id": previous_region_id,
            },
        )
        return TranslatedEvent(
            event_type=canonical,
            bus_topic="sl.region.changed",
            entity_ids=[self_id, region_id],
            observation_id=observation_id,
        )

    def _handle_parcelchanged(
        self, canonical: str, payload: dict[str, Any]
    ) -> TranslatedEvent:
        region_id = self._ensure_region(payload) or self._current_region_id
        parcel_id = self._ensure_parcel(payload, region_id=region_id)
        if region_id is None or parcel_id is None:
            return TranslatedEvent(
                event_type=canonical,
                ignored_reason="ParcelChanged event named no parcel",
            )
        previous_parcel_id = self._current_parcel_id
        self._current_region_id = region_id
        self._current_parcel_id = parcel_id
        self_id = self._ensure_self(payload)
        place_id = self._ensure_place(payload, parcel_id=parcel_id, region_id=region_id)
        self._place(self_id, parcel_id, sublocation_id=place_id)
        self._update_position(
            self_id, payload, region_id=region_id, parcel_id=parcel_id
        )

        observation_id = None
        if parcel_id != previous_parcel_id:
            parcel_name = self._entity_name(parcel_id)
            observation_id = self._observe(
                kind="world_event",
                title=f"Entered parcel {parcel_name}",
                summary=f"{self._entity_name(self_id)} entered {parcel_name}.",
                participants=[self_id],
                place_id=parcel_id,
            )
        self._publish(
            "sl.parcel.changed",
            {
                "parcel_id": parcel_id,
                "parcel_name": self._entity_name(parcel_id),
                "region_id": region_id,
            },
        )
        return TranslatedEvent(
            event_type=canonical,
            bus_topic="sl.parcel.changed",
            entity_ids=[self_id, parcel_id],
            observation_id=observation_id,
        )

    # -- avatar handlers ------------------------------------------------------

    def _handle_avatarappeared(
        self, canonical: str, payload: dict[str, Any]
    ) -> TranslatedEvent:
        avatar_id = self._ensure_avatar(payload, online=True, in_region=True)
        region_id = self._ensure_region(payload) or self._current_region_id
        parcel_id = self._ensure_parcel(payload, region_id=region_id)
        if parcel_id is None:
            parcel_id = self._current_parcel_id
        if parcel_id is not None and region_id is not None:
            place_id = self._ensure_place(
                payload, parcel_id=parcel_id, region_id=region_id
            )
            self._place(avatar_id, parcel_id, sublocation_id=place_id)
        self._update_position(
            avatar_id, payload, region_id=region_id, parcel_id=parcel_id
        )

        first_seen = avatar_id not in self._seen_avatar_ids
        self._seen_avatar_ids.add(avatar_id)
        observation_id = None
        if first_seen:
            avatar_name = self._entity_name(avatar_id)
            observation_id = self._observe(
                kind="world_event",
                title=f"{avatar_name} appeared",
                summary=f"{avatar_name} appeared nearby.",
                participants=[avatar_id],
                place_id=parcel_id,
            )
        self._publish(
            "sl.avatar.appeared",
            {
                "avatar_id": avatar_id,
                "avatar_name": self._entity_name(avatar_id),
                "place_id": parcel_id,
            },
        )
        return TranslatedEvent(
            event_type=canonical,
            bus_topic="sl.avatar.appeared",
            entity_ids=[avatar_id],
            observation_id=observation_id,
        )

    def _handle_avatarleft(
        self, canonical: str, payload: dict[str, Any]
    ) -> TranslatedEvent:
        avatar_id = self._ensure_avatar(payload, online=True, in_region=False)
        was_co_located = False
        if self._current_parcel_id is not None:
            container = self._world.get_component(self._current_parcel_id, "container")
            was_co_located = isinstance(container, ContainerComponent) and (
                avatar_id in container.children
            )
        self._clear_placement(avatar_id)
        self._update_presence(avatar_id, in_region=False, typing=False)

        observation_id = None
        if was_co_located:
            avatar_name = self._entity_name(avatar_id)
            observation_id = self._observe(
                kind="world_event",
                title=f"{avatar_name} left",
                summary=f"{avatar_name} left the parcel.",
                participants=[avatar_id],
                place_id=self._current_parcel_id,
            )
        self._publish(
            "sl.avatar.left",
            {"avatar_id": avatar_id, "place_id": self._current_parcel_id},
        )
        return TranslatedEvent(
            event_type=canonical,
            bus_topic="sl.avatar.left",
            entity_ids=[avatar_id],
            observation_id=observation_id,
        )

    # -- chat handlers --------------------------------------------------------

    def _chat_place_and_speaker(
        self, payload: dict[str, Any]
    ) -> tuple[str, str | None]:
        uuid = _text(payload, "from_uuid", "avatar_uuid", "sender_uuid", "uuid")
        name = _text(payload, "from_name", "from", "avatar_name", "sender_name", "name")
        is_self = bool(
            (uuid and self._config.self_avatar_uuid
             and uuid.lower() == self._config.self_avatar_uuid.lower())
            or (name and name == self._config.self_name)
            or _bool(payload, "is_self")
        )
        if is_self:
            speaker_id = self._ensure_self(payload)
        else:
            speaker_id = self._ensure_avatar(
                payload,
                name_keys=("from_name", "from", "avatar_name", "sender_name", "name"),
                uuid_keys=("from_uuid", "avatar_uuid", "sender_uuid", "uuid"),
                online=True,
                in_region=True,
            )
        parcel_id = self._current_parcel_id
        if parcel_id is not None:
            spatial = self._world.get_component(speaker_id, "spatial")
            if not isinstance(spatial, SpatialComponent):
                self._place(speaker_id, parcel_id)
        self._update_position(
            speaker_id,
            payload,
            region_id=self._current_region_id,
            parcel_id=parcel_id,
        )
        self._update_presence(speaker_id, online=True, in_region=True, typing=False)
        return speaker_id, parcel_id

    def _handle_chatreceived(
        self, canonical: str, payload: dict[str, Any]
    ) -> TranslatedEvent:
        return self._handle_chat(canonical, payload, group=False)

    def _handle_groupchatreceived(
        self, canonical: str, payload: dict[str, Any]
    ) -> TranslatedEvent:
        return self._handle_chat(canonical, payload, group=True)

    def _handle_chat(
        self, canonical: str, payload: dict[str, Any], *, group: bool
    ) -> TranslatedEvent:
        message = _text(payload, "msg", "message", "text")
        if not message:
            raise ValueError("ChatReceived event has no message text")
        speaker_id, parcel_id = self._chat_place_and_speaker(payload)
        speaker_name = self._entity_name(speaker_id)
        patterns = detect_prompt_injection(message)
        participants = [speaker_id]
        if self._self_entity_id and self._self_entity_id != speaker_id:
            participants.append(self._self_entity_id)
        label = "Group chat" if group else "Local chat"
        observation_id = self._observe(
            kind="utterance",
            title=f"{label} utterance by {speaker_name}",
            summary=message,
            participants=participants,
            place_id=parcel_id,
            salience=0.7,
        )
        group_id = _text(payload, "group_id", "group_uuid") or None
        if group and group_id is None and _text(payload, "group"):
            group_id = _text(payload, "group")
        self._publish(
            "sl.chat.received",
            {
                "speaker_id": speaker_id,
                "speaker_name": speaker_name,
                "message": message,
                "channel": _int(payload, "channel", default=0) or 0,
                "place_id": parcel_id,
                "group_id": group_id,
                "injection_patterns": patterns,
            },
        )
        return TranslatedEvent(
            event_type=canonical,
            bus_topic="sl.chat.received",
            entity_ids=participants,
            observation_id=observation_id,
            injection_patterns=patterns,
        )

    def _handle_imreceived(
        self, canonical: str, payload: dict[str, Any]
    ) -> TranslatedEvent:
        message = _text(payload, "msg", "message", "text")
        if not message:
            raise ValueError("IMReceived event has no message text")
        sender_id = self._ensure_avatar(
            payload,
            name_keys=("from_name", "from", "sender_name", "sender", "name"),
            uuid_keys=("from_uuid", "sender_uuid", "avatar_uuid", "uuid"),
            online=True,
        )
        sender_name = self._entity_name(sender_id)
        patterns = detect_prompt_injection(message)
        conversation_id = f"sl:im:{sender_id.removeprefix('sl:avatar:')}"
        participants = [sender_id]
        if self._self_entity_id and self._self_entity_id != sender_id:
            participants.append(self._self_entity_id)
        observation_id = self._observe(
            kind="utterance",
            title=f"Instant message from {sender_name}",
            summary=message,
            participants=participants,
            place_id=conversation_id,
            salience=0.7,
        )
        self._publish(
            "sl.im.received",
            {
                "sender_id": sender_id,
                "sender_name": sender_name,
                "message": message,
                "conversation_id": conversation_id,
                "injection_patterns": patterns,
            },
        )
        return TranslatedEvent(
            event_type=canonical,
            bus_topic="sl.im.received",
            entity_ids=participants,
            observation_id=observation_id,
            injection_patterns=patterns,
        )

    # -- movement / object / social handlers ---------------------------------

    def _handle_selfpositionupdated(
        self, canonical: str, payload: dict[str, Any]
    ) -> TranslatedEvent:
        self_id = self._ensure_self(payload)
        region_id = self._ensure_region(payload) or self._current_region_id
        parcel_id = self._ensure_parcel(payload, region_id=region_id)
        parcel_changed = parcel_id is not None and parcel_id != self._current_parcel_id
        if parcel_id is None:
            parcel_id = self._current_parcel_id

        stamp = _timestamp(payload)
        last = self._last_position_at.get(self_id)
        if (
            stamp is not None
            and last is not None
            and not parcel_changed
            and 0 <= (stamp - last).total_seconds() < self._config.position_throttle_seconds
        ):
            return TranslatedEvent(
                event_type=canonical,
                entity_ids=[self_id],
                ignored_reason="position update inside the 1 Hz throttle window",
            )
        if stamp is not None:
            self._last_position_at[self_id] = stamp

        if region_id is not None:
            self._current_region_id = region_id
        if parcel_id is not None:
            self._current_parcel_id = parcel_id
            spatial = self._world.get_component(self_id, "spatial")
            if not isinstance(spatial, SpatialComponent) or parcel_changed:
                self._place(self_id, parcel_id)
        position = self._update_position(
            self_id, payload, region_id=region_id, parcel_id=parcel_id
        )
        self._publish(
            "sl.self.moved",
            {
                "avatar_id": self_id,
                "region_id": region_id,
                "parcel_id": parcel_id,
                "position": position.position,
            },
        )
        return TranslatedEvent(
            event_type=canonical,
            bus_topic="sl.self.moved",
            entity_ids=[self_id],
        )

    def _handle_objectinfo(
        self, canonical: str, payload: dict[str, Any]
    ) -> TranslatedEvent:
        object_uuid = _text(payload, "object_uuid", "uuid")
        if not object_uuid:
            raise ValueError("ObjectInfo event has no object UUID")
        object_id = f"sl:object:{object_uuid.lower()}"
        name = _text(payload, "object_name", "name", default=object_uuid)
        if self._world.get_entity(object_id) is None:
            self._world.create_entity(entity_id=object_id, tags={"object"})
        name_comp = self._world.get_component(object_id, "name")
        if not isinstance(name_comp, NameComponent):
            self._world.add_component(
                object_id, NameComponent(entity_id=object_id, name=name)
            )
        description = _text(payload, "desc", "description")
        if description:
            desc = self._world.get_component(object_id, "description")
            if not isinstance(desc, DescriptionComponent):
                self._world.add_component(
                    object_id,
                    DescriptionComponent(entity_id=object_id, short_desc=description),
                )
            else:
                desc.short_desc = description
                desc.touch()

        comp = self._world.get_component(object_id, "sl_object")
        if not isinstance(comp, SLObjectComponent):
            comp = SLObjectComponent(entity_id=object_id, object_uuid=object_uuid)
            self._world.add_component(object_id, comp)
        owner_uuid = _text(payload, "owner_uuid")
        owner_id = _text(payload, "owner_id", "owner")
        if owner_uuid:
            comp.owner_id = f"sl:avatar:{owner_uuid.lower()}"
        elif owner_id:
            comp.owner_id = owner_id
        creator_uuid = _text(payload, "creator_uuid")
        creator_id = _text(payload, "creator_id", "creator")
        if creator_uuid:
            comp.creator_id = f"sl:avatar:{creator_uuid.lower()}"
        elif creator_id:
            comp.creator_id = creator_id
        kind = _text(payload, "kind", "object_kind")
        if kind:
            comp.kind = kind
        for field_name, keys in (
            ("touchable", ("touchable",)),
            ("sittable", ("sittable",)),
            ("script_detected", ("script_detected", "scripted")),
        ):
            parsed = _bool(payload, *keys)
            if parsed is not None:
                setattr(comp, field_name, parsed)
        comp.touch()

        parcel_id = self._current_parcel_id
        if parcel_id is not None:
            self._place(object_id, parcel_id)
        self._update_position(
            object_id,
            payload,
            region_id=self._current_region_id,
            parcel_id=parcel_id,
        )
        self._publish(
            "sl.object.seen",
            {"object_id": object_id, "object_name": name, "place_id": parcel_id},
        )

        observation_id = None
        interacted = _bool(
            payload, "touched_by_self", "sat_on_by_self", "mentioned_to_self"
        )
        if interacted:
            observation_id = self._observe(
                kind="action",
                title=f"Interacted with {name}",
                summary=f"The agent interacted with {name}.",
                participants=[self._self_entity_id] if self._self_entity_id else [],
                place_id=parcel_id,
            )
        return TranslatedEvent(
            event_type=canonical,
            bus_topic="sl.object.seen",
            entity_ids=[object_id],
            observation_id=observation_id,
        )

    def _handle_teleportcompleted(
        self, canonical: str, payload: dict[str, Any]
    ) -> TranslatedEvent:
        self_id = self._ensure_self(payload)
        region_id = self._ensure_region(payload)
        if region_id is None:
            return TranslatedEvent(
                event_type=canonical,
                entity_ids=[self_id],
                ignored_reason="TeleportCompleted event named no destination region",
            )
        self._current_region_id = region_id
        parcel_id = self._ensure_parcel(payload, region_id=region_id)
        if parcel_id is not None:
            self._current_parcel_id = parcel_id
            place_id = self._ensure_place(
                payload, parcel_id=parcel_id, region_id=region_id
            )
            self._place(self_id, parcel_id, sublocation_id=place_id)
        else:
            self._current_parcel_id = None
            self._clear_placement(self_id)
        self._update_position(
            self_id, payload, region_id=region_id, parcel_id=parcel_id
        )
        region_name = self._entity_name(region_id)
        observation_id = self._observe(
            kind="action",
            title="Teleport completed",
            summary=f"{self._entity_name(self_id)} teleported to {region_name}.",
            participants=[self_id],
            place_id=parcel_id,
        )
        self._publish(
            "sl.teleport.completed",
            {
                "avatar_id": self_id,
                "region_id": region_id,
                "region_name": region_name,
                "parcel_id": parcel_id,
            },
        )
        return TranslatedEvent(
            event_type=canonical,
            bus_topic="sl.teleport.completed",
            entity_ids=[self_id, region_id],
            observation_id=observation_id,
        )

    def _handle_friendonline(
        self, canonical: str, payload: dict[str, Any]
    ) -> TranslatedEvent:
        return self._handle_friend_presence(canonical, payload, online=True)

    def _handle_friendoffline(
        self, canonical: str, payload: dict[str, Any]
    ) -> TranslatedEvent:
        return self._handle_friend_presence(canonical, payload, online=False)

    def _handle_friend_presence(
        self, canonical: str, payload: dict[str, Any], *, online: bool
    ) -> TranslatedEvent:
        avatar_id = self._ensure_avatar(payload, online=online)
        self._publish(
            "sl.friend.presence",
            {
                "avatar_id": avatar_id,
                "avatar_name": self._entity_name(avatar_id),
                "online": online,
            },
        )
        return TranslatedEvent(
            event_type=canonical,
            bus_topic="sl.friend.presence",
            entity_ids=[avatar_id],
        )

    def _handle_appearancechanged(
        self, canonical: str, payload: dict[str, Any]
    ) -> TranslatedEvent:
        self_id = self._ensure_self(payload)
        worn = _string_list(payload, "items_worn", "worn")
        removed = _string_list(payload, "items_removed", "removed")
        status = self._world.get_component(self_id, "status")
        if isinstance(status, StatusComponent):
            parts = []
            if worn:
                parts.append(f"Worn: {', '.join(worn)}")
            if removed:
                parts.append(f"Removed: {', '.join(removed)}")
            status.notes = "; ".join(parts)
            status.touch()
        observation_id = self._observe(
            kind="action",
            title="Appearance changed",
            summary=f"{self._entity_name(self_id)} changed appearance.",
            participants=[self_id],
            place_id=self._current_parcel_id,
        )
        self._publish(
            "sl.self.appearance",
            {"avatar_id": self_id, "items_worn": worn, "items_removed": removed},
        )
        return TranslatedEvent(
            event_type=canonical,
            bus_topic="sl.self.appearance",
            entity_ids=[self_id],
            observation_id=observation_id,
        )


# ---------------------------------------------------------------------------
# The bridge
# ---------------------------------------------------------------------------


class SlWyrdBridge(BifrostBridge):
    """Own the WYRD stack for one Second Life inhabitant.

    The bridge is mind-agnostic: it reports world state and stores
    attributed observations.  It does not generate personality, speech,
    or decisions.
    """

    def __init__(
        self,
        *,
        memory_store: PersistentMemoryStore,
        world: World | None = None,
        yggdrasil: YggdrasilTree | None = None,
        bus: EventBus | None = None,
        world_store: WorldStore | None = None,
        config: SecondLifeBridgeConfig | None = None,
    ) -> None:
        self._store = memory_store
        self._world = world or World(WORLD_ID, "Second Life", bus=bus)
        if self._world.world_id != WORLD_ID:
            raise ValueError(
                f"SlWyrdBridge world_id must be {WORLD_ID!r}, "
                f"got {self._world.world_id!r}"
            )
        if getattr(self._world, "identity", None) is None:
            self._world.identify(kind="wyrd", reality="manifest")
        self._tree = yggdrasil or YggdrasilTree(self._world)
        self._oracle = PassiveOracle(self._world, memory_store, yggdrasil=self._tree)
        self._engine = WritebackEngine(memory_store, bus=bus)
        self._world_store = world_store
        self._config = config or SecondLifeBridgeConfig()
        self._translator = EventTranslator(
            self._world,
            self._tree,
            self._engine,
            bus=bus,
            config=self._config,
        )

    @classmethod
    def from_paths(
        cls,
        *,
        memory_db_path: str | Path,
        world_db_path: str | Path | None = None,
        bus: EventBus | None = None,
        config: SecondLifeBridgeConfig | None = None,
    ) -> SlWyrdBridge:
        """Build a bridge over SQLite stores, reloading a saved world if any."""
        memory_store = PersistentMemoryStore(memory_db_path)
        world_store = WorldStore(world_db_path) if world_db_path is not None else None
        world: World | None = None
        if world_store is not None and WORLD_ID in world_store.list_worlds():
            world = world_store.load(WORLD_ID)
            if bus is not None:
                world._bus = bus  # re-wire a store-loaded world to the live bus
        return cls(
            memory_store=memory_store,
            world=world,
            bus=bus,
            world_store=world_store,
            config=config,
        )

    # -- BifrostBridge surface ----------------------------------------------

    def query(self, persona_id: str, user_input: str, **kwargs: Any) -> str:
        """Answer a world question from Oracle state (no LLM involved)."""
        question = user_input.strip().lower()
        self_id = self.self_entity_id

        if "what was just said" in question or "what did" in question and "say" in question:
            said = self.what_was_just_said(limit=int(kwargs.get("limit", 5)))
            if not said:
                return "No local chat has been recorded here yet."
            return "\n".join(f"{item.title}: {item.summary}" for item in said)

        if question.startswith("where am i") or question.startswith("where is"):
            if self_id is None:
                return "I have no recorded Second Life position yet."
            where = self._oracle.where_is(self_id)
            if where is None or where.location_id is None:
                return "I have no recorded Second Life position yet."
            path = " -> ".join(where.path)
            return f"{where.location_name or where.location_id} ({where.location_id}); path: {path}"

        if "who is here" in question or "who is near" in question or "nearby" in question:
            if self_id is None:
                return "I have no recorded Second Life position yet."
            nearby = self._oracle.get_nearby(self_id)
            if not nearby:
                return "No other avatars are recorded at my current parcel."
            names = ", ".join(item.name or item.entity_id for item in nearby)
            return f"Nearby: {names}"

        packet = self.build_context_packet(
            focus_entity_ids=kwargs.get("focus_entity_ids") or ([self_id] if self_id else []),
            location_id=kwargs.get("location_id"),
        )
        return packet.formatted_for_llm

    def push_event(self, event_type: str, payload: dict[str, Any]) -> None:
        """Accept a Heimdall event through the BifrostBridge surface."""
        if event_type in {"secondlife", "second_life", "heimdall", "sl_event"}:
            self._translator.translate(payload)
        else:
            self._translator.translate(event_type, payload)

    def teardown(self) -> None:
        """Persist the ECS world if a WorldStore was configured."""
        self.save_world()

    # -- event ingestion ------------------------------------------------------

    def ingest_event(
        self,
        event_or_type: dict[str, Any] | str,
        payload: dict[str, Any] | None = None,
    ) -> TranslatedEvent:
        """Translate one Heimdall event and return its receipt."""
        return self._translator.translate(event_or_type, payload)

    def replay(self, events: Iterable[dict[str, Any]]) -> list[TranslatedEvent]:
        """Replay Heimdall events in order."""
        return self._translator.replay(events)

    def replay_file(self, path: str | Path) -> list[TranslatedEvent]:
        """Replay a JSONL/JSON Heimdall event fixture."""
        return self._translator.replay_file(path)

    # -- read surface -----------------------------------------------------------

    @property
    def world(self) -> World:
        return self._world

    @property
    def yggdrasil(self) -> YggdrasilTree:
        return self._tree

    @property
    def tree(self) -> YggdrasilTree:
        return self._tree

    @property
    def oracle(self) -> PassiveOracle:
        return self._oracle

    @property
    def writeback(self) -> WritebackEngine:
        return self._engine

    @property
    def translator(self) -> EventTranslator:
        return self._translator

    @property
    def memory_store(self) -> PersistentMemoryStore:
        return self._store

    @property
    def self_entity_id(self) -> str | None:
        return self._translator.self_entity_id

    @property
    def current_region_id(self) -> str | None:
        return self._translator.current_region_id

    @property
    def current_parcel_id(self) -> str | None:
        return self._translator.current_parcel_id

    def recent_observations(
        self,
        *,
        place_id: str | None = None,
        kind: str | None = None,
        limit: int = 5,
    ) -> list[ObservationSummary]:
        """Recent Hugin observations, optionally filtered by place/kind."""
        return self._oracle.recent_observations(
            place_id=place_id, kind=kind, limit=limit
        )

    def what_was_just_said(
        self,
        *,
        place_id: str | None = None,
        limit: int = 5,
    ) -> list[ObservationSummary]:
        """Utterances recorded at the current parcel (or *place_id*)."""
        return self._oracle.recent_observations(
            place_id=place_id if place_id is not None else self.current_parcel_id,
            kind="utterance",
            limit=limit,
        )

    def build_context_packet(
        self,
        *,
        focus_entity_ids: list[str] | None = None,
        location_id: str | None = None,
        max_observations: int = 10,
    ) -> WorldContextPacket:
        """Build the Oracle context packet for the inhabitant."""
        focus = focus_entity_ids
        if focus is None:
            focus = [self.self_entity_id] if self.self_entity_id else []
        return self._oracle.build_context_packet(
            focus_entity_ids=focus,
            location_id=location_id if location_id is not None else self.current_parcel_id,
            max_observations=max_observations,
        )

    # -- persistence -------------------------------------------------------------

    def save_world(self) -> None:
        """Save the ECS world through the configured WorldStore, if any."""
        if self._world_store is not None:
            self._world_store.save(self._world)


__all__ = [
    "GRID_ZONE_ID",
    "WORLD_ID",
    "EventTranslator",
    "SL_TOPIC_SCHEMAS",
    "SecondLifeBridgeConfig",
    "SlWyrdBridge",
    "TranslatedEvent",
    "register_sl_topics",
]
