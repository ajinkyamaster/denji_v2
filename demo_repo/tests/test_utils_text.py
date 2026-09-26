"""Slugging, word counting and truncation."""

import pytest

from app.utils.text import normalise_slug, truncate, word_count


@pytest.mark.parametrize(
    'text, expected',
    [
        pytest.param('  Mixed Case 1/Part_1  ', 'mixed-case-1-part-1', id="T-0146"),
        pytest.param('Invoice Service', 'invoice-service', id="T-0147"),
        pytest.param('ALREADY-SLUGGED', 'already-slugged', id="T-0148"),
        pytest.param('dots.and.dots', 'dots-and-dots', id="T-0149"),
        pytest.param('under_scores_here', 'under-scores-here', id="T-0150"),
        pytest.param('trailing---', 'trailing', id="T-0151"),
        pytest.param('---leading', 'leading', id="T-0152"),
        pytest.param('a b  c   d', 'a-b-c-d', id="T-0153"),
        pytest.param('Report/Worker', 'report-worker', id="T-0154"),
        pytest.param('', '', id="T-0155"),
        pytest.param('   ', '', id="T-0156"),
        pytest.param('9lives', '9lives', id="T-0157"),
        pytest.param('MixedCASE99', 'mixedcase99', id="T-0158"),
        pytest.param('slashes//double', 'slashes-double', id="T-0159"),
        pytest.param('spaces and-dashes_and/slashes', 'spaces-and-dashes-and-slashes', id="T-0160"),
        pytest.param('  spaced  ', 'spaced', id="T-0161"),
        pytest.param('one', 'one', id="T-0162"),
        pytest.param('Two Words', 'two-words', id="T-0163"),
        pytest.param('three-words-here', 'three-words-here', id="T-0164"),
        pytest.param('x/y/z', 'x-y-z', id="T-0165"),
    ],
)
def test_normalise_slug(text, expected):
    """Normalise slug."""
    assert normalise_slug(text) == expected


@pytest.mark.parametrize(
    'text, expected',
    [
        pytest.param('', 0, id="T-0166"),
        pytest.param(' ', 0, id="T-0167"),
        pytest.param('one', 1, id="T-0168"),
        pytest.param('one two', 2, id="T-0169"),
        pytest.param('one  two   three', 3, id="T-0170"),
        pytest.param('a b c d e', 5, id="T-0171"),
        pytest.param('\ttab\tseparated\t', 2, id="T-0172"),
        pytest.param('trailing ', 1, id="T-0173"),
        pytest.param(' leading', 1, id="T-0174"),
        pytest.param('many many many many many', 5, id="T-0175"),
        pytest.param('x', 1, id="T-0176"),
        pytest.param('x y', 2, id="T-0177"),
        pytest.param('x y z', 3, id="T-0178"),
        pytest.param('x y z w', 4, id="T-0179"),
        pytest.param('x y z w v', 5, id="T-0180"),
        pytest.param('line\nbreak', 2, id="T-0181"),
        pytest.param('line\n\nbreak', 2, id="T-0182"),
        pytest.param('a-b c-d', 2, id="T-0183"),
        pytest.param('  spaced  out  ', 2, id="T-0184"),
        pytest.param('unicode café count', 3, id="T-0185"),
    ],
)
def test_word_count(text, expected):
    """Word count."""
    assert word_count(text) == expected


@pytest.mark.parametrize(
    'text, limit, expected',
    [
        pytest.param('abcdef', 3, '...', id="T-0186"),
        pytest.param('abcdef', 0, '', id="T-0187"),
        pytest.param('abcdef', 4, 'a...', id="T-0188"),
        pytest.param('abcdef', 6, 'abcdef', id="T-0189"),
        pytest.param('abcdef', 10, 'abcdef', id="T-0190"),
        pytest.param('', 0, '', id="T-0191"),
        pytest.param('abc', 2, '..', id="T-0192"),
        pytest.param('abc', 1, '.', id="T-0193"),
        pytest.param('a much longer sentence to truncate', 12, 'a much lo...', id="T-0194"),
        pytest.param('a much longer sentence to truncate', 13, 'a much lon...', id="T-0195"),
        pytest.param('twenty-five characters', 20, 'twenty-five chara...', id="T-0196"),
        pytest.param('twenty-five characters', 25, 'twenty-five characters', id="T-0197"),
        pytest.param('twenty-five characters', 26, 'twenty-five characters', id="T-0198"),
        pytest.param('short', 5, 'short', id="T-0199"),
        pytest.param('short', 100, 'short', id="T-0200"),
        pytest.param('0123456789', 8, '01234...', id="T-0201"),
        pytest.param('0123456789', 3, '...', id="T-0202"),
        pytest.param('0123456789', 2, '..', id="T-0203"),
        pytest.param('unicode café', 6, 'uni...', id="T-0204"),
        pytest.param('unicode café', 4, 'u...', id="T-0205"),
    ],
)
def test_truncate(text, limit, expected):
    """Truncate."""
    assert truncate(text, limit) == expected


