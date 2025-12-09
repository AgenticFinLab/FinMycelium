
def accounting_fraud_prompt(text: str) -> str:
    return """
You are an expert financial analyst and forensic investigator specializing in corporate fraud. Your task is to simulate a comprehensive accounting fraud event based on provided multi-source data (e.g., news articles, financial reports, regulatory filings, court documents). The simulation must reconstruct the event **logically, chronologically, and factually**, covering all key aspects from inception to resolution.

#### **Simulation Requirements:**

1. **Full Chain Presentation**: Narrate the entire event from cause to effect, including background, execution, exposure, and aftermath.
2. **Key Nodes**: Identify and detail each critical phase (e.g., fraud initiation, methods used, detection, investigation, legal actions).
3. **Outcome**: Present the final state of the event, including financial, legal, and reputational consequences.
4. **Stakeholder Impact**: Analyze impacts on all involved parties (e.g., company, executives, employees, investors, auditors, regulators, industry).

#### **Specific Details to Include (Using Enron or Wirecard as Reference Template):**

For the target event (to be extracted from input data), ensure the simulation covers at least the following points:

1. **Event Overview**: A concise summary of the accounting fraud.
2. **Primary Perpetrators**: Key individuals or entities responsible (e.g., CEO, CFO, specific departments).
3. **Fraud Motivation**: Why the fraud was initiated (e.g., pressure to meet earnings, hide losses, inflate stock price).
4. **Fraudulent Methods**: Specific accounting techniques used (e.g., revenue inflation, liability concealment, fake transactions, special purpose entities (SPEs)).
5. **Documentation & Falsification**: How records were manipulated (e.g., forged invoices, altered ledgers, fake contracts).
6. **Internal Concealment**: How the fraud was hidden within the company (e.g., collusion, override of controls, misleading internal audits).
7. **External Presentation**: How the company portrayed its financial health to the public (e.g., earnings reports, investor calls, press releases).
8. **Auditor Involvement**: Role of external auditors (e.g., negligence, complicity, failure to detect).
9. **Investor Attraction**: How investors were drawn in based on fraudulent data (e.g., stock performance, dividend promises, growth projections).
10. **Duration & Scale**: Time period the fraud persisted and cumulative scale (e.g., falsified revenue amount, hidden debt).
11. **Red Flags**: Warning signs that were missed (e.g., inconsistent cash flows, unusual transactions, whistleblower tips).
12. **Trigger for Exposure**: Event that led to discovery (e.g., whistleblower, investigative journalism, regulatory inquiry, audit failure).
13. **Immediate Aftermath**: Market reaction, stock price collapse, credit downgrades, executive departures.
14. **Regulatory & Legal Actions**: Investigations by agencies (e.g., SEC, DOJ), charges filed, lawsuits (class actions, civil/criminal cases).
15. **Corporate Outcome**: Bankruptcy, restructuring, delisting, dissolution, or survival.
16. **Perpetrator Outcomes**: Legal consequences for key individuals (e.g., fines, imprisonment, bans).
17. **Investor Impact**: Financial losses, recovery efforts (e.g., settlements, insurance claims).
18. **Employee Impact**: Job losses, pension fund losses, reputational damage.
19. **Auditor Consequences**: Penalties for audit firms (e.g., fines, lawsuits, reputational damage).
20. **Industry & Regulatory Reforms**: Changes prompted by the fraud (e.g., new laws like Sarbanes-Oxley, accounting standard updates).
21. **Total Financial Damage**: Estimated monetary loss across all stakeholders.
22. **Recovery Rate**: Percentage of investor funds recovered, if any.
23. **Systemic Implications**: Broader effects on market trust, sector perception, or global finance.

#### **Output Format Instructions:**

- Output **must** be a valid JSON object matching the structure below.
- All fields should be filled based on simulated data. Use `null` for unknown information.
- Ensure factual consistency; avoid speculation unless labeled as `estimated` or `alleged`.
- Use clear, professional language in descriptions.

#### **JSON Schema Definition:**

```json
{
  "event_simulation": {
    "metadata": {
      "simulation_type": "Accounting Fraud",
      "event_name": "Name of the fraud case (e.g., Enron Scandal)",
      "reference_date_range": "YYYY-MM to YYYY-MM",
      "data_sources_summary": "Brief list of input sources used"
    },
    "overview": {
      "summary": "Full narrative summary (2-3 paragraphs).",
      "primary_perpetrators": [
        {
          "name": "Name",
          "title": "Role in company",
          "alleged_role": "Specific involvement in fraud"
        }
      ],
      "fraud_motivation": "Description of key drivers.",
      "fraudulent_methods": [
        {
          "method": "e.g., Revenue Recognition Fraud",
          "description": "How it was executed",
          "estimated_financial_impact": "Amount or percentage"
        }
      ],
      "falsified_documents": [
        {
          "document_type": "e.g., Invoice, Balance Sheet",
          "purpose": "What it was used to fake"
        }
      ]
    },
    "execution_timeline": {
      "start_date": "YYYY-MM",
      "end_date": "YYYY-MM",
      "key_milestones": [
        {
          "date": "YYYY-MM-DD",
          "event": "Description of significant occurrence"
        }
      ]
    },
    "concealment_mechanisms": {
      "internal_controls_bypassed": "How internal checks were avoided.",
      "external_auditor_relation": "Description of auditor interaction.",
      "public_disclosures": "How false info was communicated to market."
    },
    "exposure": {
      "trigger_event": "What led to discovery.",
      "whistleblower_if_any": "Details if applicable.",
      "initial_public_reaction": "Market/media response upon news."
    },
    "aftermath": {
      "financial_impact": {
        "company_market_cap_loss": "Amount in USD",
        "investor_losses_estimated": "Amount in USD",
        "hidden_debt_revealed": "Amount in USD",
        "falsified_revenue_total": "Amount over fraud period"
      },
      "legal_actions": [
        {
          "entity": "e.g., SEC, DOJ",
          "action_type": "e.g., Civil Suit, Criminal Charges",
          "outcome": "e.g., Settlements, Convictions"
        }
      ],
      "corporate_fate": "e.g., Bankruptcy, Acquired, Survived",
      "perpetrator_outcomes": [
        {
          "name": "Perpetrator name",
          "penalties": "e.g., Fine amount, Prison sentence"
        }
      ],
      "auditor_fate": "What happened to audit firm(s).",
      "employee_impact": "e.g., Layoffs, pension losses.",
      "investor_recovery": {
        "settlement_funds": "Amount in USD",
        "recovery_rate_percentage": "Estimated percentage",
        "pending_claims": "If any remain unresolved"
      }
    },
    "systemic_effects": {
      "regulatory_changes": "New laws/standards enacted.",
      "industry_practices_shift": "Changes in sector behavior.",
      "trust_impact": "Effect on investor confidence."
    },
    "summary_metrics": {
      "total_duration_months": "Integer",
      "total_investors_affected": "Integer (estimate if unknown)",
      "total_financial_damage_usd": "Sum of key losses",
      "largest_single_loss_usd": "If notable",
      "recovery_rate_percentage": "Overall estimated recovery"
    }
  }
}
```

#### **Final Instructions:**

- Process all provided data sources to extract relevant facts.
- Fill the JSON structure with detailed, coherent information.
- Maintain a neutral, factual tone; distinguish between proven facts and allegations.
- If data is insufficient for a field, use `null` and add a note in `metadata["data_sources_summary"]` about gaps.
- Output only the JSON object, enclosed in a markdown code block.

---

**Output Example (Markdown Wrapper):**

```json
{
  "event_simulation": {
    "metadata": {
      "simulation_type": "Accounting Fraud",
      "event_name": "Enron Scandal",
      "reference_date_range": "1997-01 to 2001-12",
      "data_sources_summary": "SEC filings, court documents, news archives"
    },
    "overview": {
      "summary": "Enron Corporation, an American energy company, engaged in systematic accounting fraud...",
      ...
    }
    ...
  }
}
```

Now, simulate the accounting fraud event based on the provided data.

"""