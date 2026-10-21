"""The replay on the real Digital Lending repeal: trusted, switched on time, no stale answers."""

from datetime import date

from app.replay import gold_timeline, run_replay
from tests.test_linking import NEW_URL, OLD_URL, corpus  # noqa: F401  (pytest fixture)


def test_a_true_rbi_repeal_is_auto_trusted_and_never_answers_stale(corpus, tmp_path) -> None:
    settings, service, old, kfs, new = corpus
    labels = {"directions_in_force": {}, "successors": {}, "explicit_links": {f"{OLD_URL} -> {NEW_URL}": True}}

    report = run_replay(settings.data_dir, tmp_path / "replay", labels, today=date(2025, 12, 1))

    assert report["auto_trust_precision"]["value"] == 1.0
    assert report["successor_links_from_rbi_text"]["precision"]["value"] == 1.0
    assert report["successor_links_from_rbi_text"]["recall_over_rbi_statements_judged_true"]["value"] == 1.0
    assert report["stale_answer_rate"]["evidence"]["numerator"] == 0 and report["stale_answer_rate"]["evidence"]["denominator"] > 0
    assert report["time_to_switch_days"]["max"] == 0
    assert report["failures"] == []


def test_a_wrong_auto_trust_shows_up_in_its_precision(corpus, tmp_path) -> None:
    settings, service, old, kfs, new = corpus
    labels = {"directions_in_force": {}, "successors": {}, "explicit_links": {f"{OLD_URL} -> {NEW_URL}": False}}

    report = run_replay(settings.data_dir, tmp_path / "replay", labels, today=date(2025, 12, 1))

    assert report["auto_trust_precision"]["value"] == 0.0


def test_the_gold_timeline_ends_a_repealed_rule_when_its_successor_takes_effect(corpus) -> None:
    settings, service, old, kfs, new = corpus
    documents = service.manifest.all()
    labels = {"explicit_links": {f"{OLD_URL} -> {NEW_URL}": True}}

    timeline, successors = gold_timeline(documents, labels, today=date(2025, 12, 1))

    assert successors == {old.document_id: new.document_id}
    assert timeline.end[old.document_id] == date(2025, 11, 1)  # the successor's effective date in this fixture
    assert timeline.in_force(old.document_id, date(2025, 10, 31)) and not timeline.in_force(old.document_id, date(2025, 11, 1))
