# Interview Insights

To better understand how sustainability is currently considered in technology workflows, we conducted short interviews with professionals working in cloud infrastructure, governance and risk, and AI development.

---

## Key Interview Questions

### 1. How does your team currently consider sustainability when designing or deploying systems?

Most interviewees mentioned that sustainability is **not currently a primary decision-making factor** in technology workflows. Engineering teams typically focus on performance, scalability, reliability, and cost efficiency. While some optimization practices (such as reducing idle compute resources) indirectly reduce energy usage, these decisions are generally motivated by **cost savings rather than environmental impact**.

---

### 2. Are there tools or platforms that help measure the carbon impact of your infrastructure or workloads?

Participants mentioned that some cloud providers offer **carbon footprint dashboards and sustainability reports**, but these tools are usually high-level and retrospective. They provide historical insights about emissions rather than helping teams make decisions while deploying or running workloads.

---

### 3. What are the biggest challenges when trying to understand the environmental impact of cloud workloads or AI systems?

A common challenge mentioned was **data fragmentation**. Cloud workloads often run across multiple services, regions, and infrastructure layers, making it difficult to collect accurate emissions data. Additionally, many sustainability metrics are presented in a **technical format that is difficult for non-engineering stakeholders to interpret**.

---

### 4. Do developers or engineers receive any feedback about how their technical decisions affect energy consumption?

Interviewees noted that developers typically receive feedback related to **performance, latency, and cost**, but rarely about energy consumption or carbon emissions. As a result, engineers are often unaware of the environmental impact of their code, model training, or infrastructure configurations.

---

### 5. How do governance, risk, or leadership teams interpret sustainability metrics today?

Governance professionals explained that existing tools often present sustainability data through **complex dashboards or technical reports**, which can make it difficult for leadership teams to extract meaningful insights. Stakeholders often require **clear explanations and traceable data sources** in order to trust and act upon sustainability metrics.

---

### 6. What type of tool or system would make sustainability easier to incorporate into everyday workflows?

Participants suggested that an effective system should provide **actionable recommendations rather than just reporting data**. Ideally, the system would analyze infrastructure usage, identify more sustainable alternatives, and suggest optimizations that reduce energy consumption while maintaining performance.

---

### 7. How important do you think sustainability decision-making will become for technology teams in the future?

All interviewees agreed that sustainability will become increasingly important as cloud infrastructure and AI workloads continue to scale. They expect organizations to face **greater regulatory pressure, ESG reporting requirements, and stakeholder expectations**, which will require better tools for tracking and managing environmental impact.

---

# Interview Summaries

---

## Interview 1 — Ananya Kulkarni
**Role:** Cloud Infrastructure Engineer, SaaS Company  
**Duration:** 10 minutes  

Ananya manages containerized applications and data pipelines across multiple cloud regions.

She explained that resource optimization is usually considered only from a **cost and performance perspective**. Engineers frequently scale workloads or remove idle resources to reduce operational expenses, but environmental impact is rarely considered.

She also mentioned that while cloud providers offer sustainability dashboards, these tools are **not integrated into everyday engineering workflows**. Engineers often need to navigate separate tools to view emissions data.

Ananya believes engineers would make better sustainability decisions if insights were available **during infrastructure deployment**.

### Tool Failures Identified
- Sustainability data not integrated into infrastructure workflows  
- Lack of visibility into carbon differences between cloud regions  
- Carbon insights are retrospective rather than actionable  

### Opportunity for Our Tool
An intelligent assistant that integrates with deployment pipelines and **recommends greener infrastructure choices**, such as lower-carbon regions or optimized compute configurations.

---

## Interview 2 — Arjun Patel
**Role:** IT Governance & Risk Consultant, Big Four Consulting Firm  
**Duration:** 9 minutes  

Arjun works with organizations on governance frameworks and technology compliance processes.

He noted that sustainability reporting is becoming more important due to **ESG regulations and stakeholder expectations**, but organizations struggle to interpret technical emissions data.

Most sustainability platforms produce **complex dashboards** that are difficult for non-engineering stakeholders to understand.

Arjun emphasized the importance of **transparency and auditability**, explaining that governance teams need to know how emissions calculations were generated and what data sources were used.

### Tool Failures Identified
- Sustainability tools are too technical for governance stakeholders  
- Limited transparency in emissions calculations  
- Difficulty translating sustainability data into strategic actions  

### Opportunity for Our Tool
An AI-powered interface that **translates emissions data into clear, explainable insights**, while maintaining transparent audit trails for governance and compliance teams.

---

## Interview 3 — Neha Gupta
**Role:** Software Engineer, AI Startup  
**Duration:** 8 minutes  

Neha develops backend systems supporting machine learning pipelines and model training workloads.

She explained that **AI training and experimentation can be extremely compute-intensive**, but developers rarely track the environmental impact of these processes.

Engineering teams focus on improving model accuracy and training speed, while **energy consumption remains largely invisible during development**.

Neha believes developers would make more sustainable choices if they could see **how their experimentation impacts energy usage**.

### Tool Failures Identified
- Developers lack visibility into energy usage of AI training  
- Sustainability metrics are not integrated into ML workflows  
- No feedback encouraging efficient experimentation  

### Opportunity for Our Tool
A system that integrates with AI development workflows and provides **real-time insights into the environmental impact of compute workloads**.

---

# Key Takeaway

Across all three interviews, a consistent insight emerged: sustainability data may exist, but it rarely helps teams **make decisions in real time**.

Participants expressed the need for a system that goes beyond dashboards and reporting.

Instead, they envision an **AI sustainability advisor** capable of analyzing infrastructure and workloads, recommending more sustainable alternatives, and clearly explaining **why those decisions are better and how much energy or carbon emissions could be saved**.

This highlights the opportunity for an **AI agent that not only automates sustainability analysis but also guides decision-making through transparent reasoning and measurable environmental impact.**
