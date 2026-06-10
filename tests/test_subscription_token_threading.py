import inspect
from typing import Callable, Any

import pytest

from financial_report_llm_extractor.client import ExtractorConfig
from financial_report_llm_extractor.pipeline_core import run_pipeline
from financial_report_llm_extractor.structured_sources.company_evaluation import (
    _run_llm_supplement_step,
    run_company_evaluation,
)


def test_extractor_config_has_optional_subscription_token() -> None:
    assert ExtractorConfig().subscription_token is None
    assert ExtractorConfig(subscription_token="tok").subscription_token == "tok"


@pytest.mark.parametrize(
    "func",
    [
        run_pipeline,
        run_company_evaluation,
        _run_llm_supplement_step,
    ],
)
def test_subscription_token_is_optional_keyword(func: Callable[..., Any]) -> None:
    param = inspect.signature(func).parameters.get("subscription_token")
    assert param is not None, f"{func.__name__} is missing subscription_token"
    assert param.default is None
