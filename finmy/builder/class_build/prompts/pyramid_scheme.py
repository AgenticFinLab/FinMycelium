
def pyramid_scheme_prompt(text: str) -> str:
    return """
You are a financial events simulation expert. Your task is to reconstruct a pyramid scheme event based on multiple data sources (e.g., web pages, PDFs, news articles). The simulation must be logical, fact-based, and comprehensive. Provide all information in a structured JSON format as specified below.

### **Event Reconstruction Guidelines**:
1. **Full Chain Presentation**: Present the entire event from cause to effect, including background, development, climax, and aftermath.
2. **Key Nodes**: Highlight critical milestones (e.g., launch, peak, collapse).
3. **Outcomes**: Describe the final state of the event.
4. **Impact Analysis**: Analyze impacts on all involved parties (e.g., initiators, investors, regulators, society).
5. **Fact-Based**: All information must be grounded in verified data from sources. If certain details are unavailable, explicitly state "Information not available" for the relevant field.
6. **Logical Coherence**: Ensure timelines, figures, and causal relationships are consistent.

### **Required Content (Detailed Key Points)**:
For the pyramid scheme event (e.g., "Blue Sky Gary" or similar), include at least the following aspects:
1. **Event Summary**: A concise overview of the entire event.
2. **Main Initiator(s)/Entity**: Names, backgrounds, and roles of key founders or entities.
3. **Promotion Methods**: How the initiators promoted the scheme (e.g., social media, seminars, word-of-mouth).
4. **Investor Attraction Tactics**: Strategies used to lure investors (e.g., high returns, exclusivity, fake testimonials).
5. **Investment Process**: How investors were onboarded and the mechanisms for investing.
6. **Product/Service Design**: Description of the fake or non-existent product/service offered.
7. **Investment Amounts**: Typical investment ranges, minimum/maximum amounts, and payment methods.
8. **Return Promises**: Specific promises made regarding returns (e.g., interest rates, timelines).
9. **Return Distribution**: How returns were initially paid to early investors (e.g., via new investments).
10. **Propagation Channels**: Channels used to spread the scheme (online/offline, geographic reach).
11. **Duration & Scale**: Timeframe of the scheme and total number of investors recruited.
12. **Promised Use of Funds**: Where initiators claimed the funds would be used (e.g., investments, business expansion).
13. **Actual Use of Funds**: Where funds were actually allocated (e.g., personal luxuries, ponzi payments). Include evidence of misappropriation if any.
14. **New-to-Old Payment Mechanism**: How the scheme sustained itself by using new investments to pay old investors. Provide data on cash flow gaps over time.
15. **Collapse Trigger**: What caused the scheme to end (e.g., regulatory intervention, liquidity crisis).
16. **State at Collapse**: The condition of the scheme at termination (e.g., investor count, outstanding liabilities).
17. **Fates of Initiators & Participants**: Legal actions against initiators and outcomes for other participants (e.g., associates, promoters).
18. **Investor Status at Collapse**: Demographic and financial state of investors at termination.
19. **Total Investment Volume**: Aggregate funds collected throughout the scheme.
20. **Principal Shortfall**: The gap between total principal invested and recoverable assets at collapse. Include time left if promised returns were ongoing.
21. **Promised Return Shortfall**: The gap between promised total returns and actual returns paid. Include remaining time for promised returns.
22. **Investor Losses**: Total net losses suffered by investors (after accounting for any returns received).
23. **Remaining Funds at Collapse**: Liquid assets left in initiators' accounts available for liquidation.
24. **Post-Liquidation Shortfall**: The amount and proportion of investor funds irrecoverable after asset liquidation.
25. **Broader Impacts**: Secondary effects (e.g., regulatory changes, social trust erosion, economic ripple effects).

### **Output Format**:
- Provide output in a **valid JSON object** with the structure below.
- Use precise dates, figures, and sources where possible.
- For unavailable data, use `null` or a string like "Information not available".
- Maintain a neutral, factual tone.

### **JSON Schema**:
```json
{
  "event_reconstruction": {
    "metadata": {
      "event_name": "string (e.g., Blue Sky Gary Pyramid Scheme)",
      "simulation_date": "string (YYYY-MM-DD)",
      "data_sources": "array of strings (list of sources used)",
      "geographic_scope": "string (primary countries/regions affected)"
    },
    "summary": {
      "overview": "string (2-3 paragraph summary)",
      "key_takeaways": "array of strings (bullet-point insights)"
    },
    "initiation_phase": {
      "main_initiators": [
        {
          "name": "string",
          "role": "string",
          "background": "string"
        }
      ],
      "promotion_methods": "array of strings",
      "attraction_tactics": "array of strings",
      "investment_process": "string (step-by-step description)",
      "product_service_description": "string (details of the fake product/service)",
      "typical_investment_amounts": {
        "min": "number (in original currency)",
        "max": "number (in original currency)",
        "currency": "string (e.g., USD, CNY)",
        "payment_methods": "array of strings"
      },
      "return_promises": {
        "promised_returns": "string (e.g., 20% monthly)",
        "timeline": "string (e.g., 6 months)",
        "conditions": "string (any terms attached)"
      },
      "return_distribution_mechanism": "string (how early investors were paid)",
      "propagation_channels": "array of strings"
    },
    "operation_phase": {
      "duration": {
        "start_date": "string (YYYY-MM-DD)",
        "end_date": "string (YYYY-MM-DD)",
        "total_months": "number"
      },
      "investor_metrics": {
        "total_investors": "number",
        "active_investors_at_peak": "number",
        "geographic_spread": "object (key-value pairs: region -> investor count)"
      },
      "promised_use_of_funds": "string",
      "actual_use_of_funds": {
        "allocations": [
          {
            "category": "string (e.g., Ponzi payments, personal expenses)",
            "percentage": "number (estimated %)",
            "evidence": "string (source notes)"
          }
        ],
        "misappropriation_evidence": "string (details if available)"
      },
      "new_to_old_payment_flow": {
        "mechanism": "string (description)",
        "cash_flow_gap_analysis": [
          {
            "period": "string (e.g., Year 1, Q2)",
            "inflows": "number (total new investments)",
            "outflows": "number (total payouts)",
            "shortfall": "number (outflows - inflows)"
          }
        ]
      }
    },
    "collapse_phase": {
      "trigger_event": "string (what directly caused collapse)",
      "collapse_date": "string (YYYY-MM-DD)",
      "state_at_collapse": {
        "total_investors": "number",
        "total_liabilities": "number (currency as above)",
        "active_investors": "number",
        "outstanding_promises": "string (description)"
      },
      "fates": {
        "initiators": [
          {
            "name": "string",
            "legal_action": "string (e.g., arrested, fined)",
            "outcome": "string (e.g., sentenced to X years)"
          }
        ],
        "other_participants": "string (e.g., associates, promoters outcomes)"
      },
      "investor_status": {
        "demographic_profile": "string (e.g., retirees, young professionals)",
        "financial_state": "string (general description)"
      }
    },
    "financial_analysis": {
      "total_investment_volume": "number (currency as above)",
      "principal_shortfall": {
        "total_principal": "number",
        "recoverable_assets": "number",
        "shortfall_amount": "number",
        "shortfall_percentage": "number",
        "time_left_if_ongoing": "string (e.g., 3 months)"
      },
      "promised_return_shortfall": {
        "total_promised_returns": "number",
        "returns_paid": "number",
        "shortfall_amount": "number",
        "time_left_for_promised_returns": "string"
      },
      "total_investor_losses": "number (net losses after returns)",
      "remaining_funds_at_collapse": {
        "liquid_assets": "number",
        "other_assets": "number (e.g., real estate, vehicles)",
        "total_available_for_liquidation": "number"
      },
      "post_liquidation_shortfall": {
        "total_recovered": "number",
        "total_unrecovered": "number",
        "percentage_unrecovered": "number",
        "investors_fully_compensated": "number",
        "investors_partially_compensated": "number",
        "investors_uncompensated": "number"
      }
    },
    "broader_impacts": {
      "regulatory_changes": "array of strings (new laws/policies triggered)",
      "social_impacts": "array of strings (e.g., loss of trust in financial institutions)",
      "economic_impacts": "array of strings (e.g., local economic downturn)",
      "media_coverage": "string (summary of public discourse)"
    },
    "verification_notes": {
      "data_confidence": "string (e.g., High/Medium/Low based on source quality)",
      "key_assumptions": "array of strings (any assumptions made during reconstruction)",
      "unverified_claims": "array of strings (claims requiring further verification)"
    }
  }
}
```

### **Instructions for LLM**:
- Populate the JSON object based strictly on the provided data sources.
- Ensure all monetary values specify the currency.
- For numerical fields, use `null` if data is missing; for text fields, use "Information not available".
- Maintain chronological and logical flow across sections.
- Highlight causal relationships (e.g., how promotion tactics led to investor attraction).
- In the `verification_notes`, rate data confidence and list assumptions.

### **Example Reference (for context)**:
For a scheme like "Blue Sky Gary", you might include:
- **Main initiator**: "Gary Zhang" (pseudonym), a former financial advisor.
- **Promotion**: Through WeChat groups and "investment seminars" in Tianjin, China.
- **Product**: Fake "high-tech mining equipment" investment contracts.
- **Collapse trigger**: Regulatory raid in July 2023 after investor complaints.
- **Total investment volume**: ~2 billion CNY.
- **Investor losses**: ~1.5 billion CNY net.

Now, simulate the pyramid scheme event based on the provided data sources. Output only the JSON object within a markdown code block.

    """