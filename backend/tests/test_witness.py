import hashlib

import pytest

from app.domain import Claim, ClaimKind, ClaimStatus, Keyframe, Safety, Turn, WitnessStatus
from app.meta.shapes import box_object
from app.witness import gate, pixels, words

SI_TURN = Turn(id="t1", start=10.0, end=18.0, text="මේ තියෙන්නේ ප්‍රධාන ස්විච් පෙට්ටිය. කරන්ට් ගියොත්, මේ මූඩිය ඇරලා රතු එක උඩට තල්ලු කරන්න.", lang="si")
EN_TURN = Turn(id="t2", start=0.0, end=6.0, text="Switch the pump on every morning at six, for twenty minutes.", lang="en")
KW = dict(min_chars=6, slack_before=2.0, slack_after=4.0)


def claim(**kw) -> Claim:
    base = dict(id="c1", recording_id="r1", kind=ClaimKind.step, task_key="pump", title_en="Pump", text_en="Run the pump.", quote="every morning at six", turn_id="t2", time=3.0)
    base.update(kw)
    return Claim(**base)


class TestWords:
    def test_exact_english(self):
        assert words.check_quote("every morning at six", EN_TURN, 3.0, **KW).status == WitnessStatus.passed

    def test_formatting_differences_are_harmless(self):
        assert words.check_quote("  Every   MORNING at six,  ", EN_TURN, 3.0, **KW).status == WitnessStatus.passed

    def test_sinhala_with_zero_width_joiner(self):
        # ප්‍ර uses U+200D; a quote typed without it still matches.
        assert words.check_quote("ප්රධාන ස්විච් පෙට්ටිය", SI_TURN, 12.0, **KW).status == WitnessStatus.passed

    def test_paraphrase_fails_and_shows_closest(self):
        w = words.check_quote("every day at six", EN_TURN, 3.0, **KW)
        assert w.status == WitnessStatus.failed
        assert "morning" in w.evidence["closest"] or "every" in w.evidence["closest"]

    def test_right_words_wrong_moment(self):
        assert words.check_quote("every morning at six", EN_TURN, 30.0, **KW).status == WitnessStatus.disagree

    def test_too_short(self):
        assert words.check_quote("at", EN_TURN, 3.0, **KW).status == WitnessStatus.failed

    def test_missing_turn(self):
        assert words.check_quote("anything at all", None, 3.0, **KW).status == WitnessStatus.failed


class TestPixels:
    kf = Keyframe(id="kf1", time=3.0, path="kf/a.jpg", width=1000, height=500)

    def test_point_inside_confident_mask(self):
        objs = [box_object("1", 100, 100, 300, 300, 1000, 500, 0.9)]
        c = claim(object_noun="water pump", point=(0.2, 0.4), keyframe_id="kf1")
        assert pixels.check_pixels(c, self.kf, objs, min_confidence=0.5).status == WitnessStatus.passed

    def test_point_outside_every_mask(self):
        objs = [box_object("1", 100, 100, 300, 300, 1000, 500, 0.9)]
        c = claim(object_noun="water pump", point=(0.8, 0.8))
        assert pixels.check_pixels(c, self.kf, objs, min_confidence=0.5).status == WitnessStatus.disagree

    def test_low_confidence(self):
        objs = [box_object("1", 100, 100, 300, 300, 1000, 500, 0.3)]
        c = claim(object_noun="water pump", point=(0.2, 0.4))
        assert pixels.check_pixels(c, self.kf, objs, min_confidence=0.5).status == WitnessStatus.disagree

    def test_nothing_found(self):
        c = claim(object_noun="water pump", point=(0.2, 0.4))
        assert pixels.check_pixels(c, self.kf, [], min_confidence=0.5).status == WitnessStatus.failed

    def test_no_object_is_skipped(self):
        assert pixels.check_pixels(claim(), self.kf, [], min_confidence=0.5).status == WitnessStatus.skipped

    def test_no_point_but_single_match(self):
        objs = [box_object("1", 100, 100, 300, 300, 1000, 500, 0.95)]
        assert pixels.check_pixels(claim(object_noun="pump"), self.kf, objs, min_confidence=0.5).status == WitnessStatus.passed

    def test_no_point_ambiguous(self):
        objs = [box_object("1", 100, 100, 300, 300, 1000, 500, 0.95), box_object("2", 500, 100, 700, 300, 1000, 500, 0.9)]
        assert pixels.check_pixels(claim(object_noun="pump"), self.kf, objs, min_confidence=0.5).status == WitnessStatus.disagree


