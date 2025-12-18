def forex_binary_options_fraud_prompt() -> str:
    return """
You are a Forensic Financial Historian and Systemic Risk Analyst.

**Objective:** To reconstruct a comprehensive, granular, and historically accurate narrative of a specific "Forex / Binary Options Fraud" case. Your output must function as a detailed cinematic documentary script in data form, capturing the entire lifecycle of the fraud—from its ideological origins in a permissive environment to its collapse and the subsequent regulatory and cultural aftermath.

**Output Format:** A single, extensive JSON object. Ensure the JSON is valid and parsable.

**Instructions for JSON Construction:**

1.  **Base Structure:** The JSON must have a root key `"forex_binary_options_fraud"`. The primary structure follows the "Sequence of Events Associated with a Failure of Foresight" lifecycle (Stages I-VI), preceded by a comprehensive `metadata` section and followed by `concluding_analysis`.

2.  **Lifecycle Phases:** Populate each stage (I through VI) as a separate object. Each stage must contain multiple thematic sub-objects (e.g., `socio_economic_context`, `regulatory_landscape`, `perpetrator_actions`). Each sub-object should contain specific, granular fields that provide evidentiary detail.

3.  **Granular Fields:** Every field must be populated with concrete, specific information. Avoid generalizations. Use dates, figures, names of specific software, exact regulatory loopholes cited, verbatim marketing claims, specific victim demographics, precise legal charges, and detailed quotes from officials or court documents where available.

4.  **Integrated Explanation:** For EVERY field in the JSON (including nested ones), you MUST provide an **"explanation"** key. The value of this key must be a string that explains *why this specific piece of data is significant* to understanding that aspect of the fraud's story. This explanation is part of the data narrative, not a meta-comment. It should clarify the datum's role, consequence, or symbolic meaning.

5.  **Fact-Based:** All data must be derived from the user-provided materials or from verified internet sources (e.g., SEC litigation releases, FCA final notices, CFTC complaints, reputable financial news investigations, court judgments). In case of conflicting information, prioritize official regulatory or legal documents. If certain details are unavailable, you may note "Data not specifically identified in sources" but strive for completeness.

6.  **Comprehensiveness:** The JSON must paint a complete picture. Consider all angles: technological mechanisms of fraud, psychological manipulation tactics (e.g., high-pressure sales scripts, fake testimonials), operational logistics (e.g., boiler room locations, payment processors), regulatory failures, victim psychology and demographics, legal strategies of both prosecution and defense, media narrative shifts, and long-term industry impacts.

Here is the required JSON schema outline with exemplary field descriptions, and "Explanation" is just to help you better understand the task. **Populate it with data from the target case.**

{
  "forex_binary_options_fraud_reconstruction": {
    "metadata": {
      "scheme_common_name": {
        "value": "The '[The most widely recognized name for the scheme, e.g., 'Wolf of Tel Aviv' or 'Banc de Binary' scandal]'",
        "explanation": "This is the colloquial or media-given name that encapsulates the public perception of the fraud, often highlighting its scale, method, or key figure."
      },
      "official_legal_case_name": {
        "value": "[e.g., 'Securities and Exchange Commission v. Spot Options and Ran Amiran et al.', 'FCA vs. 24option.com']",
        "explanation": "The formal title of the lead or most representative regulatory or criminal case, establishing the legal framework for the response."
      },
      "primary_perpetrator_entities": {
        "value": ["List of the key corporate entities used to perpetrate the fraud, e.g., 'Prestige Ventures Ltd (Cyprus)', 'Global Trade Solutions LLC (Belize)']",
        "explanation": "These shell companies or branded trading platforms were the direct vehicles for interacting with victims, holding funds, and creating a façade of legitimacy, often registered in offshore jurisdictions."
      },
      "key_individual_perpetrators": [
        {
          "name": "Full Name",
          "role": "e.g., Founder/CEO, Head of Sales, Chief Technology Officer",
          "nationality": "Country",
          "explanation": "This individual's specific function was crucial to the scheme's operation, such as designing the manipulative software or orchestrating the global sales network."
        }
      ],
      "operational_timeframe": {
        "suspected_inception": {
          "value": "YYYY-MM",
          "explanation": "The earliest identified date of fraudulent solicitation or platform operation, indicating when the risk began accumulating."
        },
        "peak_activity_period": {
          "value": "YYYY to YYYY",
          "explanation": "The period during which the scheme was most aggressively marketing and onboarding victims, often corresponding with high advertising spending."
        },
        "regulatory_action_onset": {
          "value": "YYYY-MM",
          "explanation": "The date of the first significant regulatory warning, fine, or restriction, marking the beginning of the scheme's external challenges."
        },
        "public_collapse_date": {
          "value": "YYYY-MM-DD",
          "explanation": "The date the platform ceased operations, filed for bankruptcy, or a major enforcement action was announced publicly, triggering widespread victim awareness."
        },
        "duration_active": {
          "value": "X years, Y months",
          "explanation": "The total lifespan, demonstrating the scheme's sustainability within the regulatory and market environment of the time."
        }
      },
      "estimated_global_scale": {
        "financial_scale": {
          "currency": "USD",
          "total_deposits_solicited": "e.g., 'Over $100 million'",
          "explanation": "The aggregate sum of funds victims were persuaded to deposit, representing the gross intake of the scheme."
        },
        "net_victim_losses": {
          "value": "e.g., 'Estimated $75 million'",
          "explanation": "The approximate amount of victim deposits that were never returned, representing the net financial damage after accounting for any 'winning' withdrawals used as bait."
        },
        "victim_count_estimate": {
          "range": "e.g., '10,000 - 15,000 individuals'",
          "explanation": "The estimated number of direct victims, illustrating the human scope and the challenge for class-action or restitution efforts."
        },
        "geographic_reach_of_victims": {
          "primary_countries": ["e.g., United Kingdom, Germany, Australia, Japan"],
          "secondary_countries": ["e.g., Canada, Italy, Singapore"],
          "explanation": "Highlights the transnational nature of the fraud, targeting countries with affluent retail investor populations but varying regulatory regimes."
        },
        "platform_metrics_at_peak": {
          "claimed_active_users": "e.g., 'Over 200,000 registered accounts'",
          "explanation": "A metric often used in marketing to create an illusion of popularity and legitimacy, though most accounts may have been dormant or fraudulent."
        }
      }
    },
    "stage_I_-_notionally_normal_starting_point": {
      "socio_economic_context": {
        "prevailing_retail_investor_sentiment": {
          "value": "e.g., 'Search for yield in a low-interest-rate environment post-2008; democratization of trading via online platforms'",
          "explanation": "Describes the macroeconomic and psychological backdrop that made retail investors susceptible to promises of high, quick returns from seemingly accessible markets."
        },
        "public_perception_of_forex_binary_options": {
          "value": "e.g., 'Perceived as a complex but potentially lucrative form of short-term speculation, often marketed as simpler than traditional forex.'",
          "explanation": "Captures the common understanding (or misunderstanding) of the product itself before the fraud revealed its dangers, often shaped by aggressive advertising."
        }
      },
      "regulatory_landscape_pre_fraud": {
        "legal_status_of_binary_options": {
          "value": "e.g., 'In the EU, binary options were classified as financial instruments under MiFID I/II, but specific marketing and product governance rules were evolving. In many other jurisdictions, they existed in a regulatory gray area.'",
          "explanation": "The ambiguous or under-developed regulatory classification created the space for operators to establish themselves before comprehensive rules were applied."
        },
        "dominant_regulatory_paradigm": {
          "value": "e.g., 'Jurisdictional licensing (e.g., CySEC in Cyprus, FCA in UK) with passporting rights across the EEA. Offshore entities operated largely outside any effective oversight.'",
          "explanation": "The system allowed 'regulated' entities to gain a veneer of credibility while the enforcement against cross-border fraud was fragmented and slow."
        },
        "known_loopholes_exploited": {
          "value": "e.g., 'Use of 'reverse solicitation' clauses to claim clients from non-passported countries approached them; outsourcing sales to unregulated third-party IB (Introducing Broker) networks.'",
          "explanation": "Specific gaps in the regulatory net that were deliberately targeted by the scheme's architects during its setup phase."
        }
      },
      "industry_norms_marketing_tactics": {
        "common_advertising_channels": {
          "value": "e.g., 'Aggressive use of online pop-up ads, sponsored social media content (Facebook, YouTube), affiliate marketing networks, celebrity/influencer endorsements.'",
          "explanation": "The standard, culturally accepted methods for customer acquisition in the online trading industry at the time, which fraudsters would later weaponize."
        },
        "typical_sales_pitch_themes": {
          "value": "e.g., 'Empowerment through technology, financial freedom, easy money with high success rates, free seminars and 'educational' webinars.'",
          "explanation": "The normative marketing narratives that blurred the line between legitimate salesmanship and predatory manipulation."
        }
      }
    },
    "stage_II_-_incubation_period": {
      "perpetrator_actions_setup": {
        "corporate_structure_obfuscation": {
          "value": "e.g., 'Layered ownership through nominees in Belize and Seychelles; operating platform branded as 'XTrade' was owned by 'Alpha Consolidated Ltd' (St. Vincent) which was controlled by 'Beta Holdings Group' (Cyprus).'",
          "explanation": "Deliberate complexity designed to confuse investigators, shield beneficial owners, and hinder asset recovery."
        },
        "acquisition_of_regulatory_veneer": {
          "value": "e.g., 'Purchased a pre-existing shell company with a CySEC license in 2012, but core fraudulent operations were run from a separate, unlicensed Israeli entity.'",
          "explanation": "A critical step to gain initial trust; the license was used for marketing while being systematically violated in practice."
        },
        "technology_platform_development": {
          "value": "e.g., 'Custom-built trading platform with a hidden 'manual execution' mode allowing brokers to override prices and delay executions during volatile market events.'",
          "explanation": "The technological backbone of the fraud, engineered not for fair execution but for covert manipulation and guaranteed profit for the house."
        }
      },
      "early_warning_signals_ignored": {
        "internal_whistleblower_complaints": {
          "value": "e.g., 'In 2014, a former software developer emailed the board alleging the platform's 'back-office' tools were designed to 'cheat clients.' The complaint was dismissed without external referral.'",
          "explanation": "Demonstrates that the fraudulent intent was known internally early on, and a conscious decision was made to suppress it."
        },
        "customer_complaint_patterns": {
          "value": "e.g., 'By 2015, over 40% of complaints to the in-house 'compliance' department concerned inability to withdraw funds or disputed trades. These were systematically closed with template responses blaming 'market conditions'.'",
          "explanation": "Shows a recurring, systemic problem that was internally documented but intentionally not addressed, representing a growing disconnect from stated norms of fair dealing."
        },
        "regulatory_warnings_specific": {
          "value": "e.g., 'In 2016, the Belgian FSMA issued a direct warning against the entity for offering services without authorization. The company continued operations via a slightly altered website domain.'",
          "explanation": "An external signal of deviance that was noticed by a regulator but was insufficiently forceful or coordinated to halt the operation."
        }
      },
      "cultural_drift_within_operation": {
        "sales_team_incentive_structure": {
          "value": "e.g., 'Brokers paid 15-20% commission on client deposits, but fined or fired if net client withdrawals exceeded a threshold. This mathematically incentivized churning and blocking withdrawals.'",
          "explanation": "The formal reward system that actively encouraged fraudulent behavior by employees, corrupting the sales culture from within."
        },
        "internal_lexicon_of_deception": {
          "value": "e.g., 'Victims referred to as 'muppets' or 'fish' in internal chats; the process of extracting deposits was called 'catching'; manipulated price feeds were called 'special quotes'.'",
          "explanation": "Language evolution that normalized predatory behavior, dehumanized victims, and solidified a deviant subculture within the organization."
        }
      }
    },
    "stage_III_-_precipitating_event": {
      "event_identification": {
        "trigger_type": {
          "value": "e.g., 'Mass Withdrawal Request Cascade', 'Regulatory Raid', 'Major Media Investigation Publication', 'Whistleblower Data Leak to Journalists'",
          "explanation": "Categorizes the nature of the event that broke the scheme's ability to maintain its façade."
        },
        "specific_event_description": {
          "value": "e.g., 'On March 15, 2018, the financial blog 'ForexFraudExposed' published leaked screenshots of the platform's broker manual detailing how to manually reject profitable withdrawal requests. The story was picked up by Reuters the next day.'",
          "explanation": "A precise, factual description of the precipitating event, including dates and key actors."
        },
        "immediate_catalyst": {
          "value": "e.g., 'The leaked documents provided incontrovertible, non-circumstantial evidence of intentional malfeasance, moving the narrative from 'bad luck' to 'criminal intent'.'",
          "explanation": "Explains why *this* particular event had the power to transform general perceptions, often because it provided undeniable proof."
        }
      },
      "immediate_reactions": {
        "perpetrator_response": {
          "value": "e.g., 'The company issued a statement claiming the documents were 'fabricated by a disgruntled ex-employee' and temporarily disabled the online chat function to stem internal panic.'",
          "explanation": "The first, often defensive, public or private action taken by the fraud operators to contain the crisis."
        },
        "victim_reaction_onset": {
          "value": "e.g., 'Within 72 hours, over 2,000 clients simultaneously filed withdrawal requests, crashing the online request system and flooding customer service lines.'",
          "explanation": "The collective action by victims that immediately stressed the scheme's financial and operational liquidity."
        },
        "first_regulatory_escalation": {
          "value": "e.g., 'On March 20, 2018, CySEC announced an emergency on-site inspection and suspended the entity's license, freezing all client accounts.'",
          "explanation": "The first major, public regulatory action directly triggered by the precipitating event, marking the shift from incubation to active crisis."
        }
      }
    },
    "stage_IV_-_onset": {
      "operational_collapse": {
        "platform_shutdown": {
          "value": "e.g., 'On March 25, 2018, the trading platform displayed a 'temporarily under maintenance' message. All client access to accounts and funds was permanently lost.'",
          "explanation": "The definitive moment when the service ceased, locking victims out and confirming the collapse."
        },
        "communication_blackout": {
          "value": "e.g., 'Company phone lines disconnected; official email addresses bounced; key executives' LinkedIn profiles were deleted or set to private.'",
          "explanation": "The disappearance of the perpetrators, a classic hallmark of a fraudulent scheme's end-stage."
        },
        "asset_freezing_actions": {
          "value": "e.g., 'A Cyprus court, at CySEC's request, froze €12.5 million across 5 bank accounts linked to the entity. However, forensic accountants estimated over €50 million had been transferred to offshore accounts in the preceding 6 months.'",
          "explanation": "Shows the immediate legal efforts to secure remaining assets and the typical finding that most funds had already been siphoned off."
        }
      },
      "victim_crisis": {
        "immediate_financial_impact": {
          "value": "e.g., 'Individual losses ranged from €500 to over €250,000. Numerous victims reported being unable to pay mortgages or medical bills as a direct result.'",
          "explanation": "Quantifies and humanizes the direct, acute financial damage experienced by victims."
        },
        "psychological_social_impact": {
          "value": "e.g., 'Online victim support forums saw posts describing severe anxiety, depression, shame, and familial strife. Many victims reported feeling 'stupid' and were reluctant to report to authorities due to embarrassment.'",
          "explanation": "Documents the non-financial trauma, which is a critical part of the fraud's full impact and often hinders recovery efforts."
        },
        "organized_victim_response": {
          "value": "e.g., 'By April 2018, a Facebook group 'Justice for [Scheme Name] Victims' formed, amassing 3,000 members. It coordinated template letters to regulators and shared lists of lawyer contacts.'",
          "explanation": "Illustrates the beginning of collective victim action, which is crucial for driving legal and political pressure."
        }
      },
      "media_narrative_crystallization": {
        "headline_tone_shift": {
          "value": "e.g., 'Headlines moved from 'Online Trading Firm in Trouble' to 'International Binary Options Scam Unravels, Thousands Defrauded'.'",
          "explanation": "Shows how the media's framing of the event consolidated around themes of criminality and systemic fraud."
        },
        "key_investigative_revelations": {
          "value": "e.g., 'A follow-up investigation by 'Finance Uncovered' traced wire transfers from the scheme to luxury real estate purchases in Dubai by a suspected beneficial owner.'",
          "explanation": "Post-collapse journalism that began piecing together the money trail and identifying hidden perpetrators, fueling public outrage."
        }
      }
    },
    "stage_V_-_rescue_and_salvage": {
      "immediate_regulatory_legal_response": {
        "emergency_measures": {
          "value": "e.g., 'CySEC initiated a claims administration process for frozen funds, but only for EU-based clients, excluding 70% of the victim pool. The process was criticized for complexity and low recovery expectations.'",
          "explanation": "The first, ad-hoc attempts to manage the fallout, often revealing jurisdictional limitations and inadequate victim compensation mechanisms."
        },
        "criminal_charges_initial": {
          "value": "e.g., 'In June 2018, Israeli police arrested 5 suspects (including the alleged ringleader) on suspicion of fraud, money laundering, and securities law violations following a year-long undercover operation.'",
          "explanation": "The commencement of formal criminal proceedings against key individuals, a critical step for justice but often geographically limited."
        }
      },
      "victim_salvage_efforts": {
        "chargeback_campaigns": {
          "value": "e.g., 'Victim groups circulated guides on how to file chargebacks with credit card companies for 'services not rendered,' with a reported 30% success rate for Mastercard/Visa transactions within 120-day windows.'",
          "explanation": "A grassroots, self-help mechanism that provided partial recovery for some victims, highlighting the role of payment intermediaries."
        },
        "class_action_lawsuits_filed": {
          "value": "e.g., 'In July 2018, a US-based class action was filed in the Southern District of New York against the payment processors used by the scheme, alleging they were 'enablers' who ignored red flags.'",
          "explanation": "The expansion of legal liability beyond the core perpetrators, targeting auxiliary service providers in jurisdictions with favorable consumer laws."
        }
      },
      "industry_reaction_containment": {
        "legitimate_operator_distancing": {
          "value": "e.g., 'The major trade association for CFD brokers issued a press release 'condemning the illegal actions of a few bad actors' and emphasizing their members' commitment to 'strict compliance'.'",
          "explanation": "Damage control by the broader industry to prevent contagion of reputational risk and regulatory backlash onto legitimate (or semi-legitimate) businesses."
        },
        "advertising_platform_bans": {
          "value": "e.g., 'In January 2019, Google announced a global ban on all advertising for CFDs, binary options, and forex products, citing 'unacceptable levels of harm' to consumers.'",
          "explanation": "A major, tangible consequence where key customer acquisition channels were severed for the entire product category, a direct salvage operation for the public."
        }
      }
    },
    "stage_VI_-_full_cultural_readjustment": {
      "long_term_regulatory_reforms": {
        "product_bans": {
          "value": "e.g., 'In July 2019, ESMA made its temporary ban on the marketing, distribution, and sale of binary options to retail clients permanent across the European Union.'",
          "explanation": "The most definitive regulatory response: the elimination of the product itself from a major market, a direct outcome of the accumulated harm from cases like this one."
        },
        "stricter_rules_for_related_products": {
          "value": "e.g., 'Concurrently, ESMA and the FCA imposed leverage limits (e.g., 30:1 on major forex), mandatory risk warnings, and standardized disclosure of loss rates for CFD trading.'",
          "explanation": "Spillover reforms applied to adjacent, similarly risky products, representing a broad reassessment of how speculative retail trading is governed."
        },
        "enhanced_supervisory_powers": {
          "value": "e.g., 'CySEC was given enhanced powers to gate withdrawals, conduct more frequent on-site inspections, and impose larger fines directly, partly in response to criticism of its oversight in this case.'",
          "explanation": "Changes to the regulator's toolkit, aiming to prevent future incubations by allowing earlier intervention."
        }
      },
      "legal_precedents_settlements": {
        "landmark_court_rulings": {
          "value": "e.g., "In the case 'CFTC v. [Perpetrator Entity]', the court ruled in 2021 that the fraudulent binary options scheme constituted both a 'swap' and a 'futures contract' under US law, expanding the CFTC's jurisdictional reach for future cases."",
          "explanation": "Legal decisions that reinterpreted or clarified laws based on the facts of this fraud, shaping the environment for future enforcement."
        },
        "final_asset_recovery_distribution": {
          "value": "e.g., "As of 2023, the court-appointed receiver had distributed €4.2 million to 1,200 eligible claimants, representing an average recovery of 8 cents on the euro of proven claims."",
          "explanation": "The cold, quantitative outcome of the salvage process, demonstrating the extreme difficulty and limited success of recovering stolen funds in complex international frauds."
        },
        "individual_sentencing_outcomes": {
          "value": "e.g., "In 2022, the CEO was sentenced to 7 years imprisonment and a €3 million fine. The Head of Sales received a 4-year sentence. Both convictions were for aggravated fraud and money laundering."",
          "explanation": "The final accountability for key individuals, providing a measure of judicial closure and deterrence signaling."
        }
      },
      "lasting_cultural_legacy": {
        "public_awareness_shift": {
          "value": "e.g., "The term 'binary options' became strongly associated with 'scam' in public discourse. Mainstream financial advice columns routinely warn readers about such offers as unequivocal frauds."",
          "explanation": "The transformation of public perception from ambiguity to clear negative association, a key indicator of cultural readjustment."
        },
        "academic_case_study_inclusion": {
          "value": "e.g., "The case is now cited in finance and law school curricula as a prime example of offshore boiler-room fraud, technological manipulation, and regulatory arbitrage."",
          "explanation": "Integration into formal educational structures, ensuring the lessons are studied by future professionals."
        },
        "persistent_challenges": {
          "value": "e.g., "Despite bans, clone websites and 're-branded' schemes using CFDs or 'digital options' continue to emerge, often targeting new jurisdictions in Asia and Africa, demonstrating the adaptive nature of financial fraud."",
          "explanation": "Acknowledges that cultural readjustment is not a perfect end-state; it identifies the enduring vulnerabilities and the evolution of the threat."
        }
      }
    },
    "concluding_analysis": {
      "primary_failure_modes": [
        {
          "failure": "e.g., 'Regulatory Fragmentation and Arbitrage'",
          "explanation": "The scheme exploited the mismatch between the global reach of the internet and the national/regional scope of financial regulators, deliberately basing operations in jurisdictions with weak enforcement."
        },
        {
          "failure": "e.g., 'Weaponization of Trust Signifiers'",
          "explanation": "The fraud effectively co-opted symbols of legitimacy (licenses, professional-looking websites, complex financial jargon) to disarm the skepticism of victims, demonstrating a failure of those signifiers to guarantee probity."
        }
      ],
      "systemic_vulnerabilities_highlighted": {
        "value": "e.g., 'The opacity of online payment processing for speculative trading; the insufficiency of 'disclaimer' risk warnings against sophisticated psychological manipulation; the lack of coordinated international asset seizure protocols.'",
        "explanation": "Broader weaknesses in the global financial and legal infrastructure that this case exposed and which remain partially unaddressed."
      },
      "cinematic_metaphor_summary": {
        "value": "e.g., "This fraud can be viewed as a heist film where the vault was not a bank but the global retail investor's trust in online finance. The perpetrators were not masked robbers but suited professionals using technology as their lockpick, and regulation acted as the delayed-response security guard, arriving after the getaway."",
        "explanation": "A synthesizing analogy that encapsulates the narrative essence of the case for the 'film documentary' framing."
      }
    }
  }
}
"""