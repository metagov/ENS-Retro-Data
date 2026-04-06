**ENS Retro Data Dashboard: Guidance Manual**

**Purpose of This Document**

This manual accompanies the ENS Retro Data Dashboard (ens-retro-data.fly.dev) and serves two parallel functions: (1) a practical navigation guide helping users move through the dashboard's features and data views, and (2) an intellectual context document explaining the research constructs, hypotheses, and analytical logic that motivate what the dashboard displays. Both functions are anchored in the broader ENS DAO Stakeholder Analysis & Retrospective — a DAO-approved, mixed-methods evaluation commissioned to diagnose governance and operational challenges and generate evidence-based reform recommendations.

---

**Part I: Introduction and Context**

**Section 1: About the ENS Retrospective**

**1.1 What Is the ENS Retro?**

The Ethereum Name Service (ENS) DAO authorized an independent retrospective of governance, spending, and organizational structure during the Extended Term 6 cycle (December 2025–April 2026). The retro is conducted by the MetaGov Project as a DAO-approved, rigorous mixed-methods evaluation. Its core purpose is to review where the DAO has been, outline goals for the future, and provide clear accountability standards going forward. The retro concludes with a full research report, governance roadmap, and community-facing materials.

**1.2 Why a Dashboard?**

The dashboard translates quantitative data — primarily treasury, spending, and governance participation data — into visual formats accessible to all ENS stakeholders. The dashboard is designed to be a living instrument: findings displayed here will be integrated with qualitative interview data, comparative DAO research, and stakeholder input in later research phases.

**1.3 How to Use This Dashboard: Data, Limitations, and the Imperative of Triangulation**

The dashboard is one input into a larger body of evidence — not a standalone source of conclusions. This is not a caveat to minimize the dashboard's value; it is a fundamental principle of empirically sound decision-making that applies to every data source in this evaluation, including this one.

All data sources carry inherent limitations. Quantitative dashboards, by their nature, measure what can be counted — and many of the most important dimensions of governance quality are difficult or impossible to fully capture in numerical form. Decisions grounded solely in any single dataset risk being distorted by what that dataset cannot see.

A concrete example: the dashboard uses a proxy measure for governance proposal complexity — primarily word count and link count — because these are objectively quantifiable from proposal text. However, "complexity" as a governance concept encompasses far more: the clarity of the argument, the technical expertise required to evaluate the proposal, the degree of prior knowledge needed to understand its implications, the number of stakeholders affected, and the degree of controversy surrounding the decision. No word count captures these dimensions. A short proposal might require deep technical expertise to evaluate; a long proposal might be structured and accessible to a broad audience. Users who draw conclusions about participation barriers from the complexity proxy alone — without triangulating with stakeholder interview data, community forum discussions, and delegate feedback — risk misdiagnosing both the problem and the appropriate intervention.

This same logic applies across the dashboard:

* **Voting power data** shows that delegation is concentrated, but cannot explain why — whether holders are rationally free-riding, uninformed about alternatives, or actively satisfied with their delegates requires qualitative corroboration

* **Treasury spending data** shows aggregate disbursements, but gaps in documentation may reflect data infrastructure challenges rather than actual gaps in activity, and lack of clarity of objectives of spending make anything approaching a ROI impossible

* **Participation rate trends** show changes in on-chain behavior, but cannot capture the off-chain discussions, informal coordination, and community culture shifts that shape formal governance activity

* **Grant outcome tracking** shows whether reports were filed, but not whether the underlying work delivered genuine value to the ENS ecosystem

The research design of the ENS Retro addresses these limitations explicitly through a mixed-methods approach: interview data, comparative DAO research, and structured community engagement are all designed to complement and triangulate with the quantitative data the dashboard surfaces. Users — whether delegates, token holders, stewards, or researchers — are encouraged to treat its visualizations as productive questions for further investigation rather than settled answers.

**Three principles for using this dashboard responsibly:**

1. **Use dashboard findings as hypotheses, not conclusions.** When a visualization suggests a pattern — high concentration, low participation, sparse outcome documentation — treat that as a prompt to dig deeper with other sources, not as an established fact about ENS DAO governance.

2. **Name the measurement gap.** For every metric displayed, ask: What important dimensions of this concept does this measure NOT capture? Surfacing what is missing from a metric is as important as reading what the metric shows.

