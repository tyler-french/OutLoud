from outloud.tts import get_available_voices, split_into_chunks


def test_split_into_chunks_short_text():
    text = "Hello world. This is a test."
    chunks = split_into_chunks(text)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_split_into_chunks_long_text():
    text = "This is sentence one. " * 50
    chunks = split_into_chunks(text, max_chars=100)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 100 or " " not in chunk


def test_split_into_chunks_respects_sentence_boundaries():
    text = "First sentence here. Second sentence here. Third sentence here."
    chunks = split_into_chunks(text, max_chars=50)

    for chunk in chunks:
        assert not chunk.startswith(" ")
        assert not chunk.endswith(" ")


def test_split_into_chunks_handles_abbreviations():
    text = "Dr. Smith went to the store. Mr. Jones followed."
    chunks = split_into_chunks(text, max_chars=1000)
    assert len(chunks) == 1


def test_get_available_voices():
    voices = get_available_voices()

    assert len(voices) > 0
    assert all("id" in v for v in voices)
    assert all("name" in v for v in voices)
    assert all("gender" in v for v in voices)
    assert all("lang" in v for v in voices)


def test_voice_ids_are_unique():
    voices = get_available_voices()
    ids = [v["id"] for v in voices]
    assert len(ids) == len(set(ids))
