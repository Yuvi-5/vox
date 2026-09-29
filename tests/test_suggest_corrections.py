import vox_core as core


def sug(original, edited, **kw):
    return core.suggest_corrections(original, edited, **kw)


def test_single_word_swap():
    assert sug("send it to Minhaj today", "send it to Minhajuddin today") == [("Minhaj", "Minhajuddin")]


def test_lowercase_to_brand_spelling_in_the_middle_of_a_sentence():
    assert sug("we shipped vox to friends", "we shipped Vox to friends") == [("vox", "Vox")]


def test_capital_at_start_of_sentence_is_grammar_not_a_correction():
    assert sug("send it today", "Send it today") == []
    assert sug("done. send it today", "done. Send it today") == []


def test_two_word_swap_becomes_one_pair():
    assert sug("ask grok cloud about it", "ask Groq Cloud about it") == [("grok cloud", "Groq Cloud")]


def test_punctuation_next_to_the_word_is_ignored():
    assert sug("thanks, Minhaj.", "thanks, Minhajuddin.") == [("Minhaj", "Minhajuddin")]


def test_several_fixes_in_one_edit():
    # neighbouring changed words are one swap, so "acme corp" is offered whole
    assert sug("call jon at acme corp", "call John at ACME Corp") == [("jon", "John"), ("acme corp", "ACME Corp")]


def test_inserted_or_deleted_words_are_not_replacements():
    assert sug("send it today", "please send it today") == []
    assert sug("please send it today", "send it today") == []


def test_long_rewrites_are_not_suggested():
    assert sug("one two three four five", "alpha beta gamma delta epsilon") == []
    assert sug("one two three four five", "alpha beta gamma delta epsilon", max_words=5) == [
        ("one two three four five", "alpha beta gamma delta epsilon")]


def test_one_letter_words_are_skipped():
    assert sug("meet at a cafe", "meet at 5 cafe") == []


def test_no_change_and_empty_inputs():
    assert sug("same text", "same text") == []
    assert sug("", "") == []
    assert sug(None, "x") == []


def test_no_duplicate_pairs():
    assert sug("vox and vox", "Vox and Vox") == [("vox", "Vox")]