3. **Contextualize before acting.** Dashboard data will be most actionable when read alongside the qualitative stakeholder analysis, comparative DAO findings, and community feedback that the full retrospective will produce. Premature interpretation — before the full evidence base is assembled — risks solutions that address symptoms rather than root causes.

**1.4 Sustained and Future Use of the Dashboard**

The dashboard was built to support the ENS Retro, but its data infrastructure and analytical architecture create options for sustained use beyond the evaluation's conclusion. Three scenarios are worth considering:

**Option A — Retire at Retro Conclusion**  
The dashboard is used exclusively for the retrospective, then archived as a point-in-time record.

* *Benefit:* No ongoing maintenance cost; clean scope boundary.

* *Cost:* The quantitative baseline built for the retro has no successor, and future governance or operational questions would need to rebuild data infrastructure from scratch.

**Option B — Maintain as a Performance and Risk Monitoring Tool**  
The dashboard is updated on a recurring cadence (quarterly or per term) and linked to DAO objectives, Working Group and Labs sub-objectives, and correlated KPIs. A Delegate Performance Module could be added.

* *Benefit:* Provides decision-quality data across levels of ENS ecosystem operations — including Labs, current or potential service providers, and enterprises seeking to build on ENS. The triangulation principles established for the retro would apply to all future uses, keeping interpretation grounded and accountable.

* *Cost:* Requires a defined owner, maintenance resources, and governance buy-in for ongoing data curation. Data quality and coverage limitations identified in the retro would need active management.

**Option C — Expand with an AI Analytical Layer**  
Building on Option B, an AI analytical tool could enable any user to perform on-the-spot calculations, test new hypotheses with existing dashboard data, or explore scenarios relevant to their specific needs — beyond the fixed views the current dashboard provides.

* *Benefit:* The current dashboard is built around identified challenges and the hypotheses explaining those challenges. ENS will have future decision-making needs that require testing new hypotheses with existing data, or with new data through a redesigned dashboard. An AI layer makes the data infrastructure extensible for those unknown future needs.

* *Cost:* Higher technical complexity, greater resources for development and maintenance, and the need for guardrails to ensure analytical outputs are interpreted responsibly given the measurement limitations already identified.

Regardless of which option ENS pursues, the triangulation principles in Section 1.3 apply equally to any future use of this data.

**1.5 Who Should Use This Manual?**

* Delegates and tokenholders seeking to understand governance and spending trends

* Stewards and working group contributors reviewing program and budget data relevant to their mandates

* Community members and researchers wanting to engage with the analytical logic behind the evaluation

* ENS Labs and MetaGov stakeholders using the dashboard to validate interim findings during milestone check-ins

**1.6 How This Manual Is Organized**

* **Part I:** Context and background (this section)

* **Part II:** Dashboard navigation guide (section-by-section walkthrough)

* **Part III:** Research constructs and hypotheses (the intellectual framework)

* **Part IV:** Module map by governance challenge

* **Part V:** Hypothesis cluster details

* **Part VI:** Analysis plan and methodology

* **Part VII:** Interpreting findings

---

**Part II: Dashboard Navigation Guide**

**Section 2: Getting Started**

**2.1 Dashboard Overview**

The homepage/landing view provides a high-level summary of the dashboard's primary data domains. Navigation is organized by module — tabs, sidebar links, or dropdown selectors allow users to move between views — and within each module, filters allow for disaggregation by time period, working group, or stakeholder category.

**2.2 Data Freshness and Caveats**

Each visualization includes a last-updated timestamp and notes on update cadence. Known data gaps — such as off-chain spending not captured in on-chain records — are flagged inline within relevant views. "N/A" or missing values may indicate either genuine absence of activity or a gap in documentation; the distinction matters and is noted where determinable. Users who identify data quality issues or discrepancies are encouraged to flag them via the ENS Governance Forum.

---

**Section 3: Dashboard Module Walkthroughs**

The following subsections are organized around the primary hypothesis clusters in the analysis plan and the data domains most relevant to the retrospective. Each module description includes the data sources feeding it, the key views available, and the specific research hypotheses it informs.

**3.1 Treasury and Spending Module**

