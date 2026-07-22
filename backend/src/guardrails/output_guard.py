"""Output guard: grounding checks on LLM extractions.

Schema validation (BaseAgent + contracts.py) proves an output is
well-formed; it cannot prove it is TRUE. The grounding check closes that
gap for the fields where hallucination costs real money: the extracted
amount and fund name must literally appear in the source text, or the
extraction is rejected as ungrounded."""


def grounding_issues(parsed: dict, source_text: str) -> list[str]:
    """Return reasons the extraction is NOT grounded in the source document."""
    issues: list[str] = []
    text = source_text.lower()

    amount = parsed.get("amount_usd")
    if amount is not None:
        variants = (
            f"{amount:,.2f}",          # 1,200,000.00
            f"{amount:,.0f}",          # 1,200,000
            f"{int(amount)}",          # 1200000
        )
        if not any(v in source_text for v in variants):
            issues.append(
                f"amount_usd={amount} does not appear in the source document"
            )

    fund_name = (parsed.get("fund_name_raw") or "").strip().lower()
    if fund_name and fund_name not in text:
        issues.append(
            f"fund_name_raw={parsed.get('fund_name_raw')!r} does not appear "
            f"in the source document"
        )
    return issues
