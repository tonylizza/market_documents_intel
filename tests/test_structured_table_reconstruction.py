"""Pure tests for `services.structured_table_reconstruction` (Track 7C.4).

Fixtures are literal `CanonicalBlock.raw_text` values pulled directly from
the real ACT PDFs (ned_remuneration_policy_table 2020 p.105,
total_remuneration_outcomes 2020 p.102), the same real-corpus text used to
develop and validate this module -- not paraphrased examples.
"""

import uuid

from market_documents.models.enums import StructuredCellStatus, StructuredTableReconstructionStatus
from market_documents.services.structured_table_config import NED_REMUNERATION_POLICY_TABLE, TOTAL_REMUNERATION_OUTCOMES
from market_documents.services.structured_table_reconstruction import TableSourceBlock, reconstruct_table


def _block(order, y0, text, page=1):
    return TableSourceBlock(id=uuid.uuid4(), page_number=page, block_order=order, y0=y0, text=text)


# Real 2020 NED table page (ACT, p.105), verbatim `raw_text` per block.
_NED_2020_BLOCKS = [
    _block(21, 306.9, "Non-executive Directors’ 2020 remuneration \n"),
    _block(
        22, 323.3,
        "The following table sets out the fees for the period 1 January 2020 to 31 December 2020 approved by means of majority vote \n"
        "during the AGM: \n",
    ),
    _block(23, 355.4, "Current \n"),
    _block(24, 366.4, "2020\n(R)\n"),
    _block(25, 355.4, "Proposed \n"),
    _block(26, 366.4, "2021 \n(R)\n"),
    _block(27, 355.4, "Recommended\n"),
    _block(28, 366.4, " increase\n"),
    _block(29, 377.4, "(%)\n"),
    _block(30, 395.3, "Main Board (annualised retainer fee)\nChairman\n1 329 240\n1 375 763\n3.5\nDeputy Chairman\n997 713\n1 032 633\n3.5\nMember\n248 188\n256 875\n3.5\n"),
    _block(31, 451.3, "Subsidiary board (per meeting)\nChairman\n22 572\n23 362\n3.5\nMember\n16 615\n17 197\n3.5\n"),
    _block(37, 712.1, "ICT Steering Committee (per meeting)\nChairperson*\n22 572\nMember\n16 615\n17 197\n3.5\n"),
    _block(38, 758.3, "* \t\nThe Chairperson is currently an Executive Director and does not receive fees.\n"),
    _block(39, 276.3, "*\t\n2019 STI includes Sign-on Retention Bonus.\n"),  # unrelated, above heading -- must be excluded
]

# Real 2020 total_remuneration_outcomes page (ACT, p.102), verbatim.
_OUTCOMES_2020_BLOCKS = [
    _block(29, 369.3, "Total remuneration outcomes\nSingle figure remuneration (R’000)\n"),
    _block(40, 483.9, "Executive directors\n"),
    _block(41, 502.7, "A Banderker1\n4 781 364\n1 148 9041\n435 788\n101 096\n3 242 207\n2 526 786\n1 750 000\n2 400 000 10 209 360\n6 176 786\n"),
    _block(42, 515.2, "W Britz\n3 975 310\n3 828 863\n394 235\n360 935 Waived fee Waived fee\n–\n–\n4 369 545\n4 189 798\n"),
    _block(43, 527.7, "H Boonzaaier \n3 061 646\n2 956 130\n276 436\n244 144\n1 755 613\n1 684 924\n1 750 000\n1 000 000\n6 843 695\n5 885 198\n"),
    _block(44, 540.1, "S Mmakau2\n3 347 678\n2 046 861\n323 939\n195 981\n1 479 066\n2 505 7542\n875 000\n–\n6 025 683\n4 748 597\nTOTAL\n15 165 998\n9 980 758\n1 430 398\n902 156\n6 476 886\n6 717 464\n5 025 000\n2 756 000 27 448 283 21 000 379\n"),
    _block(45, 570.7, "1 \x07\t\nA Banderker joined 1 April 2019 figures are prorated.\n2\t\nS Mmakau: 2019 STI includes sign on retention bonus\n"),
]


def test_no_match_returns_none():
    blocks = [_block(0, 0.0, "Some unrelated page content\n")]
    assert reconstruct_table(blocks, NED_REMUNERATION_POLICY_TABLE) is None


def test_ned_reconstruction_row_and_cell_values():
    result = reconstruct_table(_NED_2020_BLOCKS, NED_REMUNERATION_POLICY_TABLE)
    assert result is not None
    assert result.reconstruction_status == StructuredTableReconstructionStatus.CLEAN
    labels = [(r.category_label, r.source_label) for r in result.rows]
    assert labels == [
        ("Main Board (annualised retainer fee)", "Chairman"),
        ("Main Board (annualised retainer fee)", "Deputy Chairman"),
        ("Main Board (annualised retainer fee)", "Member"),
        ("Subsidiary board (per meeting)", "Chairman"),
        ("Subsidiary board (per meeting)", "Member"),
        ("ICT Steering Committee (per meeting)", "Chairperson"),
        ("ICT Steering Committee (per meeting)", "Member"),
    ]

    chairman = result.rows[0]
    assert [c.raw_value for c in chairman.cells] == ["1 329 240", "1 375 763", "3.5"]
    assert [c.cell_status for c in chairman.cells] == [StructuredCellStatus.NUMERIC] * 3
    assert chairman.cells[0].parsed_numeric_value == 1329240.0