**What it shows:** Aggregate and disaggregated ENS DAO treasury disbursements over time, broken down by working group, initiative type, and funding category.

**Key views:**

* Total spend by working group (Meta-Gov, Ecosystem, Public Goods) by term or quarter

* Grant expenditures vs. operational expenditures vs. service provider payments

* Budget vs. actuals comparisons where data are available

* Spending trend lines across governance terms

**Relevant data sources:** enswallets.xyz, SafeNotes, ENS Forum WG spending reports, Karpatkey reports, ENS Ledger Analysis

**Research connection:** Directly supports Hypothesis Cluster 7 (Treasury fragmentation, resourcing, and tracking). The dashboard's spending reconstruction views provide quantitative evidence for whether the DAO's financial data is sufficiently integrated and traceable — and for what proportion of grants have accessible outcome documentation.

**3.2 Delegation and Voting Power Module**

**What it shows:** Distribution of $ENS delegation and voting power across delegates and token-holder tiers.

**Key views:**

* Voting power concentration: share held by top 1%, 10%, and top 10 delegates over time

* Delegation network: who delegates to whom, and how that has changed across governance terms

* Re-delegation churn: percentage of delegators who changed their delegate over a given period

* New delegate growth: cohort analysis of delegate join dates and delegation power accumulation

**Relevant data sources:** Agora, Boardroom, Tally, Dune dashboards, Etherscan, Snapshot

**Research connection:** Supports Hypothesis Clusters 1 (delegation behavior), 2 (structural power concentration), 3 (delegation infrastructure), and 6 (delegate ecosystem health).

**3.3 Governance Participation Module**

**What it shows:** On-chain and off-chain voting participation rates, proposal activity, and engagement trends.

**Key views:**

* Voter turnout by proposal type (social vs. executable) and by complexity proxy (word count, link count)

* Participation breakdown by stakeholder tier (delegate, small holder, steward)

* Proposal throughput: volume, average time from submission to execution, and outcome rates

* Participation trends over time across governance cycles and terms

**Relevant data sources:** Snapshot (off-chain), Tally (on-chain), Agora, ENS Forum, ENS Newsletter

**Research connection:** Supports Hypothesis Clusters 4 (participation barriers) and 5 (governance legitimacy).

**3.4 Grants and Initiative Outcomes Module**

**What it shows:** Grant funding flows and available outcome documentation tied to funded initiatives.

**Key views:**

* Grant recipients by working group and funding round

* Availability and completeness of outcome reports linked to original grant objectives

* Distribution of grant sizes and categories (ecosystem development, public goods, tooling)

* Timeline from grant approval to documented reporting

**Relevant data sources:** ENS Grants program records, ENS Forum WG reports, SafeNotes

**Research connection:** Primarily supports Hypothesis H7.3 (grant accountability and outcome tracking) — specifically the question of what percentage of funded initiatives have clear, accessible outcome reports tied to their original stated objectives.

**3.5 Compensation and Contributor Module (where data are available)**

**What it shows:** Contributor compensation patterns across working groups.

**Key views:**

* Compensation by role type and working group

* Consistency of compensation frameworks across terms

* Documented compensation changes tied to steward transitions, where traceable

**Relevant data sources:** ENS Forum WG budgets, ENS Docs, contributor interviews (anonymized)

**Research connection:** Supports Hypothesis Cluster 8 (compensation frameworks and contributor dynamics). Compensation data availability is limited — many arrangements are informally documented, which is itself a finding relevant to H8.1 and H8.3.

---

**Part III: Research Constructs and Hypotheses**

**Section 4: The Theoretical Framework**

**4.1 The Central Research Problem**

The ENS DAO faces reported challenges — including voting power concentration, low broad-based participation, communication fragmentation, de facto centralization of real decision-making, and treasury and institutional liability risk — that have been observed through forum data, individual conversations, and governance records. These challenges motivate the dashboard's focus on measurable patterns in delegation, participation, spending, and governance structure.

**4.2 Primary Research Questions**

The dashboard is built to support investigation of two primary research questions:

* **RQ1:** What are the root causes of communication and operational inefficiency within ENS DAO governance, and how are these causes perceived and prioritized differently across stakeholder groups (stewards, delegates, token holders, service providers)?

