"""Feature vocabulary and validation for the inverted-index dispatcher.

Phase 0: vocabulary only — no extractors, no preprocessing, no index.
"""

from logic.features.vocabulary import (
    EXEMPT_FEATURES,
    FEATURE_VOCABULARY,
    validate_feature,
)

__all__ = ["EXEMPT_FEATURES", "FEATURE_VOCABULARY", "validate_feature"]
