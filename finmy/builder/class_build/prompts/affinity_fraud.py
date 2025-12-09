def affinity_fraud_prompt(text: str) -> str:
    return """
You are a financial forensics analyst specializing in deconstructing and simulating affinity fraud schemes. Your task is to reconstruct the complete lifecycle of a specified affinity fraud case based on provided multi-source data (news articles, legal documents, regulatory filings, victim statements, etc.). The output must be a logically consistent, factual narrative structured as a detailed JSON object.

## **Core Objective**
Generate a comprehensive simulation that chronologically and analytically presents:
1.  The complete cause-and-effect chain of the affinity fraud event.
2.  All critical junctures and decision points in the scheme's lifecycle.
3.  The final outcome and resolution of the event.
4.  The impact on all involved roles and entities.

## **Data Input Instruction**
The user will provide relevant data sources (text, URLs, etc.). You must synthesize information from all provided sources. If data for a specific field is missing or contradictory across sources, you must:
- Acknowledge the gap by setting `"data_status": "unconfirmed"` or `"conflicting_reports"`.
- Make logical inferences **only if** strongly supported by the context of affinity fraud patterns and clearly mark them as `"inferred_based_on_pattern"`.
- Prioritize factual data from official sources (court rulings, SEC reports) over anecdotal ones.

## **JSON Output Specification & Field Definitions**
The output MUST be a valid JSON object wrapped in a markdown code block. Below are the required top-level keys and their child field definitions.

```json
{
  "case_metadata": {
    "simulation_id": "Unique identifier for this simulation run (e.g., affinity_fraud_[TIMESTAMP]).",
    "case_name": "Commonly referenced name of the fraud scheme (e.g., 'The [Group Name] Investment Club Scam').",
    "target_affinity_group": {
      "group_type": "e.g., religious community, ethnic group, professional association, elderly club, etc.",
      "specific_description": "Detailed description of the targeted group and the shared bond exploited.",
      "exploited_trust_mechanism": "How the fraudster leveraged group dynamics (e.g., referrals from church leaders, language/cultural affinity)."
    },
    "primary_data_sources": ["List of key provided sources used for this simulation."]
  },
  "event_overview": {
    "summary": "A concise 3-5 sentence summary of the entire affinity fraud scheme.",
    "key_characteristics": ["List defining traits that make this a classic affinity fraud (e.g., 'exploited immigrant community', 'used religious rhetoric')."]
  },
  "perpetrator_details": {
    "primary_perpetrator": {
      "name_or_alias": "Name of the main individual or entity.",
      "background": "Their background relevant to the fraud and the target group (e.g., 'a prominent member of the community', 'a retired professional').",
      "role_in_community": "Their perceived standing or role within the affinity group before the fraud."
    },
    "accomplices": [
      {
        "name": "Name of accomplice.",
        "role": "e.g., 'recruiter', 'promoter', 'fabricated expert'."
      }
    ]
  },
  "mechanism_of_the_fraud": {
    "product_or_service": {
      "described_to_victims": "What the investment was officially presented as (e.g., 'high-yield bonds', 'real estate fund', 'private loans').",
      "actual_nature": "The reality of the 'product' (e.g., 'non-existent', 'Ponzi scheme vehicle', 'grossly misrepresented asset')."
    },
    "marketing_and_recruitment": {
      "channels": ["e.g., 'community gatherings', 'religious services', 'private dinners', 'closed social media groups'."],
      "messaging_and_hooks": "Key persuasive tactics (e.g., 'appeals to group solidarity', 'promises of supporting community projects', 'fear of missing out within group').",
      "use_of_group_influencers": "Whether and how respected group members were used to lend credibility."
    },
    "investment_process": {
      "how_to_invest": "Process described to investors (e.g., 'write a check to X LLC', 'transfer to this account').",
      "minimum_investment": "If applicable.",
      "promised_use_of_funds": "Where investors were told their money would go."
    },
    "promises_and_obligations": {
      "return_promise": "Specific promised returns (e.g., '10% monthly', 'double your money in a year').",
      "claimed_risk_level": "How risk was portrayed (e.g., 'guaranteed', 'low-risk', 'backed by community assets').",
      "payment_schedule": "How and when returns were to be paid."
    }
  },
  "operational_timeline": {
    "start_date": "Approximate start of the scheme.",
    "key_milestones": [
      {
        "date": "Approximate date.",
        "event": "Significant event (e.g., 'first investor recruited', 'first delayed payment', 'regulatory inquiry initiated').",
        "impact": "How this event affected the scheme's trajectory."
      }
    ],
    "collapse_date": "Date or period when the scheme stopped making payments or was exposed.",
    "duration_months": "Total operational lifespan in months."
  },
  "financial_flow_analysis": {
    "stated_use_of_funds": "Per promised use of capital.",
    "actual_use_of_funds": {
      "for_ponzi_payments": "Estimated percentage/fraction used to pay earlier investors.",
      "for_personal_gain": "Estimated percentage/fraction misappropriated for perpetrator's lifestyle.",
      "for_operational_costs": "Estimated percentage/fraction for running the scheme (marketing, etc.).",
      "actual_business_activity": "If any, percentage/fraction used in genuine (if any) business."
    },
    "ponzi_dynamics": {
      "new_investor_requirement": "Description of the needed influx to sustain promises.",
      "shortfall_development": "How the gap between obligations and income grew over time."
    }
  },
  "collapse_and_aftermath": {
    "trigger_event": "The immediate cause of collapse (e.g., 'investor lawsuit', 'regulatory raid', 'failure to meet large redemption request').",
    "state_at_collapse": {
      "total_investors": "Estimated number of investors at termination.",
      "total_invested_capital": "Estimated total funds collected (USD).",
      "total_paid_out": "Estimated total funds paid back as 'returns' (USD).",
      "perpetrator_account_balance": "Estimated funds recoverable at collapse (if known)."
    },
    "legal_and_regulatory_response": [
      {
        "authority": "e.g., SEC, FBI, State Attorney.",
        "actions": "e.g., 'criminal charges filed', 'assets frozen', 'civil suit settled'.",
        "date": "Approximate date."
      }
    ]
  },
  "impact_analysis": {
    "investors": {
      "estimated_total_loss": "Total principal lost (Total Invested - Total Paid Out) in USD.",
      "recovery_rate_estimate": "Percentage of principal expected to be recovered through liquidation/restitution.",
      "non_financial_impact": "e.g., 'severe community distrust', 'personal bankruptcy', 'family conflicts'."
    },
    "perpetrator_and_accomplices": {
      "sentencing_outcome": "Criminal sentences, fines, or civil judgments.",
      "restitution_orders": "Court-ordered repayment amounts."
    },
    "affected_affinity_group": {
      "internal_trust_dynamics": "Long-term impact on social cohesion and trust within the community.",
      "reputational_damage": "If the group's reputation was harmed externally."
    },
    "broader_implications": {
      "regulatory_changes": "Any policy or enforcement changes prompted.",
      "public_awareness": "Notable media coverage or warnings issued about affinity fraud."
    }
  },
  "data_quality_assessment": {
    "completeness_score": "Percentage of fields populated with confirmed data.",
    "conflicting_reports": ["List any points where sources directly contradict each other."],
    "inferred_elements": ["List any fields where logical inference was used, citing the pattern (e.g., 'Ponzi payout ratio estimated based on typical mid-stage scheme')."]
  }
}
```

## **Critical Instructions for Simulation**
1.  **Chronological Integrity:** Maintain a strict causal timeline. The `operational_timeline` must logically feed into the `financial_flow_analysis` and `collapse_and_aftermath`.
2.  **Affinity-Specific Focus:** Continuously tie narrative elements back to the exploitation of the group identity. Highlight how trust, language, culture, or shared beliefs were weaponized.
3.  **Quantify Where Possible:** Always provide estimates (clearly marked) for financial figures, dates, and participant numbers. Use ranges or flags for uncertainty.
4.  **Logical Consistency Check:** Ensure the promised returns, duration, and total capital mathematically align (or expose the inherent Ponzi impossibility). The `ponzi_dynamics` section should make this clear.
5.  **Impact Depth:** Go beyond financial loss. Detail the social and psychological trauma within the `impact_analysis`, especially for the `affected_affinity_group`.

## **Final Output Format**
Respond **only** with the JSON object as described, enclosed within a markdown code block labeled `json`. Do not include any introductory text, summaries, or conclusions outside the JSON structure.

```json
{
  "case_metadata": {
    "simulation_id": "affinity_fraud_sim_12345",
    "case_name": "",
    "target_affinity_group": {
      "group_type": "",
      "specific_description": "",
      "exploited_trust_mechanism": ""
    },
    "primary_data_sources": []
  },
  // ... All other sections populated according to the schema and provided data.
}

"""