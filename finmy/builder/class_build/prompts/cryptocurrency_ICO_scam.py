def cryptocurrency_ICO_scam_prompt(text: str) -> str:
    return """
    You are an expert financial crime analyst specializing in reconstructing and simulating cryptocurrency and ICO (Initial Coin Offering) scams. Your task is to synthesize information from multiple provided sources (e.g., scraped web content, PDF reports, news articles, regulatory filings) to create a comprehensive, factual, and logical narrative of the event.

**Core Instructions:**
1.  **Factual & Logical:** All output must be strictly based on the provided source data. If specific data points are unavailable in the sources, you may reason logically but must clearly indicate any assumptions or estimations as such. Do not invent facts.
2.  **Comprehensive Scope:** The analysis must follow the entire lifecycle of the scam, from inception to termination and aftermath, covering promotional tactics, financial flows, key actors, and impacts.
3.  **Structured Output:** Present the final analysis in a detailed, standardized JSON format as defined below.

**Analysis Framework & Required Details:**
Using the provided sources, reconstruct the event by addressing the following points. These points should inform the content of the JSON fields.

1.  **Event Overview:** A concise summary of the entire scam.
2.  **Primary Perpetrator(s):** Individual(s), team, or entity that initiated and controlled the scam.
3.  **Promotional Strategy:** How the project was marketed (e.g., fake websites, whitepapers, social media bots, influencer endorsements, fake team profiles).
4.  **Investor Attraction Tactics:** Specific methods used to lure investors (e.g., promises of high returns, fear of missing out (FOMO), fake testimonials, referral bonuses).
5.  **Investment Mechanism:** The process for investors to participate (e.g., sending crypto to a specified wallet, registration on a platform, KYC procedures).
6.  **Product/Service Description:** The nature of the fraudulent offering (e.g., utility token, security token, fake exchange platform, non-existent blockchain project, wallet service).
7.  **Investment Scale & Details:** How much money was typically invested, in what currency (e.g., BTC, ETH, USD), and any investment tiers or minimums.
8.  **Return Promise:** The specific claims about returns (e.g., "20% monthly ROI," "10x on token launch," staking rewards).
9.  **Payout Mechanism (if any):** How early investors received returns (withdrawals from platform, token airdrops).
10. **Information Dissemination:** Primary channels for spreading the project (Telegram, Twitter, YouTube, dedicated forums).
11. **Duration & Scale:** Operational timeline and estimated number of investors/contributors.
12. **Promised Use of Funds:** The stated purpose of the raised capital (e.g., platform development, marketing, liquidity provision).
13. **Actual Use of Funds & Misappropriation:** Evidence or strong indicators of how funds were actually used (e.g., personal luxury purchases, transferred to other exchanges/wallets, used for Ponzi payouts). Explicitly note if funds were diverted.
14. **Ponzi/Pyramid Mechanics (if applicable):** Describe the "borrow from new to pay old" structure. Provide data or estimates on the growing gap between inflows and necessary payouts.
15. **Termination Trigger:** The event that caused the scam to collapse (e.g., failure to pay, withdrawal halt, regulatory action, "rug pull" where liquidity is removed).
16. **Termination State:** The immediate condition at collapse (e.g., website offline, social media deleted, funds drained).
17. **Outcome for Perpetrators:** Legal status, arrests, fines, or known whereabouts.
18. **Outcome for Investors:** General state (e.g., unable to withdraw funds, tokens worthless).
19. **Total Funds Raised:** Estimated total value collected from investors at termination (in USD and original cryptocurrency if possible).
20. **Capital Shortfall:** The gap between remaining assets and total principal investments at termination.
21. **Promised Return Shortfall:** The gap between promised total returns and actual/distributable assets.
22. **Estimated Total Investor Loss:** The net loss to investors (considering any payouts received).
23. **Remaining Perpetrator Assets:** Known or estimated assets available for recovery/seizure at termination.
24. **Post-Liquidation Shortfall:** Estimated amount and proportion of investor funds that remain unrecoverable after any asset recovery process.
25. **Broader Impact:** Consequences beyond direct investor losses (e.g., regulatory crackdowns on legitimate ICOs, loss of trust in the crypto sector, impact on specific blockchain ecosystems).

**Output Format Specification:**
You MUST output the analysis in the following JSON structure. Wrap the final JSON in a markdown code block.

```json
{
  "financial_event_simulation": {
    "metadata": {
      "simulation_type": "Cryptocurrency_ICO_Scam",
      "event_name": "The name of the scam/project as identified from sources",
      "analysis_date": "YYYY-MM-DD",
      "data_sources_summary": "Brief list or description of the primary sources used for this reconstruction"
    },
    "narrative": {
      "overview": "A comprehensive paragraph summarizing the entire event.",
      "detailed_chronology": [
        {
          "phase": "Inception & Planning",
          "description": "Key actions in setting up the scam.",
          "timestamp_estimate": "e.g., Q2 2021"
        },
        {
          "phase": "Promotion & Fundraising Peak",
          "description": "Description of the main promotional activities and period of maximum investment inflow.",
          "timestamp_estimate": "e.g., Q3 2021 - Q1 2022"
        },
        {
          "phase": "Sustenance & Signs of Trouble",
          "description": "How the scam maintained appearance and early warning signs.",
          "timestamp_estimate": "e.g., Q2 2022"
        },
        {
          "phase": "Collapse & Termination",
          "description": "The trigger and immediate events of the collapse.",
          "timestamp_estimate": "e.g., Month 2022"
        },
        {
          "phase": "Aftermath & Resolution",
          "description": "Legal actions, investor recovery efforts, and long-term impacts.",
          "timestamp_estimate": "e.g., 2022-Ongoing"
        }
      ]
    },
    "key_entities": {
      "perpetrators": [
        {
          "name_or_alias": "Name, pseudonym, or entity",
          "role": "e.g., Founder, Fake CEO, Lead Developer, Marketer",
          "known_actions": "Summary of their involvement",
          "final_status": "e.g., At large, Arrested, Charged, Convicted"
        }
      ],
      "victim_profile": {
        "estimated_count": "Number or range",
        "geographic_distribution": "General regions or countries",
        "attraction_factor": "Primary reason victims invested (e.g., high yield promises, influencer trust)"
      },
      "other_impacted_parties": "e.g., Legitimate crypto projects caught in fallout, exchanges that listed the token, regulatory bodies involved"
    },
    "financial_mechanics": {
      "product_description": "Description of the fake product, token, or service.",
      "investment_process": "Step-by-step how investors sent funds.",
      "promised_returns": "The explicit or implied return on investment offered.",
      "actual_use_of_funds": {
        "stated_purpose": "What the whitepaper/website claimed.",
        "actual_allocation_evidence": "Based on sources, how funds were likely used (e.g., 60% Ponzi payouts, 30% perpetrator luxury, 10% fake marketing).",
        "misappropriation_confirmed": "Boolean: true or false based on evidence."
      },
      "ponzi_structure_analysis": {
        "was_ponzi": "Boolean",
        "mechanism": "How new investor funds were used to pay fake returns to earlier investors.",
        "critical_failure_point": "The mathematical or liquidity reason the scheme was unsustainable."
      }
    },
    "quantitative_analysis": {
      "timeline": {
        "start_date_estimate": "YYYY-MM-DD or YYYY-MM",
        "end_date_estimate": "YYYY-MM-DD or YYYY-MM",
        "duration_months": "Number"
      },
      "funds_raised": {
        "estimated_total_usd": "Number in USD",
        "estimated_total_crypto": "e.g., 50,000 ETH",
        "valuation_note": "How the estimate was derived (e.g., based on wallet addresses, platform data)."
      },
      "at_collapse": {
        "total_investors": "Estimated number",
        "total_investor_loss_usd": "Estimated net loss",
        "perpetrator_assets_traceable_usd": "Estimated recoverable assets at collapse",
        "capital_shortfall_usd": "Total principal - traceable assets",
        "promised_return_shortfall_usd": "Total promised returns - traceable assets"
      },
      "post_liquidation_recovery": {
        "estimated_recovery_rate": "e.g., 10%",
        "estimated_final_shortfall_usd": "Amount likely never recovered",
        "recovery_process_status": "e.g., Ongoing, Stalled, Complete"
      }
    },
    "consequences_analysis": {
      "direct_impact": "Summary of investor losses and perpetrator outcomes.",
      "systemic_impact": "Impact on the broader cryptocurrency/ICO landscape, regulatory changes, market sentiment.",
      "legal_regulatory_response": "Actions taken by authorities in response to this specific event."
    },
    "assumptions_and_data_gaps": [
      "List any key assumptions made due to missing data in sources.",
      "Note any significant data points that could not be verified."
    ]
  }
}
"""