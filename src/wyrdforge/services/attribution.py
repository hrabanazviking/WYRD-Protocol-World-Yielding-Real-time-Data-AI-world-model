"""attribution.py — Phase C3 provenance enforcement for utterances.

Doc 04's attributed-utterance rule, promoted from bridge practice to
engine law (roadmap §2.5 / §5.2): an observation that carries someone's
words — ``observation_kind == "utterance"`` — is only meaningful memory
when the engine knows WHOSE words they are. An unattributed utterance
promoted toward canonical would become a false "fact" carrying the
engine's authority, and its text would enter prompts with no speaker
to hold it as data.

Attribution, in terms of the record's existing fields, is either:

* an explicit speaker — ``ObservationPayload.speaker_id`` names the
  entity whose words the observation carries; or
* identified participants — ``ObservationPayload.participants`` is
  non-empty, so the parties to the utterance are known even when no
  single speaker is singled out.

Non-utterance observations (actions, tool results, world events, code
events, emotion signals) are system/engine records, not someone's
words: they are always "attributed" for this rule and keep their
existing write path untouched.

Phase D2 extends the same rule to ``sensation``-kind observations
(roadmap §7: sensation transitions arrive as observations, provenance
mandatory): a sensation is someone's *experience* exactly as an
utterance is someone's words, so an unattributed sensation observation
is refused the same way — the "speaker" of a felt sensation is the
embodied feeler; of a reported sensation, the reporter.

Two gates enforce the rule:

1. the writeback boundary (:class:`WritebackEngine`) refuses to build
   or write an unattributed utterance — see
   :func:`require_attributed_observation`;
2. the promotion gate (:class:`MemoryPromoter`) never promotes an
   unattributed utterance, however it reached the store (written
   before C3, or added directly via ``store.add``).
"""
from __future__ import annotations

from wyrdforge.models.memory import ObservationKind, ObservationRecord


class UnattributedUtteranceError(ValueError):
    """An utterance observation was offered with no speaker attribution.

    Raised at the writeback boundary BEFORE anything is written: the
    refusal leaves zero records behind and does not consume a
    process_turn idempotency key, so the caller may retry the same
    turn with attribution supplied.
    """


def observation_speaker(record: ObservationRecord) -> str | None:
    """The record's explicit speaker id, or None.

    Whitespace-only speaker ids count as no speaker.
    """
    speaker = record.content.structured_payload.speaker_id
    if speaker is None or not speaker.strip():
        return None
    return speaker


# Kinds carrying someone's words or experience: gated by the rule.
# (Utterances since C3; sensations since D2 — same doctrine.)
_ATTRIBUTION_GATED_KINDS = (ObservationKind.UTTERANCE, ObservationKind.SENSATION)


def is_attributed_observation(record: object) -> bool:
    """True when *record* satisfies the C3 attribution rule.

    Only utterance- and sensation-kind :class:`ObservationRecord`\\ s
    are subject to the rule; every other record (and every
    non-observation) is attributed by construction.
    """
    if not isinstance(record, ObservationRecord):
        return True
    payload = record.content.structured_payload
    if payload.observation_kind not in _ATTRIBUTION_GATED_KINDS:
        return True
    if observation_speaker(record) is not None:
        return True
    return any(p.strip() for p in payload.participants)


def require_attributed_observation(record: ObservationRecord) -> None:
    """Raise :class:`UnattributedUtteranceError` if *record* is an
    unattributed utterance or sensation; return None otherwise."""
    if not is_attributed_observation(record):
        if record.content.structured_payload.observation_kind == ObservationKind.SENSATION:
            raise UnattributedUtteranceError(
                "refusing to write an unattributed sensation observation: "
                "a sensation must carry a feeler or reporter (speaker_id) "
                "or identified participants — unattributed sensations may "
                "not enter memory (Phase C3 provenance enforcement, "
                "extended to sensations by Phase D2)"
            )
        raise UnattributedUtteranceError(
            "refusing to write an unattributed utterance observation: "
            "an utterance must carry a speaker (speaker_id) or "
            "identified participants — unattributed utterances may not "
            "enter memory (Phase C3 provenance enforcement)"
        )
