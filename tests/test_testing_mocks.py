def test_fixture(mock_stats):
    from aka_stats import Stats

    assert Stats.__name__ == "MyMockStats"

    with Stats() as stat:
        for _ in range(3):
            stat("test_counter", 1)

    assert len(mock_stats) == 3