* **RQ2:** What changes — informed by comparative DAO research, organizational theory, and stakeholder input — are most likely to improve ENS DAO coordination and execution effectiveness while maintaining commitment to decentralization and broad stakeholder inclusion?

The dashboard provides the quantitative evidence base for diagnosing the patterns addressed by RQ1 and informs the problem analysis that RQ2's recommendations must address.

---

**Part IV: Module Map by Governance Challenge**

**Section 4M: Dashboard Modules Organized by Governance Challenge**

This section maps every dashboard module and sub-module to the governance challenge it addresses. Use it as a navigation index: start with the challenge most relevant to your question, then locate the specific dashboard views that surface evidence for it.

**Challenge 1 — Delegation Behavior (H1)**

*Why do token holders delegate rather than vote directly, or re-delegate?*

| Module | Sub-Module / View | What It Measures |
| :---- | :---- | :---- |
| Delegation & Voting Power | Top-delegate power share over time | Whether concentration of early delegates persists (H1.3) |
| Delegation & Voting Power | New delegation flows by cohort | Whether new delegators spread power broadly or concentrate it among existing top delegates (H1.1) |
| Delegation & Voting Power | Re-delegation churn rate | Frequency with which delegators switch delegates; low churn suggests rational free-riding or habit (H1.2, H1.3) |
| Delegation & Voting Power | Delegation network map | Visual pattern of who delegates to whom across terms |

**Challenge 2 — Structural Power Concentration (H2)**

*How does one-token-one-vote produce and reinforce power concentration?*

| Module | Sub-Module / View | What It Measures |
| :---- | :---- | :---- |
| Delegation & Voting Power | Top 1% and top 10% voting power share | Degree to which a small number of addresses control majority voting power (H2.1) |
| Delegation & Voting Power | Vote outcomes by holder size | Whether large token holders vote against power-reducing proposals at higher rates (H2.2) |
| Delegation & Voting Power | Small-holder participation share | Proportion of voting power exercised by holders with small or medium balances relative to their token supply share (H2.3) |
| Governance Participation | Participation breakdown by stakeholder tier | Disaggregated turnout showing how delegate, small-holder, and steward tiers participate differently |

**Challenge 3 — Delegation Infrastructure (H3)**

*How do governance tools and information environments entrench large delegates?*

| Module | Sub-Module / View | What It Measures |
| :---- | :---- | :---- |
| Delegation & Voting Power | Delegation network map | Whether delegation flows cluster toward a small set of top delegates (H3.1) |
| Delegation & Voting Power | Re-delegation churn rate | Whether most delegators never change their delegate, suggesting inertia rather than active performance assessment (H3.3) |
| Delegation & Voting Power | Delegate profile richness vs. power | Correlation between documented delegate activity/profile quality and delegated power (H3.2) |
| Delegation & Voting Power | New delegate growth trajectories | Whether new delegates can accumulate meaningful power after joining (H3.1, H6.1) |

**Challenge 4 — Participation Barriers (H4)**

*What structural and cultural factors discourage broad governance participation?*

| Module | Sub-Module / View | What It Measures |
| :---- | :---- | :---- |
| Governance Participation | Voter turnout by proposal complexity proxy | Whether higher word count or link count proposals show lower turnout — a proxy test for cognitive cost barriers (H4.1) |
| Governance Participation | Participation trends over time | Whether participation rates are declining, stable, or rising across terms (H4.3) |
| Governance Participation | Proposal throughput and time-to-execution | Whether slow or opaque governance processes correlate with lower engagement (H4.2) |
| Governance Participation | Participation breakdown by stakeholder tier | Whether the governance class is narrowing over time |

**Challenge 5 — Governance Legitimacy (H5)**

*Is there a gap between ENS's decentralization narrative and structural reality?*

| Module | Sub-Module / View | What It Measures |
| :---- | :---- | :---- |
| Delegation & Voting Power | Top 1% voting power share | Whether concentration data contradicts public decentralization claims (H5.1) |
| Governance Participation | Proposal pathway complexity data | Number of governance bodies, documents, and steps involved in moving from idea to execution (H5.3) |
| Governance Participation | Proposal throughput and outcome rates | Whether governance processes produce decisions efficiently or are characterized by stalling and attrition |

