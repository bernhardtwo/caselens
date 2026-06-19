from caselens.rag.chunking import chunk_markdown


def test_sections_become_chunks_with_labels():
    md = "# Title\n\n## Alpha\nAlpha body text.\n\n## Beta\nBeta body text.\n"
    chunks = chunk_markdown(md, chunk_size=900, chunk_overlap=100)
    assert [c.section for c in chunks] == ["Alpha", "Beta"]
    assert [c.ordinal for c in chunks] == [0, 1]
    assert chunks[0].text == "Alpha body text."


def test_preamble_under_title_is_kept():
    md = "# Title\nIntro under title.\n\n## Alpha\nAlpha body.\n"
    chunks = chunk_markdown(md, chunk_size=900, chunk_overlap=100)
    assert chunks[0].section == "Title"
    assert "Intro under title." in chunks[0].text


def test_long_section_splits_with_overlap():
    body = "".join(str(i % 10) for i in range(2000))
    chunks = chunk_markdown(f"## Big\n{body}\n", chunk_size=900, chunk_overlap=100)
    assert all(c.section == "Big" for c in chunks)
    assert all(len(c.text) <= 900 for c in chunks)
    assert [c.text for c in chunks] == [body[0:900], body[800:1700], body[1600:2000]]


def test_empty_input_yields_no_chunks():
    assert chunk_markdown("", chunk_size=900, chunk_overlap=100) == []
