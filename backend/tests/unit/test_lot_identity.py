from hyc_domain.lots import LotIdentity, LotIdentityStatus, can_merge


def test_lot_identity_nfkc_trim_and_missing_component_is_provisional() -> None:
    canonical = LotIdentity("v1", " ＬＯＴ-１ ", "2026-01-01", "A")
    key, status = canonical.key_and_status()
    assert key == "LOT-1"
    assert status is LotIdentityStatus.CANONICAL
    assert LotIdentity("v1", "LOT", None, "A").key_and_status() == (
        "LOT",
        LotIdentityStatus.CANONICAL,
    )
    assert LotIdentity("v1", None, "2026-01-01", "A").key_and_status()[1] is (
        LotIdentityStatus.PROVISIONAL
    )
    assert LotIdentity("v2", "LOT", None, None).key_and_status()[1] is (
        LotIdentityStatus.CONFLICT_REVIEW
    )


def test_conflict_merge_needs_dual_roles_reason_and_expected_version() -> None:
    assert can_merge(
        status=LotIdentityStatus.CONFLICT_REVIEW,
        expected_version=2,
        current_version=2,
        lead_actor_id="lead-1",
        admin_actor_id="admin-1",
        reason="verified duplicate",
    )
    assert not can_merge(
        status=LotIdentityStatus.CONFLICT_REVIEW,
        expected_version=1,
        current_version=2,
        lead_actor_id="lead-1",
        admin_actor_id="admin-1",
        reason="x",
    )
    assert not can_merge(
        status=LotIdentityStatus.CONFLICT_REVIEW,
        expected_version=2,
        current_version=2,
        lead_actor_id="same-person",
        admin_actor_id="same-person",
        reason="x",
    )