**Challenge 6 — Delegate Ecosystem Health (H6)**

*Is the delegate ecosystem dynamic, or locked into early patterns?*

| Module | Sub-Module / View | What It Measures |
| :---- | :---- | :---- |
| Delegation & Voting Power | Cohort analysis of delegate join dates and power trajectories | Whether delegates who joined later were able to grow their delegated power meaningfully (H6.1) |
| Delegation & Voting Power | Delegate activity vs. power | Whether top delegates maintain large delegations despite declining on-chain vote participation (H6.2) |
| Delegation & Voting Power | Re-delegation churn rate | Whether the broader community reassesses delegates over time or stays locked in (H6.2, H6.3) |
| Governance Participation | Structural change tracking | Evidence of experimentation with term limits, rotation mechanisms, or onboarding programs (H6.3) |

**Challenge 7 — Treasury and Financial Management (H7)**

*How fragmented is ENS's financial data, and how accountable are funded initiatives?*

| Module | Sub-Module / View | What It Measures |
| :---- | :---- | :---- |
| Treasury & Spending | Total spend by working group by term | Aggregate disbursements across Meta-Gov, Ecosystem, and Public Goods WGs |
| Treasury & Spending | Grant vs. operational vs. service provider expenditures | Breakdown of spending categories to surface accountability questions (H7.3) |
| Treasury & Spending | Budget vs. actuals comparisons | Under- or over-execution relative to approved budgets (H7.2) |
| Treasury & Spending | Spending reconstruction gaps | Cases where spending required manual reconstruction from multiple sources, evidencing fragmentation (H7.1) |
| Grants & Initiative Outcomes | Outcome report availability by grant | Percentage of grants with accessible, linked outcome documentation (H7.3) |
| Grants & Initiative Outcomes | Time from grant approval to documented reporting | Accountability lag between funding and outcome visibility |

**Challenge 8 — Compensation and Contributor Dynamics (H8)**

*Are contributor compensation frameworks transparent, systematic, and consistent?*

| Module | Sub-Module / View | What It Measures |
| :---- | :---- | :---- |
| Compensation & Contributor | Compensation by role type and working group | Whether pay rates cluster consistently by role or vary widely without documented rationale (H8.1) |
| Compensation & Contributor | Framework consistency across terms | Whether compensation approaches changed with steward turnover (H8.3) |
| Treasury & Spending | Working group budget breakdowns | Where compensation data surfaces within overall WG spending records (H8.1, H8.3) |

---

**Cross-Challenge Module Coverage Matrix**

The following table shows which modules are relevant to which governance challenges at a glance. A filled cell indicates the module provides direct evidence for that challenge.

| Module | C1 | C2 | C3 | C4 | C5 | C6 | C7 | C8 |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| Treasury & Spending |  |  |  |  |  |  | ✓ | ✓ |
| Delegation & Voting Power | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |  |
| Governance Participation |  | ✓ |  | ✓ | ✓ | ✓ |  |  |
| Grants & Initiative Outcomes |  |  |  |  |  |  | ✓ |  |
| Compensation & Contributor |  |  |  |  |  |  |  | ✓ |

---

**Part V: Hypothesis Cluster Details**

The eight clusters below map directly to the module views described in Part IV. The table in Section 4.3 provides the high-level summary; this section provides the sub-hypothesis detail and dashboard relevance for each cluster.

**Section 5: Hypothesis Cluster Descriptions**

The analysis plan organizes testable hypotheses into eight thematic clusters. Each cluster targets a distinct dimension of ENS DAO governance:

| Cluster | Theme | Core Concern |
| :---- | :---- | :---- |
| H1 | Delegation Behavior | Why token holders delegate rather than vote directly, or re-delegate at any time |
| H2 | Structural Power Concentration | How token-weighted voting concentrates power |
| H3 | Delegation Infrastructure | How UX and information asymmetry entrench hubs |
| H4 | Participation Barriers | Why broad participation remains low |
| H5 | Governance Legitimacy | The gap between decentralization narrative and reality |
| H6 | Delegate Ecosystem Health | Barriers to new delegates and structural experimentation |
| H7 | Treasury and Financial Management | Fragmentation and accountability in spending |
| H8 | Compensation and Contributor Dynamics | Fairness and formalization of contributor pay |

