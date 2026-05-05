"""Tests for logic.features.aps — APS_* domain features."""

from __future__ import annotations

import pytest

from logic.features import aps
from logic.preprocess import Segment


def _seg(text: str) -> Segment:
    return Segment(kind="paragraph", text=text, offset=0, lintable=True)


def _has(feature: str, text: str) -> bool:
    return feature in aps.extract(_seg(text))


# ---------------------------------------------------------------------------
# APS_LEGISLATION_REFERENCE
# ---------------------------------------------------------------------------


def test_legislation_act_fires():
    assert _has("APS_LEGISLATION_REFERENCE", "See the Work Health and Safety Act 2011 for details.")


def test_legislation_regulations_fires():
    assert _has("APS_LEGISLATION_REFERENCE", "Refer to the Ombudsman Regulations 2017.")


def test_legislation_absent():
    assert not _has("APS_LEGISLATION_REFERENCE", "The policy guidance is available online.")


# ---------------------------------------------------------------------------
# APS_DEPARTMENT_NAME
# ---------------------------------------------------------------------------


def test_department_name_pattern_fires():
    assert _has("APS_DEPARTMENT_NAME", "Contact the Department of Finance for advice.")


def test_department_name_wordlist_fires():
    assert _has("APS_DEPARTMENT_NAME", "Refer to the Treasury for financial guidance.")


def test_department_name_absent():
    assert not _has("APS_DEPARTMENT_NAME", "The organisation provides guidance.")


# ---------------------------------------------------------------------------
# APS_MINISTERIAL_TITLE
# ---------------------------------------------------------------------------


def test_ministerial_title_fires():
    assert _has("APS_MINISTERIAL_TITLE", "The prime minister announced the policy.")


def test_ministerial_title_minister_for_fires():
    assert _has("APS_MINISTERIAL_TITLE", "The minister for finance approved the budget.")


def test_ministerial_title_absent():
    assert not _has("APS_MINISTERIAL_TITLE", "The official announced the policy.")


# ---------------------------------------------------------------------------
# APS_DATE_LONGFORM
# ---------------------------------------------------------------------------


def test_date_longform_fires():
    assert _has("APS_DATE_LONGFORM", "The policy was effective from 1 January 2024.")


def test_date_longform_december_fires():
    assert _has("APS_DATE_LONGFORM", "Published on 25 December 2023.")


def test_date_longform_absent():
    assert not _has("APS_DATE_LONGFORM", "The policy was effective from 01/01/2024.")


# ---------------------------------------------------------------------------
# APS_COMMONWEALTH_ENTITY
# ---------------------------------------------------------------------------


def test_commonwealth_entity_fires():
    assert _has("APS_COMMONWEALTH_ENTITY", "Contact the Australian Taxation Office for assistance.")


def test_commonwealth_entity_aps_commission_fires():
    assert _has(
        "APS_COMMONWEALTH_ENTITY",
        "The Australian Public Service Commission publishes guidance.",
    )


def test_commonwealth_entity_absent():
    assert not _has("APS_COMMONWEALTH_ENTITY", "Contact the organisation for assistance.")
