"""M6 scope T6.4 + ADR-007: mutual social invitation flow."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from otherworld.models.persona import PersonaObject, TraitVector, VoiceProfile
from otherworld.persona.invitations import (
    NoPendingInvitationError,
    NoPersonaError,
    accept_seeded_relationship,
    propose_seeded_relationship,
)
from otherworld.persona.service import save_persona

NOW = datetime.now(UTC)


def _persona(owner_id: uuid.UUID) -> PersonaObject:
    return PersonaObject(
        id=uuid.uuid4(), owner_id=owner_id, version=1,
        voice=VoiceProfile(verbosity=0.4, formality=0.5, humour_style="dry", profanity_baseline=0.1),
        values=TraitVector(), source_methods=["A"], created_at=NOW,
    )


async def test_propose_adds_an_unaccepted_claim_to_only_the_proposers_persona(db_session):
    proposer_id, counterpart_id = uuid.uuid4(), uuid.uuid4()
    await save_persona(db_session, _persona(proposer_id))

    updated = await propose_seeded_relationship(db_session, proposer_id, counterpart_id, "friend")

    assert len(updated.social) == 1
    assert updated.social[0].counterpart_owner_id == counterpart_id
    assert updated.social[0].claimed_bond == "friend"
    assert updated.social[0].mutual_accepted is False
    assert updated.version == 2  # a real persona edit, not a side-channel mutation


async def test_propose_requires_the_proposer_to_have_a_persona(db_session):
    with pytest.raises(NoPersonaError):
        await propose_seeded_relationship(db_session, uuid.uuid4(), uuid.uuid4(), "friend")


async def test_re_proposing_replaces_rather_than_duplicates(db_session):
    proposer_id, counterpart_id = uuid.uuid4(), uuid.uuid4()
    await save_persona(db_session, _persona(proposer_id))

    await propose_seeded_relationship(db_session, proposer_id, counterpart_id, "acquaintance")
    updated = await propose_seeded_relationship(db_session, proposer_id, counterpart_id, "close")

    assert len(updated.social) == 1
    assert updated.social[0].claimed_bond == "close"


async def test_accept_confirms_the_proposer_and_mirrors_onto_the_accepter(db_session):
    proposer_id, accepter_id = uuid.uuid4(), uuid.uuid4()
    await save_persona(db_session, _persona(proposer_id))
    await save_persona(db_session, _persona(accepter_id))
    await propose_seeded_relationship(db_session, proposer_id, accepter_id, "friend")

    proposer_final, accepter_final = await accept_seeded_relationship(db_session, accepter_id, proposer_id)

    assert proposer_final.social[0].mutual_accepted is True
    assert proposer_final.social[0].accepted_at is not None
    assert accepter_final.social[0].counterpart_owner_id == proposer_id
    assert accepter_final.social[0].claimed_bond == "friend"
    assert accepter_final.social[0].mutual_accepted is True


async def test_accept_rejects_unilateral_seeding_with_no_prior_proposal(db_session):
    """ADR-007's core guarantee: accepting is never a way to create a claim
    that was never actually proposed by the other party."""
    a, b = uuid.uuid4(), uuid.uuid4()
    await save_persona(db_session, _persona(a))
    await save_persona(db_session, _persona(b))

    with pytest.raises(NoPendingInvitationError):
        await accept_seeded_relationship(db_session, accepter_owner_id=b, proposer_owner_id=a)


async def test_accept_cannot_be_replayed_after_already_being_accepted(db_session):
    proposer_id, accepter_id = uuid.uuid4(), uuid.uuid4()
    await save_persona(db_session, _persona(proposer_id))
    await save_persona(db_session, _persona(accepter_id))
    await propose_seeded_relationship(db_session, proposer_id, accepter_id, "friend")
    await accept_seeded_relationship(db_session, accepter_id, proposer_id)

    with pytest.raises(NoPendingInvitationError):
        await accept_seeded_relationship(db_session, accepter_id, proposer_id)