**5.1 Cluster H1 — Delegation Behavior**

**Construct:** Why do token holders choose to delegate rather than vote directly, or re-delegate at any time? This cluster examines behavioral drivers including visibility bias, rational free-riding, and legacy distribution effects.

* **H1.1 Visibility Bias:** Holders mostly pick from a short, visible delegate list rather than conducting broad comparison

* **H1.2 Rational Free-Riding:** People delegate to avoid the time and effort costs of active participation

* **H1.3 Legacy Distribution:** Early concentration patterns persist and continue to dominate the current delegate landscape

**Dashboard relevance:** Delegation module views on top-delegate power share, new delegation flows, and re-delegation churn provide quantitative context for each of these hypotheses.

**5.2 Cluster H2 — Structural Power Concentration**

**Construct:** How does the one-token-one-vote mechanism produce and reinforce power concentration, and how do large actors respond to decentralizing reforms?

* **H2.1 Token-Weighted Democracy Paradox:** 1 token \= 1 vote structurally leads to concentration; top 1% of voting addresses may hold the majority of active voting power

* **H2.2 Coordination on Status Quo:** Large actors resist decentralizing reforms, voting against power-reducing proposals

* **H2.3 Weak Small-Holder Voice:** Small holders own a substantial share of supply but contribute a disproportionately small fraction of voting power in key decisions

**Dashboard relevance:** Voting power distribution views, inequality measures (top 1%, 10% shares), and vote outcome analysis by holder size.

**5.3 Cluster H3 — Delegation Infrastructure**

**Construct:** How do governance tools and information environments channel delegations toward a small number of large delegates?

* **H3.1 Delegation UX Drives Hubs:** Delegation interfaces (Agora, Boardroom, Slobo) may default to sorting by existing power, pushing new delegators toward top delegates

* **H3.2 Information Asymmetry:** Top delegates may have richer, more detailed profiles; holders may lack information about smaller delegates

* **H3.3 Low Re-Delegation Churn:** Most delegators may never change their delegate, and top delegates may maintain position largely through inertia rather than ongoing performance

**Dashboard relevance:** Delegation network views, churn rates, and profile richness indicators where available.

**5.4 Cluster H4 — Participation Barriers**

**Construct:** What structural and cultural factors discourage broad participation in ENS DAO governance?

* **H4.1 High Cognitive/Time Costs:** Governance complexity discourages participation; high-complexity proposals may show lower turnout

* **H4.2 Weak Feedback Loops:** Token holders may not see visible connections between their votes and observable changes to the ENS protocol

* **H4.3 Spectatorship Norms:** A cultural norm may exist in which most participants accept that a "governance class" handles governance on their behalf

**Dashboard relevance:** Turnout by proposal complexity proxy, implementation timeline tracking, and participation trend data.

**5.5 Cluster H5 — Governance Legitimacy**

**Construct:** Is there a meaningful gap between ENS DAO's public narrative of decentralization and the structural reality of concentrated governance power?

* **H5.1 Narrative-Structure Mismatch:** Public materials may describe ENS as broadly decentralized while concentration metrics show a far narrower distribution of actual power

* **H5.2 Emergency Centralization Creep:** Security and veto powers held by few actors may persist without clear sunset mechanisms or decentralization paths

* **H5.3 Governance Complexity Barrier:** The end-to-end governance process may involve multiple bodies and documents that many participants find inaccessible

**Dashboard relevance:** Concentration metrics displayed alongside governance documentation links; proposal pathway complexity data.

**5.6 Cluster H6 — Delegate Ecosystem Health**

**Construct:** Is the delegate ecosystem dynamic and competitive, or locked into early patterns with few pathways for new entrants?

* **H6.1 On-Ramp Barriers:** New delegates may lack visibility mechanisms and formal onboarding programs to grow their delegation

* **H6.2 Reputation Lock-In:** Early delegates may maintain large delegations despite declining activity, as most holders do not reassess

* **H6.3 Lack of Experimentation:** Very few structural changes to delegate systems may have been implemented and tested

**Dashboard relevance:** Cohort analysis of delegate join dates and power trajectories; delegate activity vs. power comparisons.

**5.7 Cluster H7 — Treasury and Financial Management**

