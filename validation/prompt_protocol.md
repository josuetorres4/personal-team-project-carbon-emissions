# Prompting Protocol

This document describes how we used multiple AI tools to design, prototype, and debug the **sust-AI-naible** system. The goal of these prompting experiments was to evaluate how current LLM tools can support the design and development of a **carbon-aware cloud optimization platform**.

The experiments covered:

- system design generation  
- sustainability reasoning  
- debugging multi-agent workflows  
- research synthesis  

---

# Tools Used

The following AI tools were used during development and experimentation:

- **ChatGPT** – reasoning about sustainability trade-offs and explaining carbon-aware scheduling decisions  
- **Cursor** – generating system architecture, scaffolding the prototype, and creating synthetic simulation data  
- **GitHub Copilot** – debugging orchestration logic and assisting with code generation  
- **NotebookLM** – synthesizing research papers and documentation related to carbon accounting and sustainability systems  

These tools were evaluated using **typical, edge, and failure case scenarios**.

---

# Cursor — Core System Prompt

Cursor was used to generate the **initial architecture and prototype structure** of the system.

During development, the following prompt was used inside Cursor to define the core architecture of the project:

> Build **sust-AI-naible**: a **closed-loop, multi-agent system** for **cloud workload carbon optimization** that senses cloud/workload activity, models per-job emissions deterministically (kgCO₂e with uncertainty), decides recommendations that balance carbon, cost, and latency, acts by executing approved changes, verifies claimed savings using counterfactual MRV (evidence chains + confidence intervals), and learns or communicates results through summaries, dashboards, and governance checks.  
>
> The key requirement is that the system must **close the loop** by not only measuring emissions but also taking actions and proving that emissions reductions actually occurred. Emissions calculations must remain deterministic and reproducible, while LLMs are used for reasoning, orchestration, and communication.

Using this prompt, Cursor helped generate:

- the **system architecture**
- service boundaries between agents
- data contracts for system components
- the initial **prototype repository layout**

This prompt served as the **foundation for the system architecture**.

---

# Typical Case — Carbon-Aware Workload Scheduling

We tested whether LLM tools could reason about **carbon-aware scheduling decisions**.

For example, we asked ChatGPT to evaluate a simple scheduling scenario:

> An organization runs AI workloads across three cloud regions.  
>
> Region A carbon intensity: 450 gCO2/kWh  
> Region B carbon intensity: 180 gCO2/kWh  
> Region C carbon intensity: 320 gCO2/kWh  
>
> A training job consumes approximately 200 kWh of electricity.  
>
> Which region should the organization choose to minimize carbon emissions while maintaining similar performance? Explain the reasoning behind your choice.

### Observations

- Most tools correctly selected the region with the **lowest carbon intensity**.  
- ChatGPT produced the **clearest explanations of the sustainability trade-offs**.  
- However, emission factor sources were **rarely cited**, which reduces auditability.

---

# Edge Case — Cost vs Carbon Tradeoff

We also tested how models reason about **trade-offs between cost and carbon intensity**.

The following scenario was provided to the models:

> A company can run a workload in two cloud regions.  
>
> Region X  
> Carbon intensity: 210 gCO2/kWh  
> Cost: $0.90 per compute hour  
>
> Region Y  
> Carbon intensity: 180 gCO2/kWh  
> Cost: $1.05 per compute hour  
>
> The job requires 8 compute hours.  
>
> Which region should the company select if they want to balance cost and carbon emissions? Explain how the decision should be made.

### Observations

- Models generally produced **reasonable recommendations**.  
- However, the **decision logic was often not transparent**.  
- In several cases, the reasoning appeared like a **black box**, making it difficult to understand how cost and carbon were weighted.

This revealed the need for **explainable sustainability decision systems**.

---

# Failure Case — Multi-Agent Simulation

To test the limits of LLM reasoning, we simulated a **30-day operational environment** using synthetic workload data generated with Cursor.

The simulation included:

- compute workloads  
- regional carbon intensity data  
- cost models  
- scheduling decisions  

The models were asked to reason about a multi-agent scheduling process:

> Simulate a carbon-aware scheduling agent that evaluates compute workloads over a 30-day period. Each day has workloads with different compute demands and each cloud region has a different carbon intensity. The agent should evaluate carbon emissions for each region, select the lowest-carbon region, and log the decision. Explain the reasoning process used by the agent.

### Observations

During testing:

- Some agent workflows entered **reasoning loops**.  
- The system repeatedly evaluated the same workloads.  
- This caused the simulation to hit **token limits and rate limits**.

This highlighted a key limitation of LLM-based multi-agent systems.

---

# Copilot Debugging Workflow

We also used **GitHub Copilot** to debug the prototype implementation.

Task reference:

https://github.com/IS492-SP26/team-project-carbon-emissions/tasks/f2849ec3-3c36-408a-8642-238db356e09b

While debugging the simulation pipeline, we asked Copilot for help identifying the cause of repeated loops in the agent orchestration logic:

> The planner and governance agents in my multi-agent simulation sometimes enter a loop where the same workload is repeatedly evaluated. The pipeline runs a 30-day simulation and eventually hits token limits. Help me debug why this might be happening and suggest safeguards to prevent infinite reasoning loops.

### Copilot Assistance

Copilot suggested improvements including:

- adding **state tracking** for processed workloads  
- implementing explicit **termination conditions**  
- limiting the number of reasoning iterations per job  

These changes significantly improved the **stability of the simulation pipeline**.

---

# Tool Comparison

| Tool | Strength |
|-----|-----|
| ChatGPT | Best reasoning explanations |
| Claude | Strong debugging and system reasoning |
| Copilot | Helpful for identifying orchestration issues |
| NotebookLM | Useful for research synthesis |

---

# Key Observations

Across all tools we observed several limitations:

- lack of verified emission factor sources  
- limited transparency in optimization decisions  
- difficulty handling complex multi-agent orchestration  
- risk of infinite reasoning loops  

---

# Design Implications

These prompting experiments directly informed the design of our system.

The **sust-AI-naible platform** therefore focuses on:

- deterministic carbon calculations  
- verified emissions data sources  
- transparent decision explanations  
- multi-agent orchestration with termination safeguards  

This approach ensures that emissions reductions are **auditable, reproducible, and verifiable**, rather than simply estimated by an LLM.
