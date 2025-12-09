def insider_trading_prompt(text: str) -> str:
    return """
You are a financial forensic analyst and legal expert. Your task is to simulate a complete **Insider Trading** event based on factual information provided from multiple sources (news articles, legal documents, SEC filings, court records, etc.). The simulation must reconstruct the event's full lifecycle, identify all critical nodes, analyze impacts, and present the findings in a structured, factual, and logical manner.

## Core Requirements
1. **Full-Chain Reconstruction**: Present the complete cause-and-effect sequence of the insider trading event.
2. **Key Node Identification**: Highlight critical decision points, actions, and milestones in the event’s timeline.
3. **Outcome Presentation**: Clearly state the final legal, financial, and reputational outcomes.
4. **Stakeholder Impact Analysis**: Detail the effects on all involved parties (insiders, tippers, tippees, companies, investors, regulators, markets).

## Detailed Information Points to be Covered (Based on the "Blue Sky" Example Framework)
For the specific insider trading case analyzed, ensure the simulation addresses the following points. Adapt the specifics to fit a typical insider trading scheme.

**1.  Event Overview**
    *   A concise summary of the insider trading scheme.

**2.  Primary Actor(s) & Entities**
    *   Who initially possessed the Material Nonpublic Information (MNPI)? (e.g., corporate executive, board member, lawyer, banker).
    *   List all involved entities (e.g., the source company, the trader's employer, shell companies).

**3.  Source & Nature of MNPI**
    *   What was the confidential information? (e.g., upcoming earnings, merger announcement, drug trial results).
    *   How was the information obtained? (e.g., by virtue of position, breach of duty, misappropriation).

**4.  Communication of MNPI (Tipping)**
    *   How was the information communicated from the insider (tipper) to the trader (tippee)?
    *   Methods used (encrypted apps, in-person meetings, family connections).
    *   Was there a personal benefit to the tipper? (Key for liability under *Dirks* test).

**5.  Trading Strategy & Execution**
    *   How did the trader act on the information?
    *   Specific securities traded (stocks, options, derivatives).
    *   Timing of trades relative to the public announcement.
    *   Use of complex financial instruments or offshore accounts to conceal activity.

**6.  Concealment Methods**
    *   How did the actors attempt to avoid detection? (e.g., using nominee accounts, staggered trades, avoiding usual patterns).

**7.  Scale & Duration**
    *   Over what period did the illicit trading occur?
    *   How many individual trades or transactions were made?

**8.  Financial Gains / Losses Avoided**
    *   Total illegal profits generated or losses avoided by the traders.
    *   The price movement before/after the information became public.

**9.  Detection Trigger**
    *   How was the scheme discovered? (e.g., SEC surveillance algorithms, whistleblower, unusual options activity alert, parallel investigation).

**10. Investigation Process**
    *   Which agencies investigated? (e.g., SEC, DOJ, FINRA).
    *   Key investigative techniques used (e.g., subpoenas for records, wiretaps, analysis of trading patterns).

**11. Legal & Regulatory Charges**
    *   Specific charges filed (e.g., SEC civil charges for violation of Section 10(b) and Rule 10b-5, DOJ criminal charges for securities fraud, wire fraud).
    *   Charges against tippers, tippees, and any entities.

**12. Resolution & Settlements**
    *   Outcome of legal proceedings: Guilty plea, trial verdict, or settlement.
    *   Details of settlements with regulatory bodies (e.g., SEC disgorgement, penalties, injunctions).

**13. Final State at Termination**
    *   The status of all involved parties at the conclusion of the case.
    *   Final tally of illegal profits disgorged.

**14. Consequences for Primary Actors**
    *   Sentences (fines, imprisonment, probation).
    *   Career impacts (industry bar, loss of professional licenses).
    *   Reputational damage.

**15. Consequences for Investors & Market**
    *   Impact on the share price of the involved company around the event.
    *   Erosion of market integrity and investor confidence.
    *   Any class-action lawsuits filed by affected investors.

**16. Financial Quantification at Case Close**
    *   Total illicit gains disgorged.
    *   Total civil and criminal penalties paid.
    *   Net loss to the perpetrators after all payments.

**17. Broader Implications**
    *   Changes in corporate compliance policies prompted by the case.
    *   Regulatory rulemaking or enforcement focus shifts resulting from the case.
    *   Notable legal precedents set.

## Output Format Instructions
You **MUST** output the complete analysis in a **single, standardized JSON object**. Do not include any explanatory text outside this JSON structure.

### JSON Schema Definition
```json
{
  "insider_trading_case_analysis": {
    "metadata": {
      "case_name": "string  // The common name of the case (e.g., 'SEC v. [Defendant]').",
      "simulation_date": "string (YYYY-MM-DD)  // The date of this simulation.",
      "primary_jurisdiction": "string  // Main country/region where the case was prosecuted."
    },
    "event_overview": {
      "summary": "string  // A comprehensive 3-5 sentence summary of the entire event.",
      "material_nonpublic_info": "string  // Description of the MNPI at the heart of the case.",
      "key_timeline": {
        "info_generated_date": "string (YYYY-MM-DD) // When the MNPI was created/known internally.",
        "first_illegal_trade_date": "string (YYYY-MM-DD)",
        "public_announcement_date": "string (YYYY-MM-DD)",
        "investigation_start_date": "string (YYYY-MM-DD)",
        "charges_filed_date": "string (YYYY-MM-DD)",
        "case_resolved_date": "string (YYYY-MM-DD)"
      }
    },
    "actors_and_entities": {
      "insider_tipper": {
        "name": "string",
        "role": "string  // e.g., CFO, Corporate Counsel",
        "employer_at_time": "string  // The source company of the MNPI."
      },
      "primary_tippee_trader": {
        "name": "string",
        "relationship_to_tipper": "string",
        "employer_at_time": "string"
      },
      "other_co-conspirators": [
        {
          "name": "string",
          "role_in_scheme": "string"
        }
      ],
      "affected_public_company": "string  // The company whose stock was traded.",
      "investigative_agencies": ["string"] // e.g., ["SEC", "DOJ"]
    },
    "scheme_execution": {
      "tipping_method": "string  // How info was passed.",
      "tipper_personal_benefit": "string  // Describe if known.",
      "trading_vehicles": ["string"] // e.g., ["Common Stock", "Call Options"],
      "concealment_tactics": ["string"] // e.g., ["Used friend's brokerage account"]
    },
    "financial_scope": {
      "total_illicit_gain": "number  // In USD.",
      "number_of_illicit_trades": "integer",
      "trading_window_months": "number  // Time between first trade and public announcement.",
      "price_impact_pct": "number  // Approximate % stock move post-announcement."
    },
    "detection_and_investigation": {
      "detection_trigger": "string",
      "key_investigative_evidence": ["string"] // e.g., ["Email records", "Trading data analysis", "Wiretap transcripts"]
    },
    "legal_outcomes": {
      "charges_filed": {
        "sec_civil_charges": ["string"],
        "doj_criminal_charges": ["string"]
      },
      "disgorgement_amount": "number  // In USD.",
      "civil_penalties": "number  // In USD.",
      "criminal_fines": "number  // In USD.",
      "prison_sentences": [
        {
          "defendant": "string",
          "sentence_length_months": "integer"
        }
      ],
      "other_sanctions": ["string"] // e.g., ["Industry Bar", "Forfeiture of assets"]
    },
    "impacts_analysis": {
      "market_integrity_impact": "string  // Brief assessment of damage to fair markets.",
      "investor_impact": "string  // Description of harm to other investors.",
      "corporate_governance_impact": "string  // Changes in compliance or policies spurred.",
      "regulatory_impact": "string  // Any notable shift in enforcement focus."
    }
  }
}
```

## Critical Instructions for LLM
*   **Fact-Based & Logical**: Every piece of information must be logically consistent and presented as derived from the provided source materials. If specific data points are unavailable in the sources, you may use reasoned estimates but must indicate this within the `summary` or relevant string field (e.g., 'Estimated based on typical patterns').
*   **Completeness**: Strive to populate all JSON fields. If a field is genuinely inapplicable, use `null` or an empty array `[]` as appropriate.
*   **Neutral Tone**: Maintain an objective, analytical tone. Describe actions and consequences without emotional language.
*   **Chain of Causality**: Ensure the narrative within the JSON logically connects the acquisition of MNPI, the tipping/trading, detection, and consequences.
*   **Output Confirmation**: Your final output must be **only** the JSON object, wrapped in a markdown code block as shown above. Do not add introductory or concluding remarks.

"""