**Construct:** How fragmented is ENS DAO's financial data infrastructure, and how accountable are funded initiatives to their stated objectives?

* **H7.1 Treasury Fragmentation:** Reconstructing a full year of spending may require multiple separate tools and manual cross-checking, with remaining gaps

* **H7.2 Resourcing:** There may be no clearly staffed, well-supported treasury operations function, and relevant finance roles may be overstretched

* **H7.3 Outcome Tracking:** Fewer than half of sampled grants may have clear, accessible outcome reports linked to their original objectives

**Dashboard relevance:** Spending reconstruction views, grant accountability indicators, and working group budget vs. actuals.

**5.8 Cluster H8 — Compensation and Contributor Dynamics**

**Construct:** Are contributor compensation frameworks transparent, systematic, and consistent across working groups and steward transitions?

* **H8.1 No Systematic Pay Framework:** No public, role-based compensation framework may explain pay bands or criteria by contributor type

* **H8.2 Insider Advantage:** Qualitative evidence may suggest that relationship visibility matters more than standard criteria in compensation decisions

* **H8.3 Informal Arrangements:** Many contributors may report informal or loosely documented compensation arrangements, sometimes changing with steward turnover

**Dashboard relevance:** Compensation data views where available, working group budget breakdowns.

---

**Part VI: Analysis Plan and Methodology**

**Section 6: How the Data Is Being Used**

**6.1 Evidentiary Thresholds: Starting Points, Not Verdicts**

The analysis plan establishes a defined threshold for each hypothesis — a quantitative or qualitative benchmark that guides the research team's assessment of whether a hypothesis is supported. These thresholds are grounded in existing governance research and provide a consistent, transparent standard for evaluating the evidence as it is assembled.

These thresholds represent analytically defensible starting points, not fixed benchmarks with universal validity. Whether a given finding constitutes a "problem" for ENS DAO specifically depends on context: the DAO's stated priorities, its governance philosophy, the tradeoffs it is willing to accept between decentralization and operational efficiency, and how it compares to peer organizations navigating similar structures. If evidence falls short of a threshold, that does not necessarily mean the problem does not exist — governance dysfunction can manifest subtly, at levels below quantitative thresholds, particularly when qualitative interview data reveals that stakeholders perceive a problem even when measured indicators do not yet reach the established benchmark.

Three principles govern how the research team uses these thresholds:

1. **Thresholds signal where the evidence points, not what ENS must do.** A supported hypothesis means the evidence is consistent with the governance concern described — it does not automatically prescribe a particular reform.

2. **The full evidence base matters more than any single threshold.** A hypothesis that narrowly falls below its quantitative threshold but is corroborated strongly by qualitative evidence will be treated differently than one that exceeds the threshold but is contested by stakeholder perspectives.

3. **ENS can and should calibrate these thresholds to its own context.** The thresholds in the analysis plan are a contribution to ENS DAO's governance assessment — not a final word. Deliberation about these calibrations is a healthy and expected part of the evaluation process.

**6.2 Known Limitations by Data Domain**

The table below identifies what each data domain captures, what it misses, and why those gaps matter analytically for the specific hypotheses they affect.

| Data Domain | What Dashboard Captures | What It Misses | Why the Gap Matters | Triangulation Source |
| :---- | :---- | :---- | :---- | :---- |
| Proposal complexity | Word count, link count | Clarity, technical depth, controversy, political salience | A complex proposal may have low word count but require deep expertise to evaluate; a simple proposal may be long. Relying solely on the proxy may misattribute low turnout to complexity when the actual barrier is something else entirely (H4.1) | Stakeholder interviews, forum analysis |
| Delegation patterns | On-chain delegation events | Motivation behind delegation choices; satisfaction with delegates | The same churn rate can reflect either satisfied delegators or disengaged ones who simply never revisited their delegation. Without motivation data, the dashboard cannot distinguish between healthy stability and problematic lock-in (H1.2, H3.3, H6.2) | Interviews, delegate surveys |
| Participation rates | On-chain and Snapshot vote data | Off-forum coordination, informal influence, soft governance | Participation rates may decline even as governance quality improves, if meaningful deliberation migrates to other channels. A falling turnout chart does not distinguish between disengagement and consolidation (H4.3, H5.1) | Community discussions, forum analysis |
| Spending | On-chain disbursements | Off-chain arrangements, in-kind contributions, operational context | On-chain records may substantially undercount actual resource flows. Apparent budget gaps may reflect documentation failures rather than genuine inactivity, making accountability judgments unreliable without corroboration (H7.1, H7.2) | Working group reports, steward interviews |
| Grant outcomes | Availability of outcome reports | Quality and impact of outcomes; counterfactual value | A filed report does not mean the funded work delivered genuine value, nor does a missing report mean it did not. The dashboard measures documentation discipline, not impact — a critical distinction for H7.3 | Grantee interviews, program evaluations |
| Compensation | WG budget documents | Actual pay rates, undocumented arrangements, equity perceptions | Budget line items may not reflect actual payments made, and informal arrangements by definition do not appear in formal records. The most significant compensation equity questions may be invisible to the dashboard entirely (H8.1, H8.3) | Contributor interviews |

