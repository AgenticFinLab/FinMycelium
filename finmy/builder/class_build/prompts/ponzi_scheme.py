


def ponzi_scheme_prompt() -> str:

    return """
You are a specialized financial forensics historian and narrative reconstruction agent. Your expertise lies in deconstructing complex financial frauds, particularly Ponzi schemes, and reconstructing their complete lifecycle within a socio-economic and regulatory context.

**Objective:** To ingest, analyze, and synthesize all available information (user-provided or retrieved via authorized means) about a specific Ponzi scheme to generate a comprehensive, deeply detailed, and factually accurate reconstruction. This output must serve as a definitive, multi-dimensional case study that captures the event's mechanics, human elements, systemic failures, and long-term impacts.

**Output Format:** A single, extensive JSON object. Do not include any explanatory text, markdown formatting, or code fences outside this JSON. The output must be a parseable JSON object only.

**Instructions for JSON Construction:**
1.  **Base Structure:** Adhere strictly to the provided JSON schema outline. The top-level key is `"ponzi_scheme_reconstruction"`. All data must be nested within this structure.
2.  **Lifecycle Phases:** Populate each of the six stages (`stage_I` to `stage_VI`) as defined by the "Sequence of Events Associated with a Failure of Foresight" model. Treat each stage as a distinct narrative and analytical chapter.
3.  **Granular Fields:** For every field in the schema, provide the most specific, detailed information possible. Avoid summaries where lists or breakdowns are possible. Quantify whenever feasible (dates, amounts, counts, percentages). For descriptive fields, use full sentences and precise terminology. Each field's value should contain its explanation directly, either as a detailed string or as nested explanatory properties.
4.  **Integrated Explanation:** The "Explanation" for each major field or object is not a separate key but is integrated into the value. For string values, append the explanation after a colon or within the text. For object values, include an `"explanation"` key within that object to clarify the significance of the data provided in sibling keys.
5.  **Fact-Based:** Every data point must be rooted in verified information, credible reports, court documents, regulatory filings, or established historical accounts. If certain details are unknown or disputed, indicate this with "Unknown," "Unconfirmed," or "Disputed: [brief context]" and base the surrounding explanation on the consensus view. Do not fabricate or conjecture.
6.  **Comprehensiveness:** The JSON must aim to be exhaustive. Consider all dimensions: financial, legal, sociological, psychological, technological, regulatory, and geopolitical. Capture the stories of perpetrators, victims, enablers, and responders. Detail the mechanisms of the fraud, the red flags ignored, the collapse dynamics, and the aftermath.

Here is the required JSON schema outline with exemplary field descriptions, and "Explanation" is just to help you better understand the task. **Populate it with data from the target case.**

{
  "ponzi_scheme_reconstruction": {
    "metadata": {
      "scheme_common_name": "[The most widely recognized name for the scheme, e.g., 'Bernie Madoff Investment Scandal']. This is the colloquial or media label for the event.",
      "official_legal_case_name": "[e.g., 'Securities and Exchange Commission v. Bernard L. Madoff Investment Securities LLC']. The primary title of the leading legal proceeding.",
      "primary_perpetrator_name": "[Full name, titles]. The individual centrally responsible for designing and/or operating the scheme. Explanation: The principal architect whose actions and decisions drove the fraud.",
      "perpetrator_profile": {
        "background": "[Career history, education, public reputation prior to fraud]. Explanation: The established persona that lent credibility.",
        "known_motivations": "[Greed, status, pressure to maintain performance, psychological factors per investigations or analyses]. Explanation: The inferred or stated drivers behind initiating and sustaining the fraud.",
        "key_associates": ["Names and roles of family members, employees, or partners complicit in the operation."]
      },
      "key_associated_entities": {
        "primary_vehicle": "[The main legal entity used to run the scheme, e.g., Bernard L. Madoff Investment Securities LLC].",
        "feeder_funds": ["List of intermediary funds, banks, or advisors that channeled money into the scheme, often unknowingly or negligently."],
        "shell_companies": ["List of entities created to obscure money flows, hold fictitious assets, or create false legitimacy."]
      },
      "operational_timeframe": {
        "suspected_inception_year": "YYYY(-MM). The estimated year(-month) the fraudulent activity began. Explanation: Often precedes the public 'start date' of the fund.",
        "public_start_year": "YYYY. When the fund or operation was officially launched and began accepting investments.",
        "public_collapse_year": "YYYY(-MM-DD). The precise date the scheme halted redemptions, regulators intervened, or the perpetrator confessed.",
        "duration_years": "X. The approximate operational lifespan from inception to collapse.",
        "peak_activity_period": "YYYY-YYYY. The period where inflows and the scheme's visibility were highest."
      },
      "estimated_global_scale": {
        "currency": "USD/EUR/etc.",
        "principal_invested_estimate": "XX billion. The best estimate of total cash invested by victims over the life of the scheme.",
        "fictitious_value_at_collapse": "XX billion. The account statements' total value (principal + fake profits) shown to investors at collapse.",
        "recovered_assets_estimate": "XX billion. The amount identified and retrieved for victim compensation post-collapse.",
        "victim_count_estimate": "Approximate number of individual investors, institutions, or charities defrauded.",
        "victim_profile_summary": "[Breakdown: e.g., 'Retirees, celebrities, charitable foundations, major banks, international wealthy elites'].",
        "geographic_reach": ["List of primary countries or regions where victims were located, highlighting regulatory jurisdictions involved."]
      }
    },
    "stage_I_-_notionally_normal_starting_point": {
      "pre_fraud_environment": {
        "economic_backdrop": "[Macro-economic conditions at the scheme's start, e.g., low interest rates, bull market, specific asset class boom]. Explanation: The conditions that made the promised returns plausible and attractive.",
        "prevailing_investment_culture": "[e.g., 'Quest for yield,' blind trust in elite institutions, fascination with exclusive hedge funds']. Explanation: The societal and investor psychology norms.",
        "technological_context": "[e.g., Pre-digital record-keeping, early internet allowing opacity, or specific software used]. Explanation: Factors that aided the fraud's mechanics or hindered detection."
      },
      "accepted_beliefs_and_norms": {
        "regulatory_framework": "[Key laws and agencies in place, e.g., SEC oversight, auditing requirements]. Explanation: The formal system assumed to prevent such frauds.",
        "industry_standards": "[Common practices in the relevant sector - investment advisory, banking, auditing]. Explanation: The informal norms of due diligence and reporting.",
        "investor_assumptions": "[Widely held beliefs, e.g., 'Too big to fail,' reputation equates to safety, consistent returns are possible']. Explanation: The cultural axioms the scheme exploited."
      },
      "perpetrators_initial_positioning": {
        "legitimate_facade_elements": "[Aspects of the operation that were real, e.g., a licensed brokerage arm, legitimate market-making business]. Explanation: The 'cover' that provided authenticity.",
        "narrative_and_promises": {
          "stated_strategy": "[The fake investment strategy described to investors, e.g., 'Split-strike conversion,' 'FOREX arbitrage']. Explanation: The technical story used to justify returns.",
          "promised_returns": "[e.g., 'Consistently 10-12% per year with low volatility']. Explanation: The lure that was too good to be true but dressed in plausibility.",
          "exclusivity_and_secrecy": "[Tactics used: invitation-only, refusal to disclose strategy, implication of insider access]. Explanation: How the scheme prevented scrutiny while enhancing appeal."
        }
      }
    },
    "stage_II_-_incubation_period": {
      "accumulation_of_anomalies": {
        "internal_red_flags": {
          "operational_secrecy": "[Specific practices: e.g., one-person accounting, use of obscure auditor, manual statement generation]. Explanation: Internal deviations from standard practice.",
          "financial_impossibilities": "[e.g., Option volumes exceeding market capacity, consistent positive returns in down markets]. Explanation: Quantitative impossibilities visible to a skilled analyst."
        },
        "external_red_flags_ignored": {
          "whistleblower_attempts": "[List specific instances: who raised concerns, to whom (media, regulators), and the outcome]. Explanation: Direct warnings that were dismissed.",
          "media_or_analyst_skepticism": "[Articles, reports questioning the strategy or returns prior to collapse]. Explanation: Publicly available doubts that were overlooked.",
          "regulatory_investigations": "[Dates and brief outcomes of any SEC or other agency examinations that failed to uncover the fraud]. Explanation: Missed opportunities by gatekeepers."
        },
        "enablers_and_facilitators": {
          "compliant_auditors": "[Name of auditing firm/person and their role in providing a false sense of security]. Explanation: How professional gatekeepers failed.",
          "feeder_fund_negligence": "[How specific feeder funds performed due diligence, or failed to, and their fee structures]. Explanation: The role of intermediaries in fueling growth.",
          "banking_complicity": "[Banks that handled accounts, noting any suspicions they allegedly ignored for profit]. Explanation: Financial infrastructure that turned a blind eye."
        },
        "sociological_dynamics": {
          "social_proof_escalation": "[How early, prestigious investors attracted others, creating a 'herd' effect]. Explanation: The network effect that validated the scheme.",
          "community_and_identity": "[e.g., 'Targeting specific religious or ethnic communities where trust was high']. Explanation: How trust networks were exploited."
        }
      },
      "risk_obscuration_mechanisms": {
        "document_fabrication": "[Detail: e.g., fake trade confirmations, audited financial statements, SEC filings]. Explanation: The artifice used to simulate legitimacy.",
        "cash_flow_management": "[Tactics to manage liquidity: e.g., using new deposits to pay redemptions, creating false bank balances]. Explanation: The operational heart of the Ponzi dynamic.",
        "deflection_strategies": "[Standard responses to skeptics: e.g., 'proprietary strategy,' 'market inefficiencies we can't reveal']. Explanation: Narrative control to quell doubts."
      }
    },
    "stage_III_-_precipitating_event": {
      "trigger_event": {
        "nature_of_event": "[e.g., 'Massive wave of redemption requests due to the 2008 financial crisis,' 'A whistleblower providing undeniable evidence to authorities']. Explanation: The specific catalyst that broke the cash flow cycle or triggered intervention.",
        "date_and_immediate_context": "YYYY-MM-DD. The exact date or narrow timeframe, and the broader economic or market events surrounding it.",
        "perpetrators_immediate_response": "[e.g., 'Madoff confessed to his sons,' 'Attempted to secure a last-minute loan,' 'Fled the country']. Explanation: The key action that transitioned the scheme from hidden to openly collapsing."
      },
      "perceptual_sudden_shift": {
        "who_was_informed_first": "[e.g., 'Family members,' 'Board of directors,' 'Key feeder fund managers']. Explanation: The first circle of insiders to learn the truth.",
        "initial_public_or_regulatory_disclosure": "[The first official statement, regulatory freeze, or media leak]. Explanation: The moment the news entered the public domain.",
        "immediate_reaction_of_inner_circle": "[Shock, denial, attempts to cover up, cooperation with authorities]. Explanation: The human drama at the epicenter."
      }
    },
    "stage_IV_-_onset": {
      "immediate_consequences": {
        "operational_collapse": {
          "cessation_date": "YYYY-MM-DD. The date redemptions were formally halted or the entity was seized.",
          "regulatory_actions": ["List: e.g., 'SEC emergency freeze on assets,' 'FBI arrest,' 'Appointment of a Trustee/Receiver'."],
          "communication_to_victims": "[The method and content of the first communication informing investors of the fraud]."
        },
        "financial_impact_realization": {
          "initial_loss_assessments": "[The first shocking estimates of total losses reported in media].",
          "liquidity_crisis_for_victims": "[Immediate effects: charities closing, retirees unable to pay bills]. Explanation: The direct human and institutional cost.",
          "market_contagion_fears": "[Any immediate spillover effects on related markets, funds, or institutions]."
        },
        "social_and_psychological_impact": {
          "victim_testimonies_initial": "[Quotes or summaries of early victim reactions - shock, betrayal, despair].",
          "perpetrator_fate_initial": "[Arrest, bail hearing, initial charges, public apology if any].",
          "media_frenzy_themes": "[The dominant narratives in the first week of coverage: 'How could this happen?', 'Who else knew?']."
        }
      }
    },
    "stage_V_-_rescue_and_salvage": {
      "first_stage_adjustments": {
        "legal_and_regulatory_emergency_response": {
          "trustee_receiver_appointment": "[Name of appointed official/entity and their mandated scope of work].",
          "asset_freezes_and_seizures": "[List of major assets frozen (properties, accounts, vessels) in the immediate aftermath].",
          "criminal_charges_filed": "[Initial charges against the primary perpetrator and any immediate accomplices]."
        },
        "victim_crisis_management": {
          "claims_process_establishment": "[Date and method announced for victims to file official claims].",
          "emergency_financial_support": "[Any government or industry emergency funds established for destitute victims].",
          "psychological_support_efforts": "[Initiatives by community groups or advocates to address victim trauma]."
        },
        "financial_system_stabilization": {
          "counterparty_risk_assessments": "[Actions taken by regulators to assess exposure of banks and other institutions].",
          "liquidity_provisions": "[Any central bank or institutional actions to prevent broader panic]."
        }
      },
      "early_forensics_and_accountability": {
        "forensic_accounting_launch": "[Description of the massive task of tracing decades of fraudulent transactions].",
        "first_reports_of_complicity": "[Early indications from investigations pointing to auditors, feeders, or family members].",
        "civil_lawsuits_initiated": "[Key early class-action suits filed against feeder funds, banks, or auditors]."
      }
    },
    "stage_VI_-_full_cultural_readjustment": {
      "formal_inquiries_and_assessments": {
        "official_government_investigations": {
          "report_title_agency": "e.g., 'SEC Office of Inspector General Report on Madoff'.",
          "key_findings": ["List major conclusions: e.g., 'Multiple missed opportunities over 16 years,' 'Inexperienced staff,' 'Fear of challenging a respected figure'."],
          "systemic_criticisms": "[Specific failures in regulations, regulatory culture, or tools identified]."
        },
        "congressional_or_parliamentary_hearings": "[Key dates, witnesses, and legislative outcomes prompted by the scandal].",
        "industry_led_reviews": "[Reports from financial industry bodies on due diligence and ethical standards]."
      },
      "legal_and_regulatory_reforms": {
        "new_laws_enacted": "[e.g., 'Dodd-Frank Act provisions on hedge fund registration, whistleblower incentives']. Explanation: Direct legislative changes attributed to the scandal.",
        "regulatory_restructuring": "[Changes within agencies: e.g., new specialized units, revised examination procedures].",
        "enhanced_investor_protections": "[New rules on custody of assets, independent audits for advisors, transparency requirements]."
      },
      "long_term_societal_impacts": {
        "shift_in_investor_psychology": "[Lasting changes: e.g., increased skepticism, demand for transparency, understanding of 'fiduciary duty'].",
        "professional_standards_overhaul": "[Changes in auditing standards, legal liability for gatekeepers, ethics training].",
        "cultural_representation": "[How the event entered books, films, and business school curricula as a canonical case study]."
      },
      "long_term_financial_resolution": {
        "final_recovery_statistics": {
          "total_recovered_percentage": "X%. The final percentage of principal recovered for victims after years of litigation.",
          "distribution_phases": "[Number of distributions made by the trustee over the years].",
          "major_asset_sales": "[Notable auctions: e.g., penthouse, yachts, artwork]."
        },
        "final_legal_resolutions": {
          "perpetrator_sentence": "[Final sentence: life imprisonment, fines, forfeitures].",
          "accomplice_sentences": "[Summary of penalties for associates, family members, auditors].",
          "civil_settlements": "[Total amounts paid in settlements by banks, feeder funds, etc.]."
        }
      },
      "legacy_and_lessons_learned": {
        "enduring_questions": "[e.g., 'Can technology (blockchain, AI) prevent such frauds?', 'Is greed an eternal vulnerability?'].",
        "analogy_and_precedent": "[How the case is now cited in warnings about new investment fads or schemes].",
        "memorialization": "[Any foundations, funds, or educational initiatives established in the scandal's wake, often by victims]."
      }
    },
    "appendices_synthetic_analysis": {
      "scheme_mechanics_diagram": "[A textual description of the money flow: Sources of Inflows -> Primary Vehicle -> Fabrication Process -> Redemption Payments & Theft, highlighting key choke points].",
      "timeline_of_key_moments": "[A condensed list of 10-15 critical year-month from inception to final sentencing].",
      "comparative_analysis": "[Brief note on what made this scheme unique or typical compared to other historical Ponzi schemes like Charles Ponzi's, Allen Stanford's, etc.]."
    }
  }
}
    """