def test_ned_nil_cells_are_missing_not_zero():
    result = reconstruct_table(_NED_2020_BLOCKS, NED_REMUNERATION_POLICY_TABLE)
    ict_chair = next(r for r in result.rows if r.source_label == "Chairperson" and "ICT" in r.category_label)
    assert ict_chair.row_marker == "*"
    assert [c.cell_status for c in ict_chair.cells] == [
        StructuredCellStatus.NUMERIC, StructuredCellStatus.MISSING, StructuredCellStatus.MISSING,
    ]
    assert ict_chair.cells[1].raw_value is None


def test_ned_footnote_excludes_unrelated_out_of_region_footnote():
    result = reconstruct_table(_NED_2020_BLOCKS, NED_REMUNERATION_POLICY_TABLE)
    assert [(f.marker, f.text) for f in result.footnotes] == [
        ("*", "The Chairperson is currently an Executive Director and does not receive fees."),
    ]


def test_outcomes_reconstruction_row_values_and_footnote_markers():
    result = reconstruct_table(_OUTCOMES_2020_BLOCKS, TOTAL_REMUNERATION_OUTCOMES)
    assert result is not None
    assert [r.source_label for r in result.rows] == ["A Banderker", "W Britz", "H Boonzaaier", "S Mmakau", "TOTAL"]

    banderker = result.rows[0]
    assert banderker.row_marker == "1"
    assert [c.raw_value for c in banderker.cells] == [
        "4 781 364", "1 148 904", "435 788", "101 096", "3 242 207",
        "2 526 786", "1 750 000", "2 400 000", "10 209 360", "6 176 786",
    ]
    assert banderker.cells[1].footnote_marker == "1"  # glued footnote digit split off the number

    mmakau = result.rows[3]
    assert mmakau.row_marker == "2"
    assert mmakau.cells[5].raw_value == "2 505 754"
    assert mmakau.cells[5].footnote_marker == "2"


def test_outcomes_dash_waived_fee_and_zero_are_distinct_statuses():
    result = reconstruct_table(_OUTCOMES_2020_BLOCKS, TOTAL_REMUNERATION_OUTCOMES)
    britz = result.rows[1]
    statuses = [c.cell_status for c in britz.cells]
    assert statuses == [
        StructuredCellStatus.NUMERIC, StructuredCellStatus.NUMERIC, StructuredCellStatus.NUMERIC, StructuredCellStatus.NUMERIC,
        StructuredCellStatus.TEXT_VALUE, StructuredCellStatus.TEXT_VALUE,  # "Waived fee" x2
        StructuredCellStatus.NIL_DASH, StructuredCellStatus.NIL_DASH,
        StructuredCellStatus.NUMERIC, StructuredCellStatus.NUMERIC,
    ]
    assert britz.cells[4].raw_value == "Waived fee"
    assert britz.cells[4].parsed_numeric_value is None
    assert britz.cells[6].raw_value == "–"
    assert britz.cells[6].parsed_numeric_value is None


def test_outcomes_total_row_is_terminal_and_splits_glued_values():
    result = reconstruct_table(_OUTCOMES_2020_BLOCKS, TOTAL_REMUNERATION_OUTCOMES)
    total_row = result.rows[-1]
    assert total_row.source_label == "TOTAL"
    assert [c.raw_value for c in total_row.cells] == [
        "15 165 998", "9 980 758", "1 430 398", "902 156", "6 476 886",
        "6 717 464", "5 025 000", "2 756 000", "27 448 283", "21 000 379",
    ]


def test_outcomes_footnote_block_splits_into_two_footnotes():
    result = reconstruct_table(_OUTCOMES_2020_BLOCKS, TOTAL_REMUNERATION_OUTCOMES)
    assert [(f.marker, f.text) for f in result.footnotes] == [
        ("1", "A Banderker joined 1 April 2019 figures are prorated."),
        ("2", "S Mmakau: 2019 STI includes sign on retention bonus"),
    ]


def test_outcomes_na_token_recognized_as_not_applicable():
    blocks = [
        _block(0, 0.0, "Total remuneration outcomes\n"),
        _block(1, 10.0, "Member \nN/A\n20 307\nN/A\n" + "\n".join(["–"] * 6) + "\n"),
        _block(2, 20.0, "TOTAL\n" + "\n".join(["1 000"] * 10) + "\n"),
    ]
    result = reconstruct_table(blocks, TOTAL_REMUNERATION_OUTCOMES)
    row = result.rows[0]
    assert row.source_label == "Member"
    assert row.cells[0].cell_status == StructuredCellStatus.NOT_APPLICABLE
    assert row.cells[1].raw_value == "20 307"