---

**Part VII: Interpreting Dashboard Findings**

**Section 7: Reading Visualizations in Context**

**7.1 How to Read Concentration Charts**

Concentration charts — including Gini coefficients, top-decile share displays, and voting power distribution plots — communicate the degree to which a resource (tokens, delegation, voting power) is held by a small number of actors. Higher values indicate greater concentration. When reading these charts:

* **Compare across time, not just at a point in time.** A high concentration level that is decreasing tells a different story than one that is stable or increasing. The Delegation & Voting Power module shows top 1% and top 10% delegate power share by term — compare these trend lines before drawing conclusions.

* **Distinguish token concentration from voting power concentration.** Token holding reflects ownership; voting power reflects the effective distribution of governance influence, shaped by delegation behavior. The module's disaggregated views make this distinction visible.

* **Contextualize against peer DAOs.** Phase 2 comparative research will supply benchmarks from comparable governance systems; interpretations made before that comparative data is available should be held provisionally.

**7.2 How to Read Spending and Budget Charts**

* **Distinguish budgeted amounts from disbursed amounts from documented outcomes.** These are three distinct data points — a large budget with low disbursement suggests under-execution; a large disbursement with low outcome documentation suggests accountability gaps. The Treasury & Spending module's budget vs. actuals view makes this distinction visible for each working group by term.

* **Direct cross-term comparisons require caution.** Working group mandates and scopes change across terms, meaning apparent changes in spending may reflect scope changes rather than efficiency changes.

* **"Reconstructed" or "estimated" spending figures signal a data quality finding in their own right.** Where the dashboard must reconstruct spending because no clean, consolidated record exists, this is itself evidence relevant to H7.1 — treasury fragmentation is evidenced by the reconstruction effort required to produce the chart.

**7.3 How to Read Participation Trend Lines**

* **Declining turnout is common across maturing DAOs and does not automatically indicate dysfunction.** The Governance Participation module's trend lines should be read alongside the stakeholder tier breakdown — if delegate participation is stable while token-holder participation is declining, that tells a different story than uniform decline across all tiers.

* **The complexity-participation correlation** — whether higher-complexity proposals (higher word count and link count) show lower turnout — is a central test for H4.1, visible in the voter turnout by complexity proxy view. But interpret this correlation with the measurement limitation in mind: the proxy captures length and reference density, not genuine cognitive difficulty.

* **Aggregate participation rates can mask important disaggregated patterns.** Charts that combine delegate and token-holder participation without disaggregating can be misleading about where engagement gaps actually sit.

**7.4 Avoiding Misinterpretation**

**Correlation is not causation.** A concentrated delegation landscape does not by itself confirm that the concentration causes governance dysfunction — this requires triangulation with interview data and comparative cases showing how comparable concentrations have affected governance outcomes elsewhere.

**Absence of data is not absence of activity.** Low data availability for grant outcomes (H7.3) may reflect documentation gaps rather than a lack of genuine impact. The research team will seek to distinguish between these explanations through grantee interviews and working group discussions.

**Thresholds crossed are not thresholds violated.** When the data supports a hypothesis — when a threshold is reached — that is a finding that calls for deeper analysis and deliberation, not an automatic trigger for a specific reform. The implications of any finding for ENS's governance design will depend on how the community weighs it alongside other evidence, priorities, and constraints.