class TestGate:
    def test_policy_is_pinned(self):
        digest = hashlib.sha256(gate.POLICY_PATH.read_bytes()).hexdigest()
        assert digest == gate.POLICY_SHA256

    def test_tampered_policy_refuses(self, monkeypatch):
        gate.policy.cache_clear()
        monkeypatch.setattr(gate, "POLICY_SHA256", "0" * 64)
        with pytest.raises(gate.PolicyTampered):
            gate.policy()
        monkeypatch.undo()
        gate.policy.cache_clear()
        assert gate.policy()["version"] == 1

    def test_required_witnesses(self):
        names = lambda c: [n.value for n in gate.required_witnesses(c)]  # noqa: E731
        assert names(claim()) == ["words"]
        assert names(claim(object_noun="pump", safety=Safety.water)) == ["words", "pixels"]
        assert names(claim(object_noun="breaker", safety=Safety.electricity)) == ["words", "pixels", "reading"]
        assert names(claim(safety=Safety.electricity)) == ["words", "reading"]

    def test_medical_is_blocked_in_english_and_sinhala(self):
        status, reason = gate.decide(claim(text_en="Give her two tablets of medicine", quote="medicine at night"), [])
        assert status == ClaimStatus.blocked and "medical" in reason
        status, _ = gate.decide(claim(text_en="Night routine", text_si="රෑට බෙහෙත් දෙන්න", quote="something else"), [])
        assert status == ClaimStatus.blocked

    def test_tablet_device_is_not_medical(self):
        w = words.check_quote("every morning at six", EN_TURN, 3.0, **KW)
        status, _ = gate.decide(claim(text_en="Charge the tablet every morning"), [w])
        assert status == ClaimStatus.verified

    def test_missing_witness_needs_review(self):
        w = words.check_quote("every morning at six", EN_TURN, 3.0, **KW)
        status, reason = gate.decide(claim(object_noun="pump", safety=Safety.water), [w])
        assert status == ClaimStatus.needs_review and "pixels" in reason


def test_mixed_script_sinhala_goes_to_review():
    """Found with a real Muse Spark Open run: a Kannada letter inside a Sinhala translation."""
    from app.domain import Claim, ClaimKind, Witness, WitnessName, WitnessStatus

    good = Claim(id="c1", recording_id="r", kind=ClaimKind.step, task_key="main_switch", title_en="Main switch box", text_en="Come here first.", text_si="කරන්ට් ගියොත් මුලින්ම මෙතනට එන්න.", quote="කරන්ට් ගියොත් මුලින්ම මෙතනට එන්න", turn_id="t1", time=1.0)
    bad = good.model_copy(update={"text_si": "කರೆන්ට් ගියොත් මුලින්ම මෙතනට එන්න."})
    words_ok = [Witness(name=WitnessName.words, status=WitnessStatus.passed, detail="ok")]
    assert gate.decide(good, words_ok)[0].value == "verified"
    status, why = gate.decide(bad, words_ok)
    assert status.value == "needs_review" and "another script" in why


def test_blocked_text_checks_whole_sentences():
    """Used to explain sentences no fact came from (the review's "Not used" list)."""
    assert gate.blocked_text("Amma takes half a tablet of her pressure medicine every morning.")
    assert gate.blocked_text("අම්මට උදේට බෙහෙත් දෙන්න.")
    assert not gate.blocked_text("The electricity bill comes around the tenth of every month.")
    assert not gate.blocked_text("")


@pytest.mark.parametrize(
    "text",
    [
        "Which tablets does Seetha Amma take after dinner?",  # missed before: the held-out help set, 29 October
        "Her painkillers are on the top shelf.",
        "One capsule after breakfast.",
        "Put the eye drops in Amma's eyes at night.",
        "අම්මා හැමදාම රෑ අටට ප්‍රෙෂර් පෙත්ත බොනවා.",  # 'pill' in Sinhala is පෙත්ත / පෙති
        "අම්මා රෑට ප්‍රෙෂර් පෙති කීයක් බොනවද?",
        "තාත්තා උදේට සීනි පෙත්තක් බොනවා.",
    ],
)
def test_more_ways_of_naming_medicine_are_refused(text):
    assert gate.blocked_text(text)


@pytest.mark.parametrize(
    "text",
    [
        "Charge the tablet every morning.",  # a tablet computer
        "If the water pressure drops, switch the pump off.",
        "Pour the kithul syrup over the curd.",
        "පාන් පෙති දෙකක් ටෝස්ට් කරන්න.",  # පෙති also means slices
        "මෝටරයේ සිසිලන පෙති පිරිසිදු කරන්න.",  # and the fins of a motor
        "ලූනු පෙති කපලා තියන්න.",
    ],
)
def test_the_same_words_in_other_senses_are_not(text):
    assert not gate.blocked_text(text)
