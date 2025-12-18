def embezzlement_misappropriation_of_funds_prompt() -> str:
    return """
You are a Forensic Historian and Financial Crime Reconstruction Specialist.

**Objective:** To deconstruct a specific instance of 'Embezzlement / Misappropriation of Funds' into its exhaustive constituent parts, analyzing it through the six-stage "Failure of Foresight" lifecycle model. Your task is to synthesize all available information—whether provided by the user or retrieved from trusted sources—into a singular, monumental, and microscopically detailed JSON reconstruction that captures the event in its full historical, operational, psychological, and systemic context.

**Output Format:** A single, extensive JSON object. The output must be in English.

**Instructions for JSON Construction:**
1.  **Base Structure:** The JSON must follow the exact top-level key structure provided: `embezzlement_misappropriation_of_funds_reconstruction` containing `metadata`, `stage_I_-_notionally_normal_starting_point`, `stage_II_-_incubation_period`, `stage_III_-_precipitating_event`, `stage_IV_-_onset`, `stage_V_-_rescue_and_salvage`, `stage_VI_-_full_cultural_readjustment`.
2.  **Lifecycle Phases:** Populate each stage (I-VI) with multiple, deeply nested objects. Each object within a stage should represent a distinct thematic dimension (e.g., psychological, procedural, financial) of that phase. Do not merely describe; analyze and populate with concrete data points.
3.  **Granular Fields:** Every field, from the highest metadata point to the lowest descriptor within a stage, must be populated with specific, factual information. Use `"[Data not specified]"` only as a last resort. Descriptions should be rich, analytical, and precise.
4.  **Integrated Explanation:** For EVERY field in the JSON, its value must serve as its own explanation. The value should be a detailed, self-contained sentence or data point that implicitly clarifies the field's purpose. (Example: For field `"regulatory_climate"`, the value should be something like `"A period of deregulation in the [Industry] sector, characterized by the repeal of [Specific Act] and a 'light-touch' supervisory philosophy from agencies like [Agency Name], which reduced the frequency and depth of audits."`).
5.  **Fact-Based:** All information must be grounded in the actual details of the case. Cite specific laws, named individuals, exact monetary figures, dates, internal memo titles, audit report names, etc. Infer connections and systemic conditions, but do not invent facts.
6.  **Comprehensiveness:** Strive for a holistic view. Include dimensions often overlooked: the perpetrator's personal and professional background, the specific technological or accounting methods used to conceal the fraud, the internal culture of the affected organization(s), the role of intermediaries, the psychological impact on victims, the precise legal arguments used in prosecution/defense, and the long-term reputational and market consequences.

Here is the required JSON schema outline with exemplary field descriptions, and "Explanation" is just to help you better understand the task. **Populate it with data from the target case.**

{
  "embezzlement_misappropriation_of_funds_reconstruction": {
    "metadata": {
      "scheme_common_name": "The most widely recognized name for the scheme, e.g., 'The [Company Name] Accounting Scandal' or 'The [Perpetrator Name] Embezzlement'.",
      "official_legal_case_name": "The formal title(s) of the leading criminal or civil case(s), e.g., 'United States v. [Full Defendant Name], Case No. XXXXX' and '[Regulatory Body] v. [Entity], Docket No. YYYYY'.",
      "primary_perpetrator_name": "Full name of the key architect and operator. The individual who had the requisite trust (fiduciary duty) and actively orchestrated the misappropriation.",
      "perpetrator_background": {
        "position_title_at_time_of_fraud": "Their official job title and department, e.g., 'Chief Financial Officer', 'Treasury Manager', 'Partner in Charge of Client Funds'.",
        "tenure_at_organization": "Length of time they had been in that position and with the organization prior to the fraud's discovery.",
        "professional_reputation_prior": "Description of their standing among peers, industry awards, perceived trustworthiness, and prior career highlights.",
        "key_motivations_inferred_established": "Documented or strongly inferred drivers, e.g., 'Pressure to meet unrealistic earnings targets set by the board', 'Personal debt from gambling losses estimated at $X million', 'Desire to fund a lavish lifestyle including [specific assets]', or 'To conceal prior operational losses in a division under their control'."
      },
      "key_associated_entities": {
        "victim_entity": "The organization from which funds were directly misappropriated, e.g., 'XYZ Corporation Pension Fund'.",
        "vehicle_entities": ["Shell companies, nominee accounts, or fake vendors created to receive and launder funds, e.g., 'Alpha Consulting LLC (Bahamas registered)'."],
        "financial_institutions_used": ["Banks, brokerages, or payment processors through which funds were funneled, noting specific branch or account manager complicity if any, e.g., 'Bank of A, Geneva Private Banking Division'."],
        "auditing_firm": "The external auditor responsible for the victim entity's financial statements during the fraud period."
      },
      "operational_timeframe": {
        "suspected_inception_date": "YYYY-MM-DD (or best estimate). The date of the first identified fraudulent transaction or decision to begin misappropriation.",
        "public_collapse_date": "YYYY-MM-DD. The date the scheme became publicly known, e.g., date of a regulatory filing, press release, or law enforcement announcement.",
        "duration_active": "X years, Y months. The total time from inception to collapse.",
        "key_milestone_dates": {
          "major_theft_episodes": ["YYYY-MM-DD: Description, e.g., 'Transfer of $50M to offshore vehicle under the guise of a fictitious acquisition.'"],
          "internal_inquiries_near_misses": ["YYYY-MM-DD: Description, e.g., 'Internal audit report #2020-15 raised questions about vendor 'Beta Ltd.', but was overridden by [Executive Name].'"],
          "regulatory_filings_concealing_fraud": ["YYYY-MM-DD: Description, e.g., 'Submission of Form 10-K to SEC materially overstating cash reserves by $200M.'"]
        }
      },
      "estimated_global_scale": {
        "currency_primary": "The denomination of the majority of misappropriated funds, e.g., 'USD'.",
        "total_misappropriated_nominal": "The sum of all principal funds directly taken or diverted, e.g., '$1.85 Billion'.",
        "estimated_financial_loss_including_opportunity_costs": "A broader measure including lost investment income, legal fees, reputational damage valuation, etc., e.g., '$2.3 Billion'.",
        "victim_profile": {
          "direct_victim_count": "Number of individuals or entities whose entrusted funds were directly taken.",
          "indirect_victim_count": "Estimated number affected by secondary consequences (e.g., employees laid off, shareholders, pensioners).",
          "primary_victim_categories": ["E.g., 'Corporate shareholders', 'Non-profit donors', 'Elderly trust fund beneficiaries', 'Municipal bond holders'."]
        },
        "geographic_reach_of_fraud_operations": ["List of jurisdictions where fraudulent transactions were orchestrated or funds were moved through, e.g., 'United States, Switzerland, Cayman Islands, Hong Kong'."],
        "geographic_reach_of_victim_impact": ["List of jurisdictions where victims resided, e.g., 'Primarily the United States, with significant pockets in the United Kingdom and Japan'."]
      }
    },
    "stage_I_-_notionally_normal_starting_point": {
      "cultural_and_regulatory_backdrop": {
        "prevailing_industry_ethics": "The accepted standard of conduct and oversight in the relevant sector (e.g., finance, philanthropy, government) at the time, e.g., 'An era of significant autonomy for fund managers with an emphasis on personal trust over systematic verification in the family office industry.'",
        "relevant_legal_framework": "Specific laws and regulations governing the entrusted funds that were in place at the start, e.g., 'The Employee Retirement Income Security Act (ERISA) of 1974, requiring fiduciaries of pension plans to act prudently and solely in the interest of participants.'",
        "standard_operating_procedures_sop": "The formal, written internal controls and approval processes supposedly governing fund access at the victim entity, e.g., 'Dual-signature requirement for any wire transfer over $10,000; monthly reconciliation of all accounts by an independent department; mandatory annual external audit.'"
      },
      "perpetrator_s_position_of_trust": {
        "formal_fiduciary_duties": "The legal obligations attached to their role, e.g., 'Duty of Care, Duty of Loyalty, Duty to Act in Good Faith as defined under state corporate law.'",
        "informal_social_capital": "The depth of personal trust bestowed upon them by superiors, colleagues, and victims, e.g., 'Seen as a 'company lifer' and pillar of the community; served on the board of the local charity with the CEO; personal friendships with major clients.'",
        "level_of_systemic_control": "A description of the combination of roles or access that enabled the fraud, e.g., 'Sole control over the electronic banking platform (with administrative rights), authority to approve vendor payments, and responsibility for presenting financials to the audit committee, creating a perfect concentration of incompatible functions.'"
      },
      "nature_of_the_entrusted_funds": {
        "fund_source": "The origin of the money, e.g., 'Employee pension contributions, client retainers for legal services, donor-restricted endowment funds for medical research.'",
        "stated_purpose": "What the funds were legally and ethically supposed to be used for, e.g., 'To be invested in a conservative portfolio of bonds and blue-chip stocks to pay future retiree benefits.'",
        "perceived_liquidity_and_visibility": "How accessible and frequently monitored the fund pool was, e.g., 'A 'set-and-forget' pension fund with quarterly performance reviews but no real-time transaction monitoring, held in a complex network of sub-accounts.'"
      }
    },
    "stage_II_-_incubation_period": {
      "initial_breaches_and_rationalizations": {
        "first_technical_violation": "The precise first action that breached protocol, however minor, e.g., 'On [Date], approved a $5,000 payment to a personal credit card from a corporate account, rationalizing it as a temporary 'loan' to be repaid before the quarterly close.'",
        "perpetrator_s_internal_rationalization": "The cognitive justification likely used, based on testimony or documented pressures, e.g., 'I deserve this after years of underpaid loyalty,' or 'This is just bridging a short-term liquidity gap that no one will notice.'",
        "gradual_normalization_of_deviance": "How small, unchallenged breaches led to larger ones, e.g., 'The unrepaid 'loan' was followed by creating a fictitious expense report to cover it, which then established a template for creating fake vendor invoices.'"
      },
      "systemic_control_failures_active": {
        "overridden_or_ignored_controls": "Specific instances where existing SOPs were bypassed, e.g., 'The dual-signature rule was circumvented by having the perpetrator forge the second signature on paper forms or manipulate the digital approval workflow by using a subordinate's login.'",
        "exploited_control_gaps": "Weaknesses in the system that were discovered and used, e.g., 'The internal audit department only sampled transactions above $50,000, so thefts were structured as multiple sub-$50,000 payments to the same fake entity.'",
        "technological_enablers": "Software or systems used to conceal activity, e.g., 'Used advanced access to the accounting software (SAP/Oracle) to create false journal entries that redirected funds after legitimate transactions were logged, and to suppress automated alert flags.'"
      },
      "warning_signals_and_their_suppression": {
        "internal_red_flags": "Specific concerns raised by employees, junior accountants, or automated systems, e.g., '[Date]: Whistleblower email from accounts payable clerk regarding unusual payment patterns to 'Delta Holdings', marked 'Resolved' by the perpetrator without investigation.'",
        "external_red_flags": "Concerns from auditors, regulators, or business partners that were dismissed, e.g., '[Date]: External auditor's management letter highlighted 'lack of segregation of duties in treasury function' for three consecutive years, but the board's audit committee deemed it a 'cost-saving measure'.'",
        "methods_of_suppression": "How the perpetrator or complicit management quashed concerns, e.g., 'Threatened the whistleblower with termination for 'poor performance'; charmed the audit partner with lavish entertainment; provided forged bank confirmations and contracts to regulators.'"
      },
      "financial_concealment_mechanics": {
        "accounting_fraud_method": "The specific technical method used to hide the missing funds on the books, e.g., 'Capitalizing operating expenses related to the theft as 'Goodwill' or 'Intangible Assets' to inflate the balance sheet artificially.'",
        "cash_flow_masking": "How liquidity was maintained to avoid suspicion, e.g., 'Used new investor deposits (a Ponzi-like element) to cover scheduled payouts to earlier victims, creating the illusion of normal returns.'",
        "document_forgery_details": "Types of documents fabricated, e.g., 'Forged bank statements using sophisticated graphic design software; created entirely false loan agreements with non-existent entities; fabricated board minutes approving the fraudulent transactions.'"
      }
    },
    "stage_III_-_precipitating_event": {
      "the_triggering_event": {
        "event_description": "The specific, uncontrollable occurrence that made continuation impossible, e.g., 'A major corporate client unexpectedly requested an early withdrawal of its entire $300 million investment for an acquisition opportunity, creating an immediate cash demand that could not be met with fictitious assets.'",
        "nature_of_event": "Categorize it, e.g., 'External Market Shock (e.g., 2008 liquidity freeze)', 'Internal Operational Demand (e.g., large redemption)', 'Unavoidable Regulatory Deadline (e.g., mandatory audit with direct bank confirmation)', or 'Loss of a Key Enabler (e.g., complicit bank manager retired and was replaced).'",
        "date_and_immediate_context": "The precise timing and surrounding circumstances, e.g., 'On the morning of October 15, 20XX, following a 20% market drop the previous week, redemption requests from panicked investors spiked to $500M in a single day, overwhelming the scheme's ability to rotate funds.'"
      },
      "failure_of_last_resort_measures": {
        "desperate_actions_taken": "Final attempts to plug the hole, e.g., 'Attempted to secure a fraudulent loan of $100M from a new bank using completely fabricated financials; tried to pressure a few large investors to postpone withdrawals with promises of astronomical bonus returns.'",
        "why_they_failed": "The reason these last-ditch efforts collapsed, e.g., 'The new bank's due diligence department requested direct access to the primary custodian bank records, which would have revealed the forgeries immediately; the large investors consulted their lawyers who advised against the irregular arrangement.'"
      },
      "point_of_no_return": {
        "decision_to_disclose": "Who made the decision to stop concealing and why, e.g., 'Facing imminent discovery by the incoming auditor who had scheduled direct bank verifications, the perpetrator confessed to their superior in a private meeting on [Date].'",
        "initial_disclosure_forum": "The first official channel through which the fraud was acknowledged, e.g., 'An emergency teleconference of the Board of Directors', 'A 'Dear Investor' letter from the fund manager', or 'A voluntary disclosure to the [Securities Commission] by the company's general counsel.'"
      }
    },
    "stage_IV_-_onset": {
      "immediate_financial_collapse": {
        "freeze_of_assets": "Official actions taken to secure remaining assets, e.g., '[Date]: The [Court Name] issued a temporary restraining order freezing all accounts of [Entity] and appointing a receiver.'",
        "public_announcement_impact": "Market or institutional reaction to the news, e.g., 'Company's stock (Ticker: XYZ) plunged 85% in pre-market trading and was halted by the exchange; credit rating agencies downgraded the entity to 'Default' status.'",
        "liquidity_crisis_for_victims": "The immediate consequence for those reliant on the funds, e.g., '30,000 retirees were notified that their monthly pension payments would be suspended indefinitely; a cancer research hospital halted three clinical trials due to frozen grant funds.'"
      },
      "organizational_implosion": {
        "key_departures_and_suspensions": "Immediate personnel actions, e.g., 'The CEO and entire C-suite were placed on administrative leave by the board; the Head of Internal Audit resigned effective immediately.'",
        "operational_paralysis": "State of the victim entity, e.g., 'All non-essential spending was frozen; a moratorium was placed on new investments; the headquarters was closed to the public as law enforcement secured evidence.'"
      },
      "initial_legal_and_regulatory_response": {
        "first_regulatory_filing": "The official document that triggered public enforcement, e.g., '[Date]: The Securities and Exchange Commission filed an emergency civil complaint (Case No. XX-CV-XXXX) alleging violations of Sections 10(b) and 17(a) of the Securities Exchange Act of 1934.'",
        "first_law_enforcement_action": "Initial arrests or criminal charges, e.g., '[Date]: The perpetrator was arrested at their home by the FBI on a criminal complaint charging one count of wire fraud. Bail was denied due to flight risk.'",
        "emergency_hearings": "Initial court proceedings, e.g., '[Date]: A 72-hour emergency hearing in bankruptcy court to authorize the receiver's powers and establish a claims process for victims.'"
      },
      "media_and_public_reaction_initial": {
        "headline_narrative": "The dominant framing in early media coverage, e.g., '‘Trusted CFO Betrays Lifelong Colleagues in Billion-Dollar Heist’ splashed across the front page of the [Major Newspaper].'",
        "victim_statements_early": "Quotes or sentiments from the first victims to speak publicly, e.g., 'A 75-year-old former employee stated, 'I've lost everything I worked 40 years for. I don't know how I'll pay my medical bills.''",
        "industry_shockwaves": "Immediate reactions from peers and competitors, e.g., 'The [Industry] Association issued a statement expressing 'profound dismay' and announced a special task force on governance.'"
      }
    },
    "stage_V_-_rescue_and_salvage": {
      "stabilization_efforts": {
        "appointment_of_authorities": "The independent parties put in charge, e.g., '[Date]: The court appointed [Name of Law Firm] as Independent Examiner and [Name of Consulting Firm] as Chief Restructuring Officer to take over daily operations.'",
        "forensic_investigation_launch": "The formal beginning of the fact-finding mission, e.g., '[Date]: The receiver engaged [Forensic Accounting Firm] to conduct a global asset trace, imaging all servers and seizing physical records from 15 offices worldwide.'",
        "emergency_funding_for_victims": "Any immediate relief provided, e.g., '[Date]: A state government emergency fund released $10M to cover one month of suspended pension payments for the most vulnerable retirees.'"
      },
      "asset_recovery_initial_phase": {
        "identified_recoverable_assets": "Initial findings on where the money went, e.g., 'Investigators identified real estate purchases in [Location] worth ~$40M, a private art collection valued at $15M, and numerous luxury vehicles.'",
        "first_asset_freezes_and_seizures": "Legal actions to reclaim, e.g., '[Date]: Prosecutors obtained a seizure warrant for the perpetrator's primary residence, three vacation homes, and four bank accounts in Switzerland via mutual legal assistance.'",
        "clawback_actions_initiated": "Lawsuits against beneficiaries of the fraud, e.g., '[Date]: The receiver sued 50 'net winners'—investors who had withdrawn more than their principal in the years before collapse—to claw back $120M in 'fictitious profits'.'"
      },
      "crisis_management_and_communication": {
        "victim_communication_channel": "How victims were kept informed, e.g., 'A dedicated website and 24/7 hotline were established; weekly town hall meetings were held via webinar.'",
        "official_narrative_from_new_management": "Key messages from the restructured entity, e.g., 'The new CEO's first public statement: 'Our sole focus is on recovering every possible cent for the victims and cooperating fully with authorities. The old governance system has been completely dismantled.''"
      },
      "early_legal_maneuvering": {
        "perpetrator_s_initial_legal_strategy": "First moves by the defense, e.g., 'The perpetrator's attorney filed a motion arguing for house arrest, citing cooperation and health issues, while simultaneously negotiating a plea deal on some charges.'",
        "civil_litigation_flood": "The first wave of private lawsuits, e.g., '[Date]: A class-action lawsuit was filed on behalf of all investors against the entity, its directors, and its auditing firm for gross negligence.'"
      }
    },
    "stage_VI_-_full_cultural_readjustment": {
      "official_investigations_and_reports": {
        "government_commission_report": "Findings of any official public inquiry, e.g., '[Date]: The [Congressional Committee/Parliamentary Commission] released a 500-page report titled 'The [Scandal Name] Failure', concluding that 'systemic regulatory capture and a culture of deference' were root causes.'",
        "regulatory_sanctions_and_settlements": "Final penalties against entities, e.g., '[Date]: The auditing firm agreed to pay a $100 million penalty to the [Regulator] and admit to failure in its professional standards, while neither admitting nor denying the findings.'",
        "sentencing_of_perpetrator": "Final legal outcome for the primary actor, e.g., '[Date]: The perpetrator was sentenced to 25 years in federal prison, ordered to forfeit $1.2 billion, and delivered a statement expressing 'remorse and shame' to the courtroom filled with victims.'"
      },
      "systemic_reforms_implemented": {
        "new_laws_and_regulations": "Legislation enacted in response, e.g., 'The [Scandal Name] Prevention Act of 20XX, which mandated real-time transaction reporting for private funds, strengthened whistleblower protections, and increased penalties for misappropriation.'",
        "changes_to_industry_standards": "Revised professional codes and practices, e.g., 'The [Professional Accounting Body] amended its auditing standards to require mandatory data analytics testing on 100% of high-risk transactions and direct confirmation of bank balances in all audits.'",
        "internal_control_overhauls_at_victim_entity": "Specific governance changes made, e.g., 'The company implemented a four-eyes principle on all payments, established a direct-reporting hotline to the audit committee, and mandated annual forensic audits for all high-cash-flow divisions.'"
      },
      "long_term_consequences_and_legacy": {
        "financial_recovery_rate_for_victims": "The final percentage of principal recovered, e.g., 'As of the final distribution in 20XX, victims had recovered approximately 62 cents on the dollar after 8 years of litigation and asset sales.'",
        "reputational_impact_on_key_entities": "Lasting brand damage, e.g., 'The 150-year-old auditing firm involved was forced to sell its consulting arm and saw its market share for public company audits drop by 40% over the next decade.'",
        "cultural_shift_in_perception_of_trust": "Enduring change in attitudes, e.g., 'The scandal permanently eroded public trust in [Industry Sector], leading to a generational shift where institutional investors now routinely demand independent custodians and much deeper operational due diligence, irrespective of personal relationships.'",
        "academic_and_professional_case_study": "How the event entered pedagogy, e.g., 'The case became a staple in business ethics, forensic accounting, and corporate governance curricula at major universities, often under the title '[Scandal Name]: A Perfect Storm of Failed Controls'.'"
      },
      "final_narrative_assessment": {
        "dominant_historical_interpretation": "The synthesized understanding of the event's causes, e.g., 'Widely regarded as a failure at three levels: an individual's moral collapse, an organization's control failure, and a regulatory system's complacency. It demonstrated that excessive trust concentrated in a single, charismatic individual, without rigorous systemic checks, is a profound risk.'",
        "unresolved_questions_and_conspiracy_theories": "Aspects that remain debated, e.g., 'Persistent theories, never proven, suggest higher-level executives were complicit. The fate of an estimated $50M transferred to a jurisdiction with no extradition treaty remains officially unresolved.'"
      }
    }
  }
}